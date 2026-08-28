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
      Field: {dateType: {}, dateTimeType: {}},
      State: {fieldType: {}},
      User: {fieldType: {}}
    };
  }
  if (request === '@jetbrains/youtrack-scripting-api/date-time') {
    return {
      after: function(value, period) {
        if (period === '7d') return value + 7 * DAY;
        if (period === '6d') return value + 6 * DAY;
        if (period === '1d') return value + DAY;
        throw new Error('unexpected period ' + period);
      },
      format: function(value) {
        return new Date(value).toISOString().slice(0, 10);
      }
    };
  }
  return originalLoad(request, parent, isMain);
};

const communications = require('../communications');
const lifecycleCatchUp = require('../lifecycle-catchup').rule;
const communicationCatchUp = require('../communication-catchup').rule;
const auditFreshnessBridge = require('../audit-freshness-bridge').rule;
const advanceDeadline = require('../deadline-transitions').advanceIfReady;
const advanceNotice = require('../notice-escalation').advanceIfReady;
const stageCommunications = require('../stage-communications').rule;
Module._load = originalLoad;

const values = {
  ReviewStage: {
    InactivityNotice: {name: 'Inactivity Notice'},
    SubjectToDeletion: {name: 'Subject to Deletion'},
    FinalReminder: {name: 'Final Reminder'},
    RemovalDue: {name: 'Removal Due'},
    AccessRemoved: {name: 'Access Removed'},
    AccessRetained: {name: 'Access Retained'},
    Exempt: {name: 'Exempt'}
  },
  AccountStatus: {
    Active: {name: 'Active'},
    Inactive: {name: 'Inactive'},
    NeverUsed: {name: 'Never Used'}
  },
  Outcome: {
    Pending: {name: 'Pending'},
    Retained: {name: 'Retained'},
    Removed: {name: 'Removed'},
    Exempt: {name: 'Exempt'}
  },
  RemovalReason: {
    Inactivity: {name: 'Inactivity'},
    NeverUsed: {name: 'Never Used'}
  },
  State: {
    New: {name: 'New'},
    Pending: {name: 'Pending'},
    Solved: {name: 'Solved'}
  }
};

function alias(fields, persisted, apiName, bracketName, key) {
  Array.from(new Set([apiName, bracketName])).forEach(function(name) {
    Object.defineProperty(fields, name, {
      enumerable: true,
      get: function() { return persisted[key]; },
      set: function(value) { persisted[key] = value; }
    });
  });
}

function makeFields(persisted) {
  const fields = {};
  alias(fields, persisted, 'ReviewStage', 'Review Stage', 'reviewStage');
  alias(fields, persisted, 'AccountStatus', 'Account Status', 'accountStatus');
  alias(fields, persisted, 'InactivityNoticeSent', 'Inactivity Notice Sent', 'noticeSent');
  alias(fields, persisted, 'GracePeriodEnds', 'Grace Period Ends', 'graceEnds');
  alias(fields, persisted, 'Outcome', 'Outcome', 'outcome');
  alias(fields, persisted, 'RemovalReason', 'Removal Reason', 'removalReason');
  alias(fields, persisted, 'RemovalCompleted', 'Removal Completed', 'removalCompleted');
  alias(fields, persisted, 'State', 'State', 'state');
  alias(fields, persisted, 'LastStreamed', 'Last Streamed', 'lastStreamed');
  alias(
    fields,
    persisted,
    'AccountAuditConfirmedAt',
    'Account Audit Confirmed At',
    'auditConfirmedAt'
  );
  fields.is = function(field, value) {
    if (field === values.ReviewStage) return persisted.reviewStage === value;
    if (field === values.AccountStatus) return persisted.accountStatus === value;
    if (field === values.Outcome) return persisted.outcome === value;
    if (field === values.State) return persisted.state === value;
    return false;
  };
  return fields;
}

function visibility() {
  return {
    clear: function() { this.cleared = true; },
    isEmpty: function() { return true; }
  };
}

function makeIssue(persisted) {
  const issue = {
    id: persisted.id,
    fields: makeFields(persisted),
    extensionProperties: persisted.extensionProperties,
    comments: persisted.comments,
    addComment: function(text) {
      const comment = {
        text: text,
        created: Date.now(),
        deleted: false,
        permittedUsers: visibility(),
        permittedGroups: visibility()
      };
      persisted.comments.push(comment);
      persisted.added.push(comment);
      return comment;
    }
  };
  Object.defineProperty(issue, 'reporter', {
    get: function() { return persisted.reporter; },
    set: function(value) { persisted.reporter = value; }
  });
  return issue;
}

