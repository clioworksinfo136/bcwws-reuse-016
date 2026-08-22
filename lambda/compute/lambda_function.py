"""
AWS Lambda function (Python) — Compute.

Server-side replacement for the in-browser handleCompute() that used to run
hundreds of sequential AppSync round-trips from the user's browser (~150 ms
each). This version scans every table once, does all arithmetic in memory, and
writes results back with BatchWriteItem (25 rows per call) from inside the same
AWS region, so the whole job is a handful of round-trips at ~2-5 ms each.

Two invocation modes
--------------------
1. HTTP (API Gateway proxy): creates a ComputeJob row, self-invokes
   asynchronously, and returns {"jobId": "..."} immediately. The browser polls
   the ComputeJob row to render progress. Returning right away keeps the
   request well clear of API Gateway's hard 30 s timeout no matter how large
   the dataset grows.
2. Async worker ({"jobId": "..."}): runs the actual compute and streams
   progress lines into that ComputeJob row.

Passes (identical arithmetic to the original client code)
---------------------------------------------------------
  validation - every Location of an AVG_WIDTH_TYPE must have a width
  pass 0     - populate unitprice/geometry/unit/etc from track_data.json
  pass 0b    - Track.width = mean of its Locations' width (pavement line types)
  cleanup    - drop Track/Date rows with no matching Location
  pass 1+2   - quantity, area, lastdate AND value in ONE write per track
               (the original did four separate round-trips per track: two
               updates in pass 1, then a get + an update in pass 2; unitprice
               and quan are both already known here, so the re-read is waste)
  pass 3     - Valve.value = number x unitprice x ton

Writes go straight to DynamoDB, which means AppSync subscriptions do NOT fire
for them; the frontend re-fetches Track/Date once the job reports 'done'.
"""

import datetime
import json
import math
import os
import uuid
from decimal import Decimal

import boto3

TRACK_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "track_data.json")

LOCATION_TABLE = os.environ["LOCATION_TABLE"]
TRACK_TABLE = os.environ["TRACK_TABLE"]
VALVE_TABLE = os.environ["VALVE_TABLE"]
DATE_TABLE = os.environ["DATE_TABLE"]
JOB_TABLE = os.environ["JOB_TABLE"]

# Set only on the starter copy of this function; it names the worker copy to
# invoke asynchronously. Two separate functions (rather than one that invokes
# itself) is what keeps CloudFormation from seeing a circular dependency
# between the Lambda and its own IAM policy.
WORKER_FUNCTION_NAME = os.environ.get("WORKER_FUNCTION_NAME")

# Feet per degree of latitude, matching the constant the client code used.
LAT_FT = 364000

# Pavement line types whose Track.width is averaged from their Locations' width.
AVG_WIDTH_TYPES = [
    "Stabilized Subgrade-L",
    "Limerock Base-L",
    "Asphalt Pavement Restoration-L",
    "Mill and Resurface Asphalt Pavement-L",
]

_ddb = boto3.resource("dynamodb")
_lambda = boto3.client("lambda")

with open(TRACK_DATA_PATH, "r", encoding="utf-8") as _f:
    TRACK_DATA = json.load(_f)

TRACK_DATA_BY_TYPE = {r["type"]: r for r in TRACK_DATA if r.get("type")}


# ---------------------------------------------------------------------------
# numeric helpers
# ---------------------------------------------------------------------------

def js_round(x: float) -> float:
    """Match JavaScript's Math.round (floor(x + 0.5)).

    Python's built-in round() uses banker's rounding, so round(2.5) == 2 while
    JS Math.round(2.5) == 3. Using floor(x + 0.5) keeps the Lambda's output
    bit-identical to the numbers the old client code produced.
    """
    return math.floor(x + 0.5)


def round2(x: float) -> float:
    """Round to 2 decimals the same way the client did: Math.round(x*100)/100."""
    return js_round(x * 100) / 100


def num(v):
    """DynamoDB Decimal (or None) -> float, for arithmetic."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    return None


def to_ddb(v):
    """Python number -> Decimal, which is the only numeric type DynamoDB takes."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return Decimal(str(round(v, 6)))
    if isinstance(v, int):
        return Decimal(v)
    return v


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def scan_all(table_name: str):
    """Scan an entire table, following pagination.

    The original client code called Amplify's list() with no pagination, which
    silently returns only the first page (default 100 items) - so any project
    with more than 100 tracks had rows quietly skipped by Compute. Scanning to
    exhaustion here fixes that.
    """
    table = _ddb.Table(table_name)
    items = []
    kwargs = {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        key = resp.get("LastEvaluatedKey")
        if not key:
            return items
        kwargs["ExclusiveStartKey"] = key


def batch_put(table_name: str, items):
    """Write items back with BatchWriteItem (25 per request, auto-batched)."""
    if not items:
        return
    table = _ddb.Table(table_name)
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)


