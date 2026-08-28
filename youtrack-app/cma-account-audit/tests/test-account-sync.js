const assert = require('assert');
const Module = require('module');

const NOW = 1_800_000_000_000;
const MEMBER = {id: 'user-1', login: 'member'};
const OTHER_MEMBER = {id: 'user-2', login: 'other-member'};

const runtime = {
  matches: {},
  reporters: {},
  created: [],
  searchCalls: [],
  mutations: [],
  failOnField: null
};

function trackedFields(issueId, initial) {
  return new Proxy(Object.assign({}, initial || {}), {
    set: function(target, fieldName, value) {
      runtime.mutations.push({issueId: issueId, fieldName: String(fieldName), value: value});
      if (runtime.failOnField === fieldName) {
        throw new Error('simulated mutation failure for ' + fieldName);
      }
      target[fieldName] = value;
      return true;
    }
  });
}

function MockIssue(reporter, project, summary) {
  const issueId = 'CMA-NEW-' + (runtime.created.length + 1);
  const issue = {
    id: issueId,
    reporter: reporter,
    project: project,
    summary: summary,
    description: '',
    fields: trackedFields(issueId)
  };
  runtime.created.push(issue);
  return issue;
}

const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === '@jetbrains/youtrack-scripting-api/entities') {
    return {
      Issue: MockIssue,
      User: {
        findUniqueByEmail: function(email) {
          return runtime.reporters[email] || null;
        },
        fieldType: {}
      },
      Field: {
        stringType: {},
        dateType: {},
        dateTimeType: {},
        integerType: {}
      },
      EnumField: {fieldType: {}}
    };
  }
  if (request === '@jetbrains/youtrack-scripting-api/search') {
    return {
      search: function(project, query) {
        runtime.searchCalls.push(query.query);
        const field = query.query.indexOf('{Plex User ID}:') === 0 ?
          'Plex User ID' : 'Plex Username';
        return runtime.matches[field] || [];
      }
    };
  }
  return originalLoad(request, parent, isMain);
};

const handler = require('../account-sync').httpHandler.endpoints[0].handle;
Module._load = originalLoad;

const bundles = {
  'Account Status': ['Active', 'Inactive', 'Never Used'],
  'Review Stage': [
    'Active',
    'Inactivity Notice',
    'Subject to Deletion',
    'Final Reminder',
    'Removal Due',
    'Access Removed',
    'Access Retained',
    'Exempt'
  ]
};

const scalarFields = [
  'Plex User ID',
  'Plex Username',
  'Last Streamed',
  'Total Plays',
  'Watch Time',
  'Account Audit Confirmed At'
];

function resetRuntime() {
  runtime.matches = {};
  runtime.reporters = {};
  runtime.created = [];
  runtime.searchCalls = [];
  runtime.mutations = [];
  runtime.failOnField = null;
}

function project(shortName, options) {
  options = options || {};
  const missingFields = options.missingFields || [];
  const missingValues = options.missingValues || {};
  const projectFields = {};

  scalarFields.forEach(function(fieldName) {
    projectFields[fieldName] = {};
  });
  Object.keys(bundles).forEach(function(fieldName) {
    const values = {};
    bundles[fieldName].forEach(function(name) {
      if ((missingValues[fieldName] || []).indexOf(name) === -1) {
        values[name] = {name: name};
      }
    });
    projectFields[fieldName] = {
      findValueByName: function(name) { return values[name] || null; }
    };
  });
  missingFields.forEach(function(fieldName) {
    delete projectFields[fieldName];
  });

  return {
    shortName: shortName || 'CMA',
    findFieldByName: function(name) { return projectFields[name] || null; },
    value: function(fieldName, valueName) {
      const field = projectFields[fieldName];
      return field && field.findValueByName ? field.findValueByName(valueName) : null;
    }
  };
}

function validBody(overrides) {
  return Object.assign({
    plexUserId: 'plex-123',
    plexUsername: 'member',
    totalPlays: 12,
    watchSeconds: 3600,
    lastStreamedMs: NOW - (60 * 24 * 60 * 60 * 1000),
    watchTime: '1 hrs 0 mins',
    accountStatus: 'Inactive',
    reviewNeeded: true,
    email: 'member@example.com'
  }, overrides || {});
}

function context(body, projectOverride) {
  const response = {
    code: 200,
    payload: null,
    json: function(value) { this.payload = value; }
  };
  return {
    project: projectOverride || project('CMA'),
    currentUser: {login: 'audit-bot'},
    request: {json: function() { return body; }},
    response: response
  };
}

function existingIssue(targetProject, options) {
  options = options || {};
  const issueId = options.id || 'CMA-2';
  const initial = {
    'Plex User ID': options.plexUserId || 'plex-123',
    'Plex Username': options.plexUsername || 'member',
    'Account Status': targetProject.value(
      'Account Status',
      options.accountStatus || 'Inactive'
    ),
    'Review Stage': options.stage ? targetProject.value('Review Stage', options.stage) : null
  };
  if (options.confirmedAt !== undefined) {
    initial['Account Audit Confirmed At'] = options.confirmedAt;
  }
  return {
    id: issueId,
    project: targetProject,
    reporter: options.reporter === undefined ? MEMBER : options.reporter,
    fields: trackedFields(issueId, initial)
  };
}

function matchExisting(issue) {
  runtime.matches['Plex User ID'] = [issue];
  runtime.reporters['member@example.com'] = MEMBER;
}

function assertNoMutation() {
  assert.deepStrictEqual(runtime.mutations, []);
  assert.strictEqual(runtime.created.length, 0);
}

function testProjectBoundary() {
  resetRuntime();
  const ctx = context(validBody(), project('SUPPORT'));
  handler(ctx);
  assert.strictEqual(ctx.response.code, 403);
  assert.strictEqual(runtime.searchCalls.length, 0);
  assertNoMutation();
}

function testPayloadValidationStopsBeforeSearchOrMutation() {
  const invalidPayloads = [
    {body: null, error: /JSON object/},
    {body: validBody({plexUserId: ''}), error: /plexUserId/},
    {body: validBody({email: ''}), error: /email/},
    {body: validBody({totalPlays: Number.MAX_SAFE_INTEGER + 1}), error: /safe integer/},
    {body: validBody({watchSeconds: 1.5}), error: /safe integer/},
    {body: validBody({watchTime: '999 hrs'}), error: /watchTime does not match/},
    {body: validBody({accountStatus: 'Paused'}), error: /accountStatus/},
    {body: validBody({accountStatus: 'Never Used'}), error: /Never Used requires/},
    {
      body: validBody({accountStatus: 'Inactive', totalPlays: 0, lastStreamedMs: null}),
      error: /Never Used requires/
    },
    {body: validBody({totalPlays: 0}), error: /zero-play accounts/},
    {body: validBody({lastStreamedMs: null}), error: /accounts with plays/},
    {
      body: validBody({accountStatus: 'Active', reviewNeeded: true}),
      error: /Active requires/
    },
    {
      body: validBody({accountStatus: 'Inactive', reviewNeeded: false}),
      error: /Inactive requires/
    },
    {body: validBody({lastStreamedMs: 0}), error: /positive timestamp/},
    {
      body: validBody({lastStreamedMs: NOW + (5 * 60 * 1000) + 1}),
      error: /future/
    }
  ];

  invalidPayloads.forEach(function(entry) {
    resetRuntime();
    const ctx = context(entry.body);
    handler(ctx);
    assert.strictEqual(ctx.response.code, 400);
    assert.match(ctx.response.payload.error, entry.error);
    assert.strictEqual(runtime.searchCalls.length, 0);
    assertNoMutation();
  });
}

function testFutureTimestampAtSkewBoundaryIsAccepted() {
  resetRuntime();
  const ctx = context(validBody({
    accountStatus: 'Active',
    reviewNeeded: false,
    lastStreamedMs: NOW + (5 * 60 * 1000)
  }));
  handler(ctx);
  assert.strictEqual(ctx.response.payload.result, 'healthy-no-ticket');
  assertNoMutation();
}

function testHealthyAccountDoesNotCreateOrStampATicket() {
  resetRuntime();
  const ctx = context(validBody({accountStatus: 'Active', reviewNeeded: false}));
  handler(ctx);
  assert.strictEqual(ctx.response.payload.result, 'healthy-no-ticket');
  assertNoMutation();
}

function testCanonicalNeverUsedFactsAreAccepted() {
  resetRuntime();
  let ctx = context(validBody({
    totalPlays: 0,
    lastStreamedMs: null,
    watchSeconds: 0,
    watchTime: '0 mins',
    accountStatus: 'Never Used',
    reviewNeeded: false
  }));
  handler(ctx);
  assert.strictEqual(ctx.response.payload.result, 'healthy-no-ticket');
  assertNoMutation();

  resetRuntime();
  runtime.reporters['member@example.com'] = MEMBER;
  ctx = context(validBody({
    totalPlays: 0,
    lastStreamedMs: null,
    watchSeconds: 0,
    watchTime: '0 mins',
    accountStatus: 'Never Used',
    reviewNeeded: true
  }));
  handler(ctx);
  assert.strictEqual(ctx.response.payload.result, 'created');
  assert.strictEqual(ctx.response.payload.action, 'notice-started');
  assert.strictEqual(runtime.created[0].fields['Account Status'].name, 'Never Used');
  assert.strictEqual(runtime.created[0].fields['Account Audit Confirmed At'], NOW);
}

