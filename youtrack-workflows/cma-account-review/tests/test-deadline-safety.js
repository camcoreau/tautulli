const assert = require('assert');
const fs = require('fs');
const Module = require('module');
const path = require('path');

const DAY = 24 * 60 * 60 * 1000;
let deliveredAt = 0;
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === '@jetbrains/youtrack-scripting-api/entities') {
    return {
      Issue: {onSchedule: function(rule) { return rule; }},
      EnumField: {fieldType: {}},
      Field: {dateType: {}, dateTimeType: {}}
    };
  }
  if (request === '@jetbrains/youtrack-scripting-api/date-time') {
    return {
      after: function(value, period) {
        assert.ok(period === '1d' || period === '6d' || period === '7d');
        const days = period === '1d' ? 1 : (period === '6d' ? 6 : 7);
        return value + days * DAY;
      },
      format: function(value, pattern, timeZone) {
        assert.strictEqual(pattern, 'yyyy-MM-dd');
        assert.strictEqual(timeZone, 'Australia/Melbourne');
        return String(Math.floor(value / DAY)).padStart(8, '0');
      }
    };
  }
  if (request === './communications') {
    return {
      currentMessageDeliveredAt: function() { return deliveredAt; },
      hasFreshAudit: function(issue, afterTimestamp) {
        const confirmedAt = issue.fields.AccountAuditConfirmedAt || 0;
        const now = Date.now();
        return confirmedAt > afterTimestamp &&
          confirmedAt <= now &&
          now - confirmedAt < DAY;
      }
    };
  }
  return originalLoad(request, parent, isMain);
};

const advanceNotice = require('../notice-escalation').advanceIfReady;
const advanceDeadline = require('../deadline-transitions').advanceIfReady;
Module._load = originalLoad;

