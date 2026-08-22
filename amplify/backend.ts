import { defineBackend } from '@aws-amplify/backend';
import { auth } from './auth/resource';
import { data } from './data/resource';
import { imagesStorage } from './storage/resource';
import { EventType } from 'aws-cdk-lib/aws-s3';
import { LambdaDestination } from 'aws-cdk-lib/aws-s3-notifications';
import * as path from 'path';
import { fileURLToPath } from 'url';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as cdk from 'aws-cdk-lib';

// ES modules (amplify/package.json has "type": "module") have no __dirname.
// Recreate it from import.meta.url so lambda.Code.fromAsset can resolve a
// relative filesystem path to the bundled Python function.
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const backend = defineBackend({
  auth,
  data,
  imagesStorage
});

// ---------------------------------------------------------------------------
// Nearest-station lookup API (public Python Lambda behind an open REST API).
//
// Custom CDK stack holding:
//   - a Python Lambda that bundles lambda/station_id/ (lambda_function.py +
//     station-id.json) and serves nearest-station "STA" lookups via KD-tree;
//   - a REST API Gateway with a single public GET /station proxy resource so
//     the app can call it without authentication.
//
// The endpoint URL is surfaced to the frontend via backend.addOutput (custom),
// which lands in amplify_outputs.json under `custom.stationApiUrl`.
// ---------------------------------------------------------------------------
const stationStack = backend.createStack('StationIdStack');

const stationLambda = new lambda.Function(stationStack, 'StationIdLambda', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'lambda_function.lambda_handler',
  timeout: cdk.Duration.seconds(10),
  memorySize: 512,
  code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambda', 'station_id')),
});

const stationApi = new apigw.LambdaRestApi(stationStack, 'StationIdApi', {
  handler: stationLambda,
  proxy: true,
  defaultMethodOptions: { authorizationType: apigw.AuthorizationType.NONE },
  // CORS: the frontend is served from a different domain than execute-api,
  // so browsers block cross-origin fetch() calls unless the API opts in.
  // The Lambda also returns Access-Control-Allow-* on every response and
  // answers the OPTIONS preflight directly (proxy routes OPTIONS to it).
  defaultCorsPreflightOptions: {
    allowOrigins: apigw.Cors.ALL_ORIGINS,
    allowMethods: apigw.Cors.ALL_METHODS,
  },
});

// ---------------------------------------------------------------------------
// Compute API (Python Lambda that runs the Compute job server-side).
//
// Replaces the old in-browser handleCompute(), which issued hundreds of
// sequential AppSync calls from the client (~150 ms each). This Lambda scans
// each table once, does the arithmetic in memory, and writes back with
// BatchWriteItem from inside the region, so the same job is a handful of
// round-trips at ~2-5 ms.
//
// POST /  -> {"jobId": "..."} immediately; the Lambda then self-invokes
// asynchronously and streams progress into the ComputeJob table, which the
// frontend polls. Returning right away keeps the request clear of API
// Gateway's hard 30 s timeout regardless of dataset size.
// ---------------------------------------------------------------------------
const computeStack = backend.createStack('ComputeStack');
const tables = backend.data.resources.tables;

const computeEnv = {
  LOCATION_TABLE: tables['Location'].tableName,
  TRACK_TABLE: tables['Track'].tableName,
  VALVE_TABLE: tables['Valve'].tableName,
  DATE_TABLE: tables['Date'].tableName,
  JOB_TABLE: tables['ComputeJob'].tableName,
};

// Two functions, one code asset, deliberately NOT one self-invoking function.
// A single Lambda calling grantInvoke(itself) makes CloudFormation reject the
// stack with a circular dependency: CDK gives the Function a DependsOn for its
// role's DefaultPolicy, while that same policy has to reference the Function's
// ARN. Splitting the roles breaks the cycle - the starter points at the worker,
// and the worker points at nothing.
const computeWorker = new lambda.Function(computeStack, 'ComputeWorker', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'lambda_function.lambda_handler',
  // Generous ceiling: the work is seconds, but a cold start plus a very large
  // table scan should never hit the limit mid-write and leave data half-updated.
  timeout: cdk.Duration.minutes(5),
  memorySize: 1024,
  code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambda', 'compute')),
  environment: computeEnv,
});

tables['Location'].grantReadData(computeWorker);
tables['Track'].grantReadWriteData(computeWorker);
tables['Valve'].grantReadWriteData(computeWorker);
tables['Date'].grantReadWriteData(computeWorker);
tables['ComputeJob'].grantReadWriteData(computeWorker);

const computeStarter = new lambda.Function(computeStack, 'ComputeStarter', {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'lambda_function.lambda_handler',
  timeout: cdk.Duration.seconds(30),
  memorySize: 256,
  code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambda', 'compute')),
  // WORKER_FUNCTION_NAME is what puts this copy into "starter" mode.
  environment: { ...computeEnv, WORKER_FUNCTION_NAME: computeWorker.functionName },
});

// The starter only ever creates the job row and kicks off the worker.
tables['ComputeJob'].grantReadWriteData(computeStarter);
computeWorker.grantInvoke(computeStarter);

const computeApi = new apigw.LambdaRestApi(computeStack, 'ComputeApi', {
  handler: computeStarter,
  proxy: true,
  defaultMethodOptions: { authorizationType: apigw.AuthorizationType.NONE },
  defaultCorsPreflightOptions: {
    allowOrigins: apigw.Cors.ALL_ORIGINS,
    allowMethods: apigw.Cors.ALL_METHODS,
  },
  // The station API already owns the account-level AWS::ApiGateway::Account
  // CloudWatch role, which is a singleton per account+region. Creating a second
  // one here would have two stacks fighting over the same resource.
  cloudWatchRole: false,
});

backend.addOutput({
  custom: {
    stationApiUrl: stationApi.url,
    computeApiUrl: computeApi.url,
  },
});
