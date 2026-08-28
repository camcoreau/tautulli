const assert = require('assert');
const Module = require('module');

const DAY = 24 * 60 * 60 * 1000;
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === '@jetbrains/youtrack-scripting-api/entities') {
    return {
      Issue: {onChange: function(rule) { return rule; }},
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
      },
      format: function(value) {
        return new Date(value).toISOString().slice(0, 10);
      }
    };
  }
  return originalLoad(request, parent, isMain);
};

const communications = require('../communications');
const bridge = require('../audit-freshness-bridge').rule;
Module._load = originalLoad;

const ReviewStage = {
  InactivityNotice: {name: 'Inactivity Notice'},
  SubjectToDeletion: {name: 'Subject to Deletion'},
  FinalReminder: {name: 'Final Reminder'},
  RemovalDue: {name: 'Removal Due'},
  AccessRemoved: {name: 'Access Removed'},
  AccessRetained: {name: 'Access Retained'}
};
const Outcome = {Pending: {name: 'Pending'}};
const AccountAuditConfirmedAt = {};

function visibility() {
  return {clear: function() { this.cleared = true; }};
}

function issue(options) {
  options = options || {};
  const persisted = {
    stage: ReviewStage[options.stage || 'RemovalDue'],
    outcome: Outcome.Pending,
    pulse: options.pulse || null,
    noticeSent: null,
    graceEnds: null,
    lastStreamed: options.lastStreamed || null
  };
  const fields = {
    get ReviewStage() { return persisted.stage; },
    set ReviewStage(value) { persisted.stage = value; },
    get Outcome() { return persisted.outcome; },
    get AccountAuditConfirmedAt() { return persisted.pulse; },
    set AccountAuditConfirmedAt(value) { persisted.pulse = value; },
    get LastStreamed() { return persisted.lastStreamed; },
    get InactivityNoticeSent() { return persisted.noticeSent; },
    set InactivityNoticeSent(value) { persisted.noticeSent = value; },
    get GracePeriodEnds() { return persisted.graceEnds; },
    set GracePeriodEnds(value) { persisted.graceEnds = value; },
    isChanged: function(field) {
      return field === AccountAuditConfirmedAt && persisted.pulse !== null;
    },
    is: function(field, value) {
      if (field === ReviewStage) return persisted.stage === value;
      if (field === Outcome) return persisted.outcome === value;
      return false;
    }
  };
  Object.defineProperty(fields, 'Review Stage', {
    get: function() { return persisted.stage; },
    set: function(value) { persisted.stage = value; }
  });
  Object.defineProperty(fields, 'Account Status', {
    get: function() { return {name: options.accountStatus || 'Inactive'}; }
  });
  Object.defineProperty(fields, 'Account Audit Confirmed At', {
    get: function() { return persisted.pulse; },
    set: function(value) { persisted.pulse = value; }
  });
  Object.defineProperty(fields, 'Inactivity Notice Sent', {
    get: function() { return persisted.noticeSent; },
    set: function(value) { persisted.noticeSent = value; }
  });
  Object.defineProperty(fields, 'Grace Period Ends', {
    get: function() { return persisted.graceEnds; },
    set: function(value) { persisted.graceEnds = value; }
  });

  const current = {
    id: options.id || 'CMA-BRIDGE',
    reporter: options.reporter === undefined ? {login: 'member'} : options.reporter,
    fields: fields,
    extensionProperties: Object.assign({}, options.extensionProperties || {}),
    comments: [],
    added: [],
    addComment: function(text) {
      const comment = {
        text: text,
        created: Date.now(),
        permittedUsers: visibility(),
        permittedGroups: visibility()
      };
      this.comments.push(comment);
      this.added.push(comment);
      return comment;
    }
  };
  return {current: current, persisted: persisted};
}

function context(current) {
  return {
    issue: current,
    AccountAuditConfirmedAt: AccountAuditConfirmedAt,
    ReviewStage: ReviewStage,
    Outcome: Outcome
  };
}

function withNow(value, callback) {
  const originalNow = Date.now;
  Date.now = function() { return value; };
  try {
    callback();
  } finally {
    Date.now = originalNow;
  }
}

function testPulseIsStoredPrivatelyAndCleared() {
  const now = 10 * DAY;
  withNow(now, function() {
    const scenario = issue({pulse: now});
    const ctx = context(scenario.current);
    assert.strictEqual(bridge.guard(ctx), true);
    bridge.action(ctx);
    assert.strictEqual(scenario.persisted.pulse, null);
    assert.strictEqual(
      scenario.current.extensionProperties.cmaAccountAuditConfirmedAt,
      now
    );
    assert.strictEqual(scenario.current.added.length, 0);
    assert.strictEqual(bridge.guard(ctx), false);
  });
}

function testPulseCompletesOnePreparedMessageAndAlignsItsTimer() {
  const now = 20 * DAY;
  withNow(now, function() {
    const scenario = issue({stage: 'InactivityNotice', pulse: now});
    assert.strictEqual(communications.sendForStageChange(scenario.current), false);
    assert.strictEqual(scenario.current.added.length, 0);

    bridge.action(context(scenario.current));
    assert.strictEqual(scenario.current.added.length, 1);
    assert.strictEqual(scenario.persisted.noticeSent, now);
    assert.strictEqual(communications.sendCurrentMessage(scenario.current), false);
  });
}

function testMatureNoticeAdvancesOnlyInsideSuccessfulPulse() {
  const deliveredAt = 30 * DAY;
  const now = deliveredAt + 7 * DAY;
  const token = 'v1:1:inactivity';
  withNow(now, function() {
    const scenario = issue({
      stage: 'InactivityNotice',
      pulse: now,
      extensionProperties: {
        cmaMessageStateVersion: 1,
        cmaMessageSequence: 1,
        cmaObservedReviewStage: 'Inactivity Notice',
        cmaPendingMessageKey: 'inactivity',
        cmaPendingMessageToken: token,
        cmaDeliveredMessageToken: token,
        cmaDeliveredMessageAt: deliveredAt,
        cmaAccountAuditConfirmedAt: deliveredAt
      }
    });

    bridge.action(context(scenario.current));
    assert.strictEqual(scenario.persisted.stage, ReviewStage.SubjectToDeletion);
    assert.strictEqual(communications.sendForStageChange(scenario.current), true);
    assert.strictEqual(scenario.current.added.length, 1);
  });
}

function testInvalidPulseFailsBeforeChangingPrivateState() {
  const now = 40 * DAY;
  withNow(now, function() {
    [now + 1, now - 5 * 60 * 1000 - 1, 0.5].forEach(function(pulse) {
      const scenario = issue({pulse: pulse});
      assert.throws(function() {
        bridge.action(context(scenario.current));
      }, /timestamp is invalid/);
      assert.strictEqual(
        scenario.current.extensionProperties.cmaAccountAuditConfirmedAt,
        undefined
      );
      assert.strictEqual(scenario.current.added.length, 0);
    });
  });
}

testPulseIsStoredPrivatelyAndCleared();
testPulseCompletesOnePreparedMessageAndAlignsItsTimer();
testMatureNoticeAdvancesOnlyInsideSuccessfulPulse();
testInvalidPulseFailsBeforeChangingPrivateState();

console.log('CMA audit freshness bridge tests passed');
