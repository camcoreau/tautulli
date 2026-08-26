const assert = require('assert');
const Module = require('module');

const DAY = 24 * 60 * 60 * 1000;
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === '@jetbrains/youtrack-scripting-api/entities') {
    return {
      Issue: {onSchedule: function(rule) { return rule; }},
      EnumField: {fieldType: {}},
      Field: {dateType: {}},
      State: {fieldType: {}}
    };
  }
  if (request === '@jetbrains/youtrack-scripting-api/date-time') {
    return {
      after: function(value, period) {
        assert.strictEqual(period, '7d');
        return value + 7 * DAY;
      }
    };
  }
  return originalLoad(request, parent, isMain);
};

const communications = require('../communications');
const originalNeedsMessage = communications.needsMessage;
const rule = require('../lifecycle-catchup').rule;
Module._load = originalLoad;

function context(options) {
  const ReviewStage = {
    InactivityNotice: {name: 'Inactivity Notice'},
    SubjectToDeletion: {name: 'Subject to Deletion'},
    FinalReminder: {name: 'Final Reminder'},
    RemovalDue: {name: 'Removal Due'},
    AccessRemoved: {name: 'Access Removed'},
    AccessRetained: {name: 'Access Retained'},
    Exempt: {name: 'Exempt'}
  };
  const AccountStatus = {
    Active: {name: 'Active'},
    Inactive: {name: 'Inactive'},
    NeverUsed: {name: 'Never Used'}
  };
  const Outcome = {
    Pending: {name: 'Pending'},
    Retained: {name: 'Retained'},
    Removed: {name: 'Removed'},
    Exempt: {name: 'Exempt'}
  };
  const RemovalReason = {
    Inactivity: {name: 'Inactivity'},
    NeverUsed: {name: 'Never Used'}
  };
  const State = {
    New: {name: 'New'},
    Pending: {name: 'Pending'},
    Solved: {name: 'Solved'}
  };
  const values = {
    ReviewStage: options.stageKey ? ReviewStage[options.stageKey] : null,
    AccountStatus: AccountStatus[options.accountStatusKey || 'Inactive'],
    Outcome: Outcome[options.outcomeKey || 'Pending'],
    State: State[options.stateKey || 'Pending'],
    InactivityNoticeSent: options.noticeSent || null,
    GracePeriodEnds: options.graceEnds || null,
    RemovalCompleted: options.removalCompleted || null,
    RemovalReason: options.removalReasonKey ? RemovalReason[options.removalReasonKey] : null
  };
  values.is = function(field, value) {
    if (field === ReviewStage) return values.ReviewStage === value;
    if (field === AccountStatus) return values.AccountStatus === value;
    if (field === Outcome) return values.Outcome === value;
    if (field === State) return values.State === value;
    return false;
  };

  return {
    issue: {fields: values},
    ReviewStage: ReviewStage,
    AccountStatus: AccountStatus,
    Outcome: Outcome,
    RemovalReason: RemovalReason,
    State: State
  };
}

function withMessageNeeded(value, callback) {
  communications.needsMessage = function() { return value; };
  try {
    callback();
  } finally {
    communications.needsMessage = originalNeedsMessage;
  }
}

function testLegacyActivePendingReviewIsRetained() {
  const ctx = context({accountStatusKey: 'Active'});

  assert.strictEqual(rule.guard(ctx), true);
  rule.action(ctx);

  assert.strictEqual(ctx.issue.fields.ReviewStage, ctx.ReviewStage.AccessRetained);
}

function testNeverUsedNoticeStartsWhenMessageCanBeSent() {
  const ctx = context({
    stageKey: 'InactivityNotice',
    accountStatusKey: 'NeverUsed',
    stateKey: 'New',
    noticeSent: 1000
  });

  withMessageNeeded(true, function() {
    assert.strictEqual(rule.guard(ctx), true);
    rule.action(ctx);
  });

  assert.ok(ctx.issue.fields.InactivityNoticeSent > 1000);
  assert.strictEqual(ctx.issue.fields.State, ctx.State.Pending);
  assert.strictEqual(ctx.issue.fields.RemovalReason, ctx.RemovalReason.NeverUsed);
}

function testDelayedDeletionNoticeReceivesFullSevenDays() {
  const ctx = context({
    stageKey: 'SubjectToDeletion',
    graceEnds: 1000
  });

  const originalNow = Date.now;
  Date.now = function() { return 2000; };
  try {
    withMessageNeeded(true, function() {
      assert.strictEqual(rule.guard(ctx), true);
      rule.action(ctx);
    });
  } finally {
    Date.now = originalNow;
  }

  assert.strictEqual(ctx.issue.fields.GracePeriodEnds, 2000 + 7 * DAY);
}

function testCompletePendingReviewIsLeftUntouched() {
  const ctx = context({
    stageKey: 'SubjectToDeletion',
    graceEnds: 1788331200000
  });

  withMessageNeeded(false, function() {
    assert.strictEqual(rule.guard(ctx), false);
  });
}

testLegacyActivePendingReviewIsRetained();
testNeverUsedNoticeStartsWhenMessageCanBeSent();
testDelayedDeletionNoticeReceivesFullSevenDays();
testCompletePendingReviewIsLeftUntouched();

console.log('CMA lifecycle catch-up tests passed');