function context(issue) {
  return {
    issue: issue,
    ReviewStage: values.ReviewStage,
    AccountStatus: values.AccountStatus,
    Outcome: values.Outcome,
    RemovalReason: values.RemovalReason,
    State: values.State
  };
}

function historicalIssue(stage, options) {
  options = options || {};
  return {
    id: options.id || 'CMA-HISTORICAL',
    reporter: {login: 'member'},
    reviewStage: stage ? values.ReviewStage[stage] : null,
    accountStatus: values.AccountStatus.Inactive,
    outcome: values.Outcome.Pending,
    state: values.State.New,
    removalReason: null,
    noticeSent: options.noticeSent || null,
    graceEnds: options.graceEnds || null,
    removalCompleted: null,
    lastStreamed: null,
    auditConfirmedAt: options.auditConfirmedAt || null,
    extensionProperties: {},
    comments: options.comments || [],
    added: []
  };
}

function testFormerHourlyIncidentSequenceCannotRepeatOrAdvance() {
  const originalNow = Date.now;
  const marker = Date.UTC(2026, 7, 27, 13, 0, 0);
  const existingComment = {
    text: communications.TEMPLATES.inactivity,
    created: Date.UTC(2026, 7, 27, 12, 36, 0),
    deleted: false,
    permittedUsers: visibility(),
    permittedGroups: visibility()
  };
  const persisted = historicalIssue('InactivityNotice', {
    noticeSent: marker,
    comments: [existingComment]
  });

  try {
    for (let hour = 0; hour < 48; hour += 1) {
      Date.now = function() { return marker + hour * 60 * 60 * 1000; };
      let ctx = context(makeIssue(persisted));
      if (lifecycleCatchUp.guard(ctx)) lifecycleCatchUp.action(ctx);

      ctx = context(makeIssue(persisted));
      assert.strictEqual(advanceDeadline(ctx), false);

      ctx = context(makeIssue(persisted));
      if (communicationCatchUp.guard(ctx)) communicationCatchUp.action(ctx);

      ctx = context(makeIssue(persisted));
      assert.strictEqual(advanceNotice(ctx), false);
    }
  } finally {
    Date.now = originalNow;
  }

  assert.strictEqual(persisted.comments.length, 1);
  assert.strictEqual(persisted.added.length, 0);
  assert.strictEqual(persisted.noticeSent, marker);
  assert.strictEqual(persisted.state, values.State.Pending);
  assert.strictEqual(persisted.removalReason, values.RemovalReason.Inactivity);
  assert.strictEqual(communications.currentMessageDeliveredAt(makeIssue(persisted)), 0);
}

function testHistoricalStaleGraceDateCannotAdvance() {
  const originalNow = Date.now;
  const base = Date.UTC(2026, 7, 27, 13, 0, 0);
  const staleGrace = base - DAY;
  const persisted = historicalIssue('SubjectToDeletion', {graceEnds: staleGrace});

  try {
    for (let hour = 0; hour < 24; hour += 1) {
      Date.now = function() { return base + hour * 60 * 60 * 1000; };
      let ctx = context(makeIssue(persisted));
      if (lifecycleCatchUp.guard(ctx)) lifecycleCatchUp.action(ctx);

      ctx = context(makeIssue(persisted));
      assert.strictEqual(advanceDeadline(ctx), false);

      ctx = context(makeIssue(persisted));
      if (communicationCatchUp.guard(ctx)) communicationCatchUp.action(ctx);
    }
  } finally {
    Date.now = originalNow;
  }

  assert.strictEqual(persisted.reviewStage, values.ReviewStage.SubjectToDeletion);
  assert.strictEqual(persisted.graceEnds, staleGrace);
  assert.strictEqual(persisted.added.length, 0);
}