function testNewReviewRequiresAReporterBeforeCreation() {
  resetRuntime();
  const ctx = context(validBody());
  handler(ctx);
  assert.strictEqual(ctx.response.code, 422);
  assert.match(ctx.response.payload.error, /reporter/);
  assertNoMutation();
}

function testNewReviewIsCreatedAndStampedOnce() {
  resetRuntime();
  runtime.reporters['member@example.com'] = MEMBER;
  const ctx = context(validBody());
  handler(ctx);
  assert.strictEqual(ctx.response.payload.result, 'created');
  assert.strictEqual(ctx.response.payload.action, 'notice-started');
  assert.strictEqual(runtime.created.length, 1);
  assert.strictEqual(runtime.created[0].fields['Review Stage'].name, 'Inactivity Notice');
  assert.strictEqual(runtime.created[0].fields['Plex User ID'], 'plex-123');
  assert.strictEqual(runtime.created[0].fields['Account Audit Confirmed At'], NOW);
  assert.strictEqual(
    runtime.mutations.filter(function(item) {
      return item.fieldName === 'Account Audit Confirmed At';
    }).length,
    1
  );
}

function testDuplicateAndCrossIdentifierConflictsDoNotMutate() {
  resetRuntime();
  let targetProject = project('CMA');
  runtime.matches['Plex User ID'] = [
    existingIssue(targetProject, {id: 'CMA-2'}),
    existingIssue(targetProject, {id: 'CMA-3'})
  ];
  let ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.code, 409);
  assert.match(ctx.response.payload.error, /Multiple CMA tickets/);
  assertNoMutation();

  resetRuntime();
  targetProject = project('CMA');
  runtime.matches['Plex User ID'] = [
    existingIssue(targetProject, {id: 'CMA-2', plexUsername: 'member-old'})
  ];
  runtime.matches['Plex Username'] = [
    existingIssue(targetProject, {id: 'CMA-3', plexUserId: 'plex-other'})
  ];
  ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.code, 409);
  assert.match(ctx.response.payload.error, /different CMA tickets/);
  assertNoMutation();

  resetRuntime();
  targetProject = project('CMA');
  runtime.matches['Plex Username'] = [
    existingIssue(targetProject, {id: 'CMA-4', plexUserId: 'plex-other'})
  ];
  ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.code, 409);
  assert.match(ctx.response.payload.error, /different Plex User ID/);
  assertNoMutation();
}

function testExistingReporterMustResolveAndMatchBeforeMutation() {
  resetRuntime();
  let targetProject = project('CMA');
  let existing = existingIssue(targetProject, {confirmedAt: 123});
  runtime.matches['Plex User ID'] = [existing];
  let ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.code, 422);
  assert.match(ctx.response.payload.error, /reporter/);
  assert.strictEqual(existing.fields['Account Audit Confirmed At'], 123);
  assertNoMutation();

  resetRuntime();
  targetProject = project('CMA');
  existing = existingIssue(targetProject, {confirmedAt: 123});
  runtime.matches['Plex User ID'] = [existing];
  runtime.reporters['member@example.com'] = OTHER_MEMBER;
  ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.code, 409);
  assert.match(ctx.response.payload.error, /reporter does not match/);
  assert.strictEqual(existing.fields['Account Audit Confirmed At'], 123);
  assertNoMutation();
}

function testMissingFieldsAndBundleValuesFailBeforeMutation() {
  resetRuntime();
  let targetProject = project('CMA', {missingFields: ['Account Audit Confirmed At']});
  let existing = existingIssue(targetProject);
  matchExisting(existing);
  let ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.code, 422);
  assert.match(ctx.response.payload.error, /Account Audit Confirmed At/);
  assertNoMutation();

  resetRuntime();
  targetProject = project('CMA', {missingValues: {'Account Status': ['Inactive']}});
  existing = existingIssue(targetProject, {accountStatus: 'Active'});
  matchExisting(existing);
  ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.code, 422);
  assert.match(ctx.response.payload.error, /Account Status does not contain value Inactive/);
  assertNoMutation();

  resetRuntime();
  targetProject = project('CMA', {missingValues: {'Review Stage': ['Inactivity Notice']}});
  existing = existingIssue(targetProject);
  matchExisting(existing);
  ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.code, 422);
  assert.match(ctx.response.payload.error, /Review Stage does not contain value Inactivity Notice/);
  assertNoMutation();
}

function testSuccessfulExistingUpdateChangesFactsAndExactStamp() {
  resetRuntime();
  const targetProject = project('CMA');
  const existing = existingIssue(targetProject, {confirmedAt: 123});
  matchExisting(existing);
  const ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.payload.result, 'updated');
  assert.strictEqual(ctx.response.payload.action, 'notice-started');
  assert.strictEqual(existing.fields['Review Stage'].name, 'Inactivity Notice');
  assert.strictEqual(existing.fields['Total Plays'], 12);
  assert.strictEqual(existing.fields['Account Audit Confirmed At'], NOW);
}

