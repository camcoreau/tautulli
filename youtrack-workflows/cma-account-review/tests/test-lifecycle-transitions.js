const assert = require('assert');
const Module = require('module');

const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === '@jetbrains/youtrack-scripting-api/entities') {
    return {
      Issue: {onChange: function(rule) { return rule; }},
      EnumField: {fieldType: {}},
      Field: {dateType: {}},
      User: {fieldType: {}},
      State: {fieldType: {}}
    };
  }
  if (request === '@jetbrains/youtrack-scripting-api/date-time') {
    return {
      after: function(value) { return value + 7 * 24 * 60 * 60 * 1000; },
      format: function() { return '2026-09-02'; },
      parse: function() { return 1788331200000; }
    };
  }
  return originalLoad(request, parent, isMain);
};

const rule = require('../lifecycle-transitions').rule;
Module._load = originalLoad;

function context(stageKey, accountStatusKey) {
  const ReviewStage = {
    InactivityNotice: {name: 'Inactivity Notice'},
    SubjectToDeletion: {name: 'Subject to Deletion'},
    AccessRetained: {name: 'Access Retained'},
    AccessRemoved: {name: 'Access Removed'},
    Exempt: {name: 'Exempt'}
  };
  const AccountStatus = {
    NeverUsed: {name: 'Never Used'},
    Inactive: {name: 'Inactive'}
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
    Pending: {name: 'Pending'},
    Solved: {name: 'Solved'}
  };
  const reviewer = {login: 'jayden'};
  const currentStage = ReviewStage[stageKey];
  const accountStatus = AccountStatus[accountStatusKey || 'Inactive'];
  const fields = {
    isChanged: function(field) { return field === ReviewStage; },
    becomes: function(field, value) {
      return field === ReviewStage && currentStage === value;
    },
    is: function(field, value) {
      return field === AccountStatus && accountStatus === value;
    }
  };

  return {
    issue: {
      fields: fields,
      project: {
        findFieldByName: function(name) {
          assert.strictEqual(name, 'Reviewed By');
          return {
            findValueByLogin: function(login) {
              return login === reviewer.login ? reviewer : null;
            }
          };
        }
      }
    },
    currentUser: reviewer,
    ReviewStage: ReviewStage,
    AccountStatus: AccountStatus,
    Outcome: Outcome,
    RemovalReason: RemovalReason,
    ReviewedBy: {name: 'Reviewed By'},
    State: State
  };
}

function testNeverUsedReviewIsInitializedAutomatically() {
  const ctx = context('InactivityNotice', 'NeverUsed');

  assert.strictEqual(rule.guard(ctx), true);
  rule.action(ctx);

  assert.strictEqual(ctx.issue.fields.Outcome, ctx.Outcome.Pending);
  assert.strictEqual(ctx.issue.fields.State, ctx.State.Pending);
  assert.strictEqual(ctx.issue.fields.RemovalReason, ctx.RemovalReason.NeverUsed);
  assert.ok(ctx.issue.fields.InactivityNoticeSent > 0);
}

function testInactiveReviewGetsInactivityReason() {
  const ctx = context('InactivityNotice', 'Inactive');

  rule.action(ctx);

  assert.strictEqual(ctx.issue.fields.RemovalReason, ctx.RemovalReason.Inactivity);
}

function testConfirmedRemovalRecordsTheAdministrator() {
  const ctx = context('AccessRemoved');

  rule.action(ctx);

  assert.strictEqual(ctx.issue.fields.Outcome, ctx.Outcome.Removed);
  assert.strictEqual(ctx.issue.fields.State, ctx.State.Solved);
  assert.strictEqual(ctx.issue.fields.ReviewedBy, ctx.currentUser);
  assert.ok(ctx.issue.fields.RemovalCompleted > 0);
}

testNeverUsedReviewIsInitializedAutomatically();
testInactiveReviewGetsInactivityReason();
testConfirmedRemovalRecordsTheAdministrator();

console.log('CMA lifecycle transition tests passed');