function testMissingReporterKeepsTimerBlockedThenReceivesFullPeriod() {
  const originalNow = Date.now;
  const base = Date.UTC(2026, 7, 28, 10, 0, 0);
  const persisted = historicalIssue('SubjectToDeletion', {
    id: 'CMA-NEW-CYCLE',
    graceEnds: base + 7 * DAY,
    auditConfirmedAt: base
  });
  persisted.reporter = null;
  persisted.extensionProperties.cmaAccountAuditConfirmedAt = base;

  try {
    Date.now = function() { return base; };
    const issue = makeIssue(persisted);
    assert.strictEqual(communications.sendForStageChange(issue), false);
    const originalGrace = persisted.graceEnds;

    for (let hour = 1; hour <= 3; hour += 1) {
      Date.now = function() { return base + hour * 60 * 60 * 1000; };
      let ctx = context(makeIssue(persisted));
      assert.strictEqual(advanceDeadline(ctx), false);
      ctx = context(makeIssue(persisted));
      assert.strictEqual(communicationCatchUp.guard(ctx), false);
      communicationCatchUp.action(ctx);
      assert.strictEqual(persisted.graceEnds, originalGrace);
      assert.strictEqual(persisted.added.length, 0);
    }

    const deliveredAt = base + 4 * 60 * 60 * 1000;
    Date.now = function() { return deliveredAt; };
    persisted.reporter = {login: 'member'};
    persisted.auditConfirmedAt = deliveredAt;
    const ctx = context(makeIssue(persisted));
    auditFreshnessBridge.action(ctx);
    assert.strictEqual(persisted.added.length, 1);
    assert.strictEqual(persisted.graceEnds, deliveredAt + 7 * DAY);

    for (let run = 0; run < 48; run += 1) {
      assert.strictEqual(communicationCatchUp.guard(context(makeIssue(persisted))), false);
    }
  } finally {
    Date.now = originalNow;
  }
}

function testFailedAuditsPauseMatureReviewUntilFreshEvidenceReturns() {
  const originalNow = Date.now;
  const base = Date.UTC(2026, 7, 1, 10, 0, 0);
  const persisted = historicalIssue('InactivityNotice', {
    id: 'CMA-FRESHNESS-GATE',
    auditConfirmedAt: base
  });
  persisted.extensionProperties.cmaAccountAuditConfirmedAt = base;

  try {
    Date.now = function() { return base; };
    assert.strictEqual(communications.sendForStageChange(makeIssue(persisted)), true);
    assert.strictEqual(persisted.added.length, 1);

    for (let hour = 0; hour < 48; hour += 1) {
      const now = base + 7 * DAY + hour * 60 * 60 * 1000;
      Date.now = function() { return now; };
      assert.strictEqual(advanceNotice(context(makeIssue(persisted))), false);
      assert.strictEqual(persisted.reviewStage, values.ReviewStage.InactivityNotice);
      assert.strictEqual(persisted.added.length, 1);
    }

    const recoveredAt = base + 9 * DAY;
    Date.now = function() { return recoveredAt; };
    persisted.auditConfirmedAt = recoveredAt;
    let ctx = context(makeIssue(persisted));
    auditFreshnessBridge.action(ctx);
    stageCommunications.action(context(makeIssue(persisted)));
    assert.strictEqual(persisted.reviewStage, values.ReviewStage.SubjectToDeletion);
    assert.strictEqual(persisted.added.length, 2);
  } finally {
    Date.now = originalNow;
  }
}

function testLegacyActiveRepairCannotCreateAnEndUserMessage() {
  const persisted = historicalIssue(null, {id: 'CMA-LEGACY-ACTIVE'});
  persisted.accountStatus = values.AccountStatus.Active;
  let ctx = context(makeIssue(persisted));
  assert.strictEqual(lifecycleCatchUp.guard(ctx), true);
  lifecycleCatchUp.action(ctx);
  assert.strictEqual(persisted.reviewStage, values.ReviewStage.AccessRetained);

  ctx = context(makeIssue(persisted));
  stageCommunications.action(ctx);
  assert.strictEqual(persisted.added.length, 0);
  assert.strictEqual(
    persisted.extensionProperties.cmaObservedReviewStage,
    'Access Retained'
  );
  assert.strictEqual(communications.currentMessageDeliveredAt(makeIssue(persisted)), 0);
  assert.strictEqual(communicationCatchUp.guard(context(makeIssue(persisted))), false);
}

testFormerHourlyIncidentSequenceCannotRepeatOrAdvance();
testHistoricalStaleGraceDateCannotAdvance();
testMissingReporterKeepsTimerBlockedThenReceivesFullPeriod();
testFailedAuditsPauseMatureReviewUntilFreshEvidenceReturns();
testLegacyActiveRepairCannotCreateAnEndUserMessage();

console.log('CMA production-incident regression tests passed');
