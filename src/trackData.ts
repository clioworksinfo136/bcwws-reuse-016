export type TrackRow = {
  id: string;
  type: string;
  geometry: 'line' | 'point' | 'polygon';
  unitprice: number | null;
  color: string | null;
  unit: string | null;
};

export const TRACK_DATA: TrackRow[] = [
  { id: '#0-14', type: '#0-14: Excavation in Hard Rock', geometry: 'line', unitprice: 33.00, color: 'red', unit:"Linear Foot"},
  { id: '#0-21', type: "#0-21: Pavement Marking & Striping", geometry: 'line', unitprice: 168750.00, color: 'black', unit: "Lump Sum" },
  { id: '#0-22', type: "#0-22: Type 'F' Curb and Gutter", geometry: 'line', unitprice: 49.00, color: 'black', unit: "Linear Foot" },
  { id: '#0-23', type: "#0-23: Type 'E' Curb and Gutter", geometry: 'line', unitprice: 56.00, color: 'black', unit: "Linear Foot" },
  { id: '#0-24', type: "#0-24: Type 'D' Curb", geometry: 'line', unitprice: 47.00, color: 'black', unit: "Linear Foot" },
  { id: '#0-32', type: '#0-32: Chain Link Fence', geometry: 'line', unitprice: 48.00, color: 'light green', unit: "Linear Foot" },
  { id: '#0-33', type: '#0-33: Aluminum Fence', geometry: 'line', unitprice: 41.00, color: 'light green', unit: "Linear Foot" },
  { id: '#0-34', type: '#0-34: Guard Rail', geometry: 'line', unitprice: 81.00, color: 'black', unit: "Linear Foot" },
  { id: '#0-45', type: '#0-45:24" DI Pipe', geometry: 'line', unitprice: 437.00, color: 'purple', unit: "Linear Foot"},
  { id: '#0-46', type: '#0-46:30" DI Pipe', geometry: 'line', unitprice: 658.00, color: 'purple', unit: "Linear Foot"},
  { id: '#0-1', type: '#0-1:Bonds and Insurance', geometry: 'point', unitprice: 718250.00, color: 'black', unit: "Lump Sum" },
  { id: '#0-7', type: '#0-7: 24 inch Plug Valve', geometry: 'point', unitprice: 59867.00, color: 'purple', unit: "Each"},
  { id: '#0-8', type: '#0-8: 30 inch Plug Valve', geometry: 'point', unitprice: 90045.00, color: 'purple', unit: "Each"},
  { id: '#0-9', type: '#0-9: Valve Connection', geometry: 'point', unitprice: 14808.00, color: 'purple', unit: "Each"},
  { id: '#0-10', type: '#0-10: NRWWTP Connection', geometry: 'point', unitprice: 229369.00, color: 'purple', unit: "Lump Sum" },
  { id: '#0-11', type: '#0-11: 30 inch Line Stop', geometry: 'point', unitprice: 106061.00, color: 'purple', unit: "Each" },
  { id: '#0-12', type: '#0-12: EWTM Connection', geometry: 'point', unitprice: 16250.00, color: 'purple', unit: "Each" },
  { id: '#0-13', type: '#0-13: Removal and Replacement of Unsuitable Material', geometry: 'point', unitprice: 36.00, color:  'red', unit: "Cubic Yard" },
  { id: '#0-15', type: '#0-15:  Minor Utility Adjustment', geometry: 'point', unitprice: 2708.00, color: 'red', unit: "Each" },
  { id: '#0-16', type: '#0-16:  Major Utility Adjustment', geometry: 'point', unitprice: 5417.00, color: 'red', unit: "Each" },
  { id: '#0-2', type: '#0-2:Mobilization', geometry: 'point', unitprice: 478667.00, color: 'black', unit: "Lump Sum" },
  { id: '#0-3', type: '#0-3: Maintenance of Traffic', geometry: 'point', unitprice: 118125.00, color: 'black', unit: "Lump Sum" },
  {id: '#0-30', type: '#0-30: Replace Existing Potable Water Service', geometry: 'point', unitprice: 3275.00, color: 'blue', unit: "Each" },
  { id: '#0-31', type: '#0-31: Replace Existing Sanitary Sewer Lateral', geometry: 'point', unitprice: 2854.00, color: 'green',unit: "Each"  },
  { id: '#0-35', type: '#0-35:  Road Sign & Post Assembly', geometry: 'point', unitprice: 2188.00, color: 'red', unit: "Each"},
  { id: '#0-36', type: '#0-36:  Mailbox', geometry: 'point', unitprice: 369.00, color: 'red'  , unit: "Each" },
  { id: '#0-42', type: '#0-42: Restoration of Golf Course', geometry: 'point', unitprice: 66838.00, color: 'red', unit: "Each" },
  { id: '#0-43', type: "#0-43: Existing Trees", geometry: 'point', unitprice: 9375.00, color: 'light green', unit: "Each" },
  { id: '#0-44', type: '#0-44: Florida Number 2 Trees', geometry: 'point', unitprice: 5000.00, color: 'light green', unit: "Each" },
  { id: '#0-6', type: '#0-6: DI Fittings', geometry: 'point', unitprice: 31762.00, color: 'purple', unit: "Square Foot"   },
  { id: '#0-17', type: '#0-17:  Subgrade', geometry: 'polygon', unitprice: 15.00, color: 'grey', unit: "Square Foot" },
  { id: '#0-18', type: '#0-18: Limerock Base', geometry: 'polygon', unitprice: 48.75, color: 'grey', unit: "Square Foot" },
  { id: '#0-19', type: '#0-19: Asphalt Pavement Restoration', geometry: 'polygon', unitprice: 31.00, color: 'grey', unit: "Square Foot" },
  { id: '#0-20', type: '#0-20: Mill and Resurface Asphalt Pavement', geometry: 'polygon', unitprice: 19.00, color: 'grey', unit: "Square Foot" },
  { id: '#0-25', type: '#0-25: Concrete Median', geometry: 'polygon', unitprice: 107.00, color:'grey', unit: "Square Foot" },
  { id: '#0-26', type: '#0-26: Concrete Sidewalk', geometry: 'polygon', unitprice: 107.00, color: "grey", unit: "Square Foot"  },
  { id: '#0-27', type: '#0-27:  Asphalt Driveway', geometry: 'polygon', unitprice: 124.00, color: "grey", unit: "Square Foot"  },
  { id: '#0-28', type: '#0-28: Concrete Driveway', geometry: 'polygon', unitprice: 191.00, color: "grey", unit: "Each"  },
  { id: '#0-29', type: '#0-29: Paver Driveway', geometry: 'polygon', unitprice: 127.00, color:'grey', unit: "Square Foot"   },
  { id: '#0-37', type: '#0-37:  Asphalt Walkway', geometry: 'polygon', unitprice: 81.00, color: 'grey' , unit: "Square Foot" },
  { id: '#0-38', type: '#0-38: Paver Walkway', geometry: 'polygon', unitprice: 156.00, color: 'grey', unit: "Square Foot" },
  { id: '#0-39', type: '#0-39: Concrete Golf Cart Path', geometry: 'polygon', unitprice: 112.00, color: 'grey', unit: "Square Foot" },
  { id: '#0-40', type: '#0-40: Concrete Golf Cart Path with Rolled Curb', geometry: 'polygon', unitprice: 131.00, color: 'grey', unit: "Square Foot"  },
  { id: '#0-41', type: '#0-41: Restoration of Green Areas', geometry: 'polygon', unitprice: 10.50, color: 'grey',unit: "Square Foot"  },
];

export const TRACK_TYPES = TRACK_DATA.map(r => r.type);

export type ValvePriceRow = {
  valve: string;
  unitprice: number;
  ton: number;
};

export const VALVE_PRICE_DATA: ValvePriceRow[] = [
  { valve: '#0-6 24 in 11.25-bend' },
  { valve: '#0-6 24 in 22.5-bend'   },
  { valve: '#0-6 24 in 45-bend'     },
  { valve: '#0-6 24 in 90-bend'     },
];