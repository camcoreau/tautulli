const assert = require('assert');
const Module = require('module');

const DAY = 24 * 60 * 60 * 1000;
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === '@jetbrains/youtrack-scripting-api/entities') {
    return {
      Issue: {
        onChange: function(rule) { return rule; },
        onSchedule: function(rule) { return rule; }
      },
      EnumField: {fieldType: {}},
      Field: {dateType: {}, dateTimeType: {}}
    };
  }
  if (request === '@jetbrains/youtrack-scripting-api/date-time') {
    return {
      after: function(value, period) {
        if (period === '7d') return value + 7 * DAY;
        if (period === '1d') return value + DAY;
        throw new Error('unexpected period ' + period);
      }
    };
  }
  return originalLoad(request, parent, isMain);
};

const stageRule = require('../stage-communications').rule;
const catchUpRule = require('../communication-catchup').rule;
Module._load = originalLoad;

function visibility() {
  return {clear: function() { this.cleared = true; }, cleared: false};
}

function context(stage, changed, options) {
  options = options || {};
  const ReviewStage = {};
  const auditConfirmedAt = Object.prototype.hasOwnProperty.call(
    options,
    'auditConfirmedAt'
  ) ? options.auditConfirmedAt : Date.now();
  const extensionProperties = Object.assign({}, options.extensionProperties || {});
  if (auditConfirmedAt !== null && auditConfirmedAt !== undefined) {
    extensionProperties.cmaAccountAuditConfirmedAt = auditConfirmedAt;
  }
  const issue = {
    id: 'CMA-TEST',
    reporter: options.reporter === undefined ? {login: 'member'} : options.reporter,
    extensionProperties: extensionProperties,
    comments: [],
    fields: {
      'Review Stage': {name: stage},
      'Account Status': {name: 'Inactive'},
      isChanged: function(field) { return Boolean(changed) && field === ReviewStage; }
    },
    added: [],
    addComment: function(text) {
      const comment = {
        text: text,
        created: Date.now(),
        deleted: false,
        permittedUsers: visibility(),
        permittedGroups: visibility()
      };
      this.comments.push(comment);
      this.added.push(comment);
      return comment;
    }
  };
  issue.comments.forEach = Array.prototype.forEach.bind(issue.comments);
  return {issue: issue, ReviewStage: ReviewStage};
}

function testStageChangeSendsAndDailyCatchUpDoesNothing() {
  const ctx = context('Inactivity Notice', true);
  assert.strictEqual(stageRule.guard(ctx), true);
  stageRule.action(ctx);
  assert.strictEqual(ctx.issue.added.length, 1);
  assert.strictEqual(catchUpRule.guard(ctx), false);
}

function testNonMessageStageIsRecordedWithoutCustomerComment() {
  const ctx = context('Removal Due', true);
  assert.strictEqual(stageRule.guard(ctx), true);
  stageRule.action(ctx);
  assert.strictEqual(ctx.issue.added.length, 0);
  assert.strictEqual(ctx.issue.extensionProperties.cmaObservedReviewStage, 'Removal Due');
}

function testUnchangedStageDoesNotCreateANewDelivery() {
  const ctx = context('Access Retained', false);
  assert.strictEqual(stageRule.guard(ctx), false);
  assert.strictEqual(ctx.issue.added.length, 0);
}

function testScheduledCatchUpOnlyRetriesManualOutcomeMessages() {
  ['Inactivity Notice', 'Subject to Deletion', 'Final Reminder'].forEach(
    function(stage) {
      const telemetry = context(stage, true, {reporter: null});
      stageRule.action(telemetry);
      telemetry.issue.reporter = {login: 'member'};
      assert.strictEqual(catchUpRule.guard(telemetry), false, stage);
      catchUpRule.action(telemetry);
      assert.strictEqual(telemetry.issue.added.length, 0, stage);
    }
  );

  const manualOutcome = context('Access Retained', true, {reporter: null});
  stageRule.action(manualOutcome);
  manualOutcome.issue.reporter = {login: 'member'};
  assert.strictEqual(catchUpRule.guard(manualOutcome), true);
  catchUpRule.action(manualOutcome);
  assert.strictEqual(manualOutcome.issue.added.length, 1);
  assert.strictEqual(catchUpRule.guard(manualOutcome), false);
}

function testHistoricalCatchUpIsAReadOnlyQuarantine() {
  const historical = context('Access Removed', false, {auditConfirmedAt: null});
  assert.strictEqual(catchUpRule.guard(historical), false);
  assert.strictEqual(historical.issue.added.length, 0);
  assert.deepStrictEqual(historical.issue.extensionProperties, {});
}

function testCatchUpRunsOnceDailyAsDefenseInDepth() {
  assert.strictEqual(catchUpRule.cron, '0 10 10 * * ?');
}

function testCatchUpCannotSendTelemetryMessageFromStaleEvidence() {
  const originalNow = Date.now;
  const day = 24 * 60 * 60 * 1000;
  Date.now = function() { return 10 * day; };
  try {
    const current = context('Inactivity Notice', true, {
      reporter: null,
      auditConfirmedAt: 9 * day
    });
    stageRule.action(current);
    current.issue.reporter = {login: 'member'};
    assert.strictEqual(catchUpRule.guard(current), false);
    catchUpRule.action(current);
    assert.strictEqual(current.issue.added.length, 0);
  } finally {
    Date.now = originalNow;
  }
}

testStageChangeSendsAndDailyCatchUpDoesNothing();
testNonMessageStageIsRecordedWithoutCustomerComment();
testUnchangedStageDoesNotCreateANewDelivery();
testScheduledCatchUpOnlyRetriesManualOutcomeMessages();
testHistoricalCatchUpIsAReadOnlyQuarantine();
testCatchUpRunsOnceDailyAsDefenseInDepth();
testCatchUpCannotSendTelemetryMessageFromStaleEvidence();

console.log('CMA communication rule tests passed');