def batch_delete(table_name: str, ids):
    if not ids:
        return
    table = _ddb.Table(table_name)
    with table.batch_writer() as batch:
        for _id in ids:
            batch.delete_item(Key={"id": _id})


# ---------------------------------------------------------------------------
# progress reporting
# ---------------------------------------------------------------------------

class Job:
    """Accumulates log lines and flushes them to the ComputeJob row.

    Flushing every line would reintroduce the per-step round-trip cost this
    whole rewrite exists to remove, so lines are buffered and pushed at pass
    boundaries or every FLUSH_EVERY lines - frequent enough that a 1 s poll
    still looks live.
    """

    FLUSH_EVERY = 40

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.table = _ddb.Table(JOB_TABLE)
        self.lines = []
        self.pending = 0

    def log(self, line: str, flush: bool = False):
        self.lines.append(line)
        self.pending += 1
        if flush or self.pending >= self.FLUSH_EVERY:
            self.flush()

    def flush(self):
        self.pending = 0
        self.table.update_item(
            Key={"id": self.job_id},
            UpdateExpression="SET #log = :log, updatedAt = :now",
            ExpressionAttributeNames={"#log": "log"},
            ExpressionAttributeValues={":log": self.lines, ":now": now_iso()},
        )

    def finish(self, status: str, error: str = None):
        self.table.update_item(
            Key={"id": self.job_id},
            UpdateExpression=(
                "SET #s = :s, #log = :log, finishedAt = :t, updatedAt = :t"
                + (", #e = :e" if error else "")
            ),
            ExpressionAttributeNames={
                "#s": "status",
                "#log": "log",
                **({"#e": "error"} if error else {}),
            },
            ExpressionAttributeValues={
                ":s": status,
                ":log": self.lines,
                ":t": now_iso(),
                **({":e": error} if error else {}),
            },
        )


# ---------------------------------------------------------------------------
# the compute itself
# ---------------------------------------------------------------------------

def run_compute(job: Job):
    locations = scan_all(LOCATION_TABLE)
    tracks = scan_all(TRACK_TABLE)

    # ---- validation: pavement points must all carry a width -----------------
    missing = [
        l for l in locations
        if l.get("type") in AVG_WIDTH_TYPES and not num(l.get("width"))
    ]
    if missing:
        lines = "\n".join(
            f"  - Track {l.get('track', '?')}, {l.get('date', '')} {l.get('time', '')} ({l.get('type')})"
            for l in missing
        )
        raise ValueError(
            f"Compute stopped: {len(missing)} point(s) of width-based pavement types have no width.\n\n"
            "Please go back to the History Data tab and fill in the width for these points "
            "before running Compute:\n\n" + lines
        )

    # Bucket Locations by track number once; every pass reads from this.
    pts_by_track = {}
    for l in locations:
        t = l.get("track")
        if t is None:
            continue
        pts_by_track.setdefault(int(t), []).append(l)

    track_by_number = {}
    for t in tracks:
        if t.get("track") is not None:
            track_by_number[int(t["track"])] = t

    # ---- pass 0: populate from track_data.json ------------------------------
    job.log("Pass 0: Populating unit price, total price, geometry, unit from trackData...", flush=True)
    # Keyed by id so a track touched by several passes is written exactly once.
    # BatchWriteItem rejects duplicate keys inside a single batch, so this also
    # guarantees the write is valid.
    writes = {}
    for track_no in sorted(pts_by_track.keys()):
        pts = pts_by_track[track_no]
        first_type = next((p.get("type") for p in pts if p.get("type")), None)
        match = TRACK_DATA_BY_TYPE.get(first_type) if first_type else None

        rec = track_by_number.get(track_no)
        created = rec is None
        if created:
            rec = {
                "id": str(uuid.uuid4()),
                "__typename": "Track",
                "track": to_ddb(track_no),
                "cost": True,
                "createdAt": now_iso(),
            }
            track_by_number[track_no] = rec

        rec["trip"] = True
        width_set = not num(rec.get("width"))
        if width_set:
            rec["width"] = to_ddb(1)
        if match:
            for src, dst in (
                ("id", "trackid"), ("unitprice", "unitprice"), ("totalprice", "totalprice"),
                ("geometry", "geometry"), ("unit", "unit"), ("color", "color"),
                ("type", "type"), ("typeid1", "typeid1"), ("typeid", "typeid"),
            ):
                if match.get(src) is not None:
                    rec[dst] = to_ddb(match[src])
        rec["updatedAt"] = now_iso()
        writes[rec["id"]] = rec

        if match:
            detail = (f'type "{first_type}" -> trackid={match.get("id", "-")}, '
                      f'geometry={match.get("geometry")}, unitprice={match.get("unitprice", "-")}, '
                      f'unit={match.get("unit", "-")}')
        elif first_type:
            detail = f'type "{first_type}" (no trackData match - values unchanged)'
        else:
            detail = "no point type found - values unchanged"
        job.log(f"  * Track {track_no} ({len(pts)} pt{'' if len(pts) == 1 else 's'}, "
                f"{'created' if created else 'existing'}): {detail}"
                f"{', width set to 1' if width_set else ''}")

    # ---- pass 0b: average widths for pavement line types --------------------
    job.log("Pass 0: Averaging Location width for pavement line tracks...", flush=True)
    for track_no, rec in track_by_number.items():
        if rec.get("type") not in AVG_WIDTH_TYPES:
            continue
        widths = [num(p.get("width")) for p in pts_by_track.get(track_no, [])
                  if num(p.get("width")) is not None]
        if not widths:
            job.log(f'  * Track {track_no} ("{rec.get("type")}"): no point widths - unchanged')
            continue
        avg = round2(sum(widths) / len(widths))
        rec["width"] = to_ddb(avg)
        writes[rec["id"]] = rec
        job.log(f'  * Track {track_no} ("{rec.get("type")}"): avg width = {avg} '
                f"(from {len(widths)} pt{'' if len(widths) == 1 else 's'})")

    job.log(f"Pass 0 done - processed {len(pts_by_track)} track(s).", flush=True)

    # ---- cleanup: Track/Date rows with no matching Location -----------------
    job.log("Removing Track rows with no matching Location...", flush=True)
    used_tracks = set(pts_by_track.keys())
    orphan_tracks = {t["id"] for t in tracks
                     if t.get("track") is None or int(t["track"]) not in used_tracks}
    batch_delete(TRACK_TABLE, orphan_tracks)
    for t in tracks:
        if t["id"] in orphan_tracks and t.get("track") is not None:
            track_by_number.pop(int(t["track"]), None)
    for orphan_id in orphan_tracks:
        writes.pop(orphan_id, None)

    job.log("Removing Date rows with no matching Location...", flush=True)
    used_dates = {l.get("date") for l in locations}
    dates = scan_all(DATE_TABLE)
    batch_delete(DATE_TABLE, [d["id"] for d in dates
                             if d.get("date") is None or d["date"] not in used_dates])

    # ---- pass 1 + 2: quantity, area, lastdate and value in one write --------
    job.log("Pass 1: Computing quantity, area, last date...", flush=True)
    for track_no, rec in sorted(track_by_number.items()):
        if not rec.get("cost"):
            continue
        pts = pts_by_track.get(track_no, [])
        geometry = rec.get("geometry")

        dates_on_track = sorted(p["date"] for p in pts if p.get("date"))
        if dates_on_track:
            rec["lastdate"] = dates_on_track[-1]

        if geometry == "line":
            total_len = sum(num(p.get("length")) or 0 for p in pts)
            w = num(rec.get("width"))
            w = 1 if w is None else w
            is_avg = rec.get("type") in AVG_WIDTH_TYPES
            quan = round2(total_len * w / 9) if is_avg else round2(total_len * w)
            rec["quan"] = to_ddb(quan)
            job.log(f"  * Track {track_no} (line): quan = Slength x width"
                    f"{' / 9' if is_avg else ''} = {round2(total_len)} x {w}"
                    f"{' / 9' if is_avg else ''} = {quan}")

        elif geometry == "point":
            n = len(pts)
            data_row = TRACK_DATA_BY_TYPE.get(rec.get("type")) if rec.get("type") else None
            ton = data_row.get("ton") if data_row else None
            if ton is not None:
                rec["quan"] = to_ddb(ton)
                rec["numpoint"] = to_ddb(n)
                job.log(f'  * Track {track_no} (point, {data_row.get("typeid1")}): quan = ton = {ton}')
            else:
                rec["quan"] = to_ddb(n)
                rec["numpoint"] = to_ddb(n)
                job.log(f"  * Track {track_no} (point): quan = point count = {n}")

        elif geometry == "polygon":
            ordered = sorted(pts, key=lambda p: f"{p.get('date', '')}T{p.get('time', '')}")
            n = len(ordered)
            if n < 3:
                rec["numpoint"] = to_ddb(n)
                rec["ft2"] = to_ddb(0)
                rec["yd2"] = to_ddb(0)
                rec["quan"] = to_ddb(0)
                job.log(f"  * Track {track_no} (polygon): only {n} pt(s) - need >=3, quan = 0")
            else:
                mid_lat = sum(num(p.get("lat")) or 0 for p in ordered) / n
                lng_ft = LAT_FT * math.cos(math.radians(mid_lat))
                area = 0.0
                for i in range(n):
                    j = (i + 1) % n
                    area += ((num(ordered[i].get("lng")) or 0) * lng_ft * (num(ordered[j].get("lat")) or 0) * LAT_FT
                             - (num(ordered[j].get("lng")) or 0) * lng_ft * (num(ordered[i].get("lat")) or 0) * LAT_FT)
                sq_ft = round2(abs(area) / 2)
                sq_yd = round2(sq_ft / 9)
                unit = rec.get("unit") or ""
                quan = sq_ft if unit == "SF" else sq_yd
                rec["numpoint"] = to_ddb(n)
                rec["ft2"] = to_ddb(sq_ft)
                rec["yd2"] = to_ddb(sq_yd)
                rec["quan"] = to_ddb(quan)
                job.log(f"  * Track {track_no} (polygon): area = {sq_ft} SF / {sq_yd} SY "
                        f"({n} pts), quan = {quan} ({unit or 'SY'})")

        # value = unitprice x quan, folded into this same write
        unitprice = num(rec.get("unitprice"))
        quan_v = num(rec.get("quan"))
        if unitprice is not None and quan_v is not None:
            value = round2(unitprice * quan_v)
            rec["value"] = to_ddb(value)
            job.log(f"  * Track {track_no}: value = unit price x quantity = "
                    f"{unitprice} x {quan_v} = {value}")
        else:
            if unitprice is None and quan_v is None:
                reason = "no unit price or quantity"
            elif unitprice is None:
                reason = "no unit price"
            else:
                reason = "no quantity"
            job.log(f"  * Track {track_no}: value skipped ({reason})")

        rec["updatedAt"] = now_iso()
        writes[rec["id"]] = rec

    batch_put(TRACK_TABLE, list(writes.values()))
    job.log(f"Pass 1 + 2 done - wrote {len(writes)} track row(s).", flush=True)

    # ---- pass 3: valve values ----------------------------------------------
    job.log("Pass 3: Computing Valve value = number x unit price x ton...", flush=True)
    valves = scan_all(VALVE_TABLE)
    valve_writes = []
    valued = 0
    for v in valves:
        number, unitprice, ton = num(v.get("number")), num(v.get("unitprice")), num(v.get("ton"))
        if number is not None and unitprice is not None and ton is not None:
            value = round2(number * unitprice * ton)
            v["value"] = to_ddb(value)
            v["updatedAt"] = now_iso()
            valve_writes.append(v)
            valued += 1
            job.log(f'  * Valve {v.get("valve") or v["id"]}: value = number x unitprice x ton = '
                    f"{number} x {unitprice} x {ton} = {value}")
        else:
            job.log(f'  * Valve {v.get("valve") or v["id"]}: skipped (missing number/unitprice/ton)')
    batch_put(VALVE_TABLE, valve_writes)
    job.log(f"Pass 3 done - valued {valued} valve(s) of {len(valves)} total.", flush=True)

    job.log("Compute complete.", flush=True)


