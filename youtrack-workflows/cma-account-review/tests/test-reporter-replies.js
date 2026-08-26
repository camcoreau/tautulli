const assert = require('assert');
const Module = require('module');

const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === '@jetbrains/youtrack-scripting-api/entities') {
    return {
      Issue: {onChange: function(rule) { return rule; }},
      EnumField: {fieldType: {} }
    };
  }
  return originalLoad(request, parent, isMain);
};

const rule = require('../reporter-replies').rule;
Module._load = originalLoad;

function collection(items) {
  const values = items || [];
  return {
    forEach: function(callback) { values.forEach(callback); },
    isNotEmpty: function() { return values.length > 0; }
  };
}

function publicComment(author) {
  return {
    author: author,
    permittedGroups: {isEmpty: function() { return true; }},
    permittedUsers: {isEmpty: function() { return true; }}
  };
}

function context(options) {
  const ReviewStage = {
    InactivityNotice: {name: 'Inactivity Notice'},
    SubjectToDeletion: {name: 'Subject to Deletion'},
    FinalReminder: {name: 'Final Reminder'},
    RemovalDue: {name: 'Removal Due'},
    AccessRetained: {name: 'Access Retained'}
  };
  const Outcome = {Pending: {name: 'Pending'}};
  const currentStage = ReviewStage[options.stageKey || 'InactivityNotice'];
  const issue = {
    reporter: {login: 'member'},
    comments: {added: collection(options.comments || [])},
    fields: {
      ReviewStage: currentStage,
      is: function(field, value) {
        if (field === ReviewStage) {
          return currentStage === value;
        }
        if (field === Outcome) {
          return options.pending !== false && value === Outcome.Pending;
        }
        return false;
      }
    }
  };

  return {issue: issue, ReviewStage: ReviewStage, Outcome: Outcome};
}

function testReporterReplyRetainsAtEveryOpenStage() {
  ['InactivityNotice', 'SubjectToDeletion', 'FinalReminder', 'RemovalDue'].forEach(function(key) {
    const ctx = context({
      stageKey: key,
      comments: [publicComment({login: 'member'})]
    });

    assert.strictEqual(rule.guard(ctx), true, key);
    rule.action(ctx);
    assert.strictEqual(ctx.issue.fields.ReviewStage, ctx.ReviewStage.AccessRetained);
  });
}

function testAgentCommentDoesNotRetain() {
  const ctx = context({
    stageKey: 'InactivityNotice',
    comments: [publicComment({login: 'camcore-automation'})]
  });

  assert.strictEqual(rule.guard(ctx), false);
}

function testSolvedOutcomeDoesNotRetain() {
  const ctx = context({
    stageKey: 'FinalReminder',
    pending: false,
    comments: [publicComment({login: 'member'})]
  });

  assert.strictEqual(rule.guard(ctx), false);
}

testReporterReplyRetainsAtEveryOpenStage();
testAgentCommentDoesNotRetain();
testSolvedOutcomeDoesNotRetain();

console.log('CMA reporter reply tests passed');