function testMutationExceptionEscapesAndCannotStampSuccess() {
  resetRuntime();
  const targetProject = project('CMA');
  const existing = existingIssue(targetProject, {confirmedAt: 123});
  matchExisting(existing);
  runtime.failOnField = 'Review Stage';
  const ctx = context(validBody(), targetProject);
  assert.throws(function() { handler(ctx); }, /simulated mutation failure/);
  assert.strictEqual(ctx.response.payload, null);
  assert.strictEqual(existing.fields['Account Audit Confirmed At'], 123);
  assert.strictEqual(
    runtime.mutations.some(function(item) {
      return item.fieldName === 'Account Audit Confirmed At';
    }),
    false
  );
}

function testRepeatedDailySyncDoesNotRestartAnOpenReview() {
  resetRuntime();
  const targetProject = project('CMA');
  const existing = existingIssue(targetProject, {stage: 'Inactivity Notice'});
  matchExisting(existing);

  const first = context(validBody(), targetProject);
  handler(first);
  const second = context(validBody(), targetProject);
  handler(second);

  assert.strictEqual(first.response.payload.action, 'review-already-in-progress');
  assert.strictEqual(second.response.payload.action, 'review-already-in-progress');
  assert.strictEqual(existing.fields['Review Stage'].name, 'Inactivity Notice');
  assert.strictEqual(runtime.created.length, 0);
  assert.strictEqual(existing.fields['Account Audit Confirmed At'], NOW);
}

function testActivityAutomaticallyRetainsAnOpenReview() {
  resetRuntime();
  const targetProject = project('CMA');
  const existing = existingIssue(targetProject, {stage: 'Subject to Deletion'});
  matchExisting(existing);
  const ctx = context(validBody({accountStatus: 'Active', reviewNeeded: false}), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.payload.action, 'retained');
  assert.strictEqual(existing.fields['Review Stage'].name, 'Access Retained');
  assert.strictEqual(existing.fields['Account Audit Confirmed At'], NOW);
}

function testRetainedReviewNeedsANewActiveBaselineBeforeRestart() {
  resetRuntime();
  const targetProject = project('CMA');
  const existing = existingIssue(targetProject, {
    stage: 'Access Retained',
    accountStatus: 'Inactive'
  });
  matchExisting(existing);

  let ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.payload.action, 'retained-awaiting-new-active-baseline');
  assert.strictEqual(existing.fields['Review Stage'].name, 'Access Retained');

  ctx = context(validBody({accountStatus: 'Active', reviewNeeded: false}), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.payload.action, 'facts-only');
  assert.strictEqual(existing.fields['Account Status'].name, 'Active');

  ctx = context(validBody({accountStatus: 'Inactive', reviewNeeded: true}), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.payload.action, 'notice-restarted-after-active-baseline');
  assert.strictEqual(existing.fields['Review Stage'].name, 'Inactivity Notice');
}

function testTerminalStageIsProtectedButAuditStillStamped() {
  resetRuntime();
  const targetProject = project('CMA');
  const existing = existingIssue(targetProject, {stage: 'Exempt'});
  matchExisting(existing);
  const ctx = context(validBody(), targetProject);
  handler(ctx);
  assert.strictEqual(ctx.response.payload.action, 'protected-terminal-stage');
  assert.strictEqual(existing.fields['Review Stage'].name, 'Exempt');
  assert.strictEqual(existing.fields['Account Audit Confirmed At'], NOW);
}

const originalDateNow = Date.now;
Date.now = function() { return NOW; };
try {
  testProjectBoundary();
  testPayloadValidationStopsBeforeSearchOrMutation();
  testFutureTimestampAtSkewBoundaryIsAccepted();
  testHealthyAccountDoesNotCreateOrStampATicket();
  testCanonicalNeverUsedFactsAreAccepted();
  testNewReviewRequiresAReporterBeforeCreation();
  testNewReviewIsCreatedAndStampedOnce();
  testDuplicateAndCrossIdentifierConflictsDoNotMutate();
  testExistingReporterMustResolveAndMatchBeforeMutation();
  testMissingFieldsAndBundleValuesFailBeforeMutation();
  testSuccessfulExistingUpdateChangesFactsAndExactStamp();
  testMutationExceptionEscapesAndCannotStampSuccess();
  testRepeatedDailySyncDoesNotRestartAnOpenReview();
  testActivityAutomaticallyRetainsAnOpenReview();
  testRetainedReviewNeedsANewActiveBaselineBeforeRestart();
  testTerminalStageIsProtectedButAuditStillStamped();
} finally {
  Date.now = originalDateNow;
}

console.log('CMA account-sync endpoint tests passed');