# ---------------------------------------------------------------------------
# handler
# ---------------------------------------------------------------------------

def _response(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Content-Type": "application/json",
        },
        "body": json.dumps(payload),
    }


def lambda_handler(event, context):
    # ---- worker mode: run the compute for an existing job -------------------
    if isinstance(event, dict) and event.get("jobId") and not event.get("httpMethod"):
        job = Job(event["jobId"])
        try:
            run_compute(job)
            job.finish("done")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            job.log(f"ERROR: {exc}")
            job.finish("error", str(exc))
        return {"ok": True}

    # ---- HTTP mode ----------------------------------------------------------
    if (event or {}).get("httpMethod") == "OPTIONS":
        return _response(200, {})

    job_id = str(uuid.uuid4())
    _ddb.Table(JOB_TABLE).put_item(Item={
        "id": job_id,
        "__typename": "ComputeJob",
        "status": "running",
        "log": ["Starting compute..."],
        "startedAt": now_iso(),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    })

    # Kick the real work off asynchronously so this request returns straight
    # away, well inside API Gateway's 30 s ceiling.
    _lambda.invoke(
        FunctionName=WORKER_FUNCTION_NAME or context.function_name,
        InvocationType="Event",
        Payload=json.dumps({"jobId": job_id}).encode("utf-8"),
    )

    return _response(202, {"jobId": job_id})