function context(stageKey, options) {
  options = options || {};
  const ReviewStage = {
    InactivityNotice: {name: 'Inactivity Notice'},
    SubjectToDeletion: {name: 'Subject to Deletion'},
    FinalReminder: {name: 'Final Reminder'},
    RemovalDue: {name: 'Removal Due'},
    AccessRetained: {name: 'Access Retained'}
  };
  const Outcome = {Pending: {name: 'Pending'}};
  const currentStage = ReviewStage[stageKey];
  const fields = {
    ReviewStage: currentStage,
    GracePeriodEnds: options.graceEnds || null,
    InactivityNoticeSent: options.noticeSent || null,
    LastStreamed: options.lastStreamed || null,
    AccountAuditConfirmedAt: options.auditConfirmedAt || null,
    Outcome: Outcome.Pending,
    is: function(field, value) {
      if (field === ReviewStage) return currentStage === value;
      if (field === Outcome) return value === Outcome.Pending;
      return false;
    }
  };
  return {
    issue: {fields: fields},
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

function testInactivityCannotEscalateBeforeThePublicNoticeExists() {
  const ctx = context('InactivityNotice', {noticeSent: DAY});
  deliveredAt = 0;
  withNow(20 * DAY, function() {
    assert.strictEqual(advanceNotice(ctx), false);
  });
}

function testInactivityEscalatesSevenDaysAfterActualDelivery() {
  const ctx = context('InactivityNotice', {
    noticeSent: DAY,
    auditConfirmedAt: 8 * DAY + 1
  });
  deliveredAt = 2 * DAY;
  withNow(9 * DAY, function() {
    assert.strictEqual(advanceNotice(ctx), true);
  });
  assert.strictEqual(ctx.issue.fields.ReviewStage, ctx.ReviewStage.SubjectToDeletion);
}

function testLateDayInactivityNoticeGetsTheFullSevenDays() {
  deliveredAt = DAY - 5 * 60 * 1000;
  const ctx = context('InactivityNotice', {
    noticeSent: DAY,
    auditConfirmedAt: deliveredAt + 6 * DAY + 12 * 60 * 60 * 1000
  });
  withNow(deliveredAt + 7 * DAY - 1, function() {
    assert.strictEqual(advanceNotice(ctx), false);
  });
  withNow(deliveredAt + 7 * DAY, function() {
    assert.strictEqual(advanceNotice(ctx), true);
  });
}

function testStreamingSinceActualNoticeRetainsAccess() {
  const ctx = context('InactivityNotice', {
    noticeSent: DAY,
    lastStreamed: 3 * DAY,
    auditConfirmedAt: 8 * DAY + 1
  });
  deliveredAt = 2 * DAY;
  withNow(9 * DAY, function() {
    assert.strictEqual(advanceNotice(ctx), true);
  });
  assert.strictEqual(ctx.issue.fields.ReviewStage, ctx.ReviewStage.AccessRetained);
}

function testDeletionDeadlineCannotAdvanceBeforeCurrentNoticeDelivery() {
  const ctx = context('SubjectToDeletion', {graceEnds: 11 * DAY});
  deliveredAt = 0;
  withNow(10 * DAY, function() {
    assert.strictEqual(advanceDeadline(ctx), false);
  });
}

function testDeletionDeadlineTransitionsAfterDelivery() {
  const reminder = context('SubjectToDeletion', {
    graceEnds: 11 * DAY,
    auditConfirmedAt: 9 * DAY + 1
  });
  deliveredAt = 4 * DAY;
  withNow(10 * DAY, function() {
    assert.strictEqual(advanceDeadline(reminder), true);
  });
  assert.strictEqual(reminder.issue.fields.ReviewStage, reminder.ReviewStage.FinalReminder);

  const removal = context('FinalReminder', {
    graceEnds: 11 * DAY,
    auditConfirmedAt: 10 * DAY + 1
  });
  deliveredAt = 10 * DAY;
  withNow(11 * DAY, function() {
    assert.strictEqual(advanceDeadline(removal), true);
  });
  assert.strictEqual(removal.issue.fields.ReviewStage, removal.ReviewStage.RemovalDue);
}

function testDeletionStagesCannotAdvanceBeforeTheirFullIntervals() {
  deliveredAt = DAY - 5 * 60 * 1000;
  const subject = context('SubjectToDeletion', {
    graceEnds: 100 * DAY,
    auditConfirmedAt: deliveredAt + 5 * DAY + 12 * 60 * 60 * 1000
  });
  withNow(deliveredAt + 6 * DAY - 1, function() {
    assert.strictEqual(advanceDeadline(subject), false);
  });
  withNow(deliveredAt + 6 * DAY, function() {
    assert.strictEqual(advanceDeadline(subject), true);
  });

  const finalReminder = context('FinalReminder', {
    graceEnds: 100 * DAY,
    auditConfirmedAt: deliveredAt + 12 * 60 * 60 * 1000
  });
  withNow(deliveredAt + DAY - 1, function() {
    assert.strictEqual(advanceDeadline(finalReminder), false);
  });
  withNow(deliveredAt + DAY, function() {
    assert.strictEqual(advanceDeadline(finalReminder), true);
  });
}

function testMatureStagesPauseWithoutCurrentAuditEvidence() {
  deliveredAt = 2 * DAY;
  const missing = context('InactivityNotice', {
    noticeSent: DAY,
    auditConfirmedAt: null
  });
  const stale = context('InactivityNotice', {
    noticeSent: DAY,
    auditConfirmedAt: 8 * DAY
  });
  const future = context('InactivityNotice', {
    noticeSent: DAY,
    auditConfirmedAt: 9 * DAY + 1
  });
  const notAfterDelivery = context('InactivityNotice', {
    noticeSent: DAY,
    auditConfirmedAt: deliveredAt
  });

  withNow(9 * DAY, function() {
    assert.strictEqual(advanceNotice(missing), false);
    assert.strictEqual(advanceNotice(stale), false);
    assert.strictEqual(advanceNotice(future), false);
    assert.strictEqual(advanceNotice(notAfterDelivery), false);
  });
}

function testEscalationsHaveNoScheduledFallback() {
  ['notice-escalation.js', 'deadline-transitions.js'].forEach(function(name) {
    const source = fs.readFileSync(path.join(__dirname, '..', name), 'utf8');
    assert.strictEqual(source.includes('onSchedule'), false, name);
    assert.strictEqual(source.includes('cron:'), false, name);
    assert.strictEqual(source.includes('advanceIfReady'), true, name);
  });
  const bridgeSource = fs.readFileSync(
    path.join(__dirname, '..', 'audit-freshness-bridge.js'),
    'utf8'
  );
  assert.strictEqual(bridgeSource.includes('noticeEscalation.advanceIfReady(ctx)'), true);
  assert.strictEqual(bridgeSource.includes('deadlineTransitions.advanceIfReady(ctx)'), true);
}

testInactivityCannotEscalateBeforeThePublicNoticeExists();
testInactivityEscalatesSevenDaysAfterActualDelivery();
testLateDayInactivityNoticeGetsTheFullSevenDays();
testStreamingSinceActualNoticeRetainsAccess();
testDeletionDeadlineCannotAdvanceBeforeCurrentNoticeDelivery();
testDeletionDeadlineTransitionsAfterDelivery();
testDeletionStagesCannotAdvanceBeforeTheirFullIntervals();
testMatureStagesPauseWithoutCurrentAuditEvidence();
testEscalationsHaveNoScheduledFallback();

console.log('CMA deadline safety tests passed');
