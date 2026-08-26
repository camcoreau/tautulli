const assert = require('assert');
const communications = require('../communications');

function emptyVisibility() {
  return {
    cleared: false,
    clear: function() {
      this.cleared = true;
    }
  };
}

function issue(options) {
  const comments = (options.comments || []).slice();
  comments.forEach(function(comment) {
    if (comment.deleted === undefined) {
      comment.deleted = false;
    }
  });
  comments.forEach = Array.prototype.forEach.bind(comments);

  return {
    id: 'CMA-1',
    reporter: options.reporter === undefined ? {login: 'member'} : options.reporter,
    fields: {
      'Review Stage': {name: options.stage},
      'Account Status': {name: options.accountStatus || 'Inactive'},
      'Inactivity Notice Sent': options.noticeSent || 1000
    },
    comments: comments,
    added: [],
    addComment: function(text) {
      const comment = {
        text: text,
        created: options.now || 2000,
        deleted: false,
        permittedUsers: emptyVisibility(),
        permittedGroups: emptyVisibility()
      };
      comments.push(comment);
      this.added.push(comment);
      return comment;
    }
  };
}

function testInitialTemplateSelection() {
  assert.strictEqual(
    communications.messageKey(issue({stage: 'Inactivity Notice'})),
    'inactivity'
  );
  assert.strictEqual(
    communications.messageKey(issue({
      stage: 'Inactivity Notice',
      accountStatus: 'Never Used'
    })),
    'neverUsed'
  );
}

function testEveryAutomatedStageHasTheApprovedTemplate() {
  const expected = {
    'Subject to Deletion': 'subjectToDeletion',
    'Final Reminder': 'finalReminder',
    'Access Removed': 'accessRemoved',
    'Access Retained': 'accessRetained'
  };

  Object.keys(expected).forEach(function(stage) {
    assert.strictEqual(communications.messageKey(issue({stage: stage})), expected[stage]);
  });
  assert.strictEqual(communications.messageKey(issue({stage: 'Removal Due'})), null);
  assert.strictEqual(communications.messageKey(issue({stage: 'Exempt'})), null);
}

function testPublicMessageIsSentOncePerCycle() {
  const current = issue({stage: 'Subject to Deletion', noticeSent: 1000, now: 2000});

  assert.strictEqual(communications.sendCurrentMessage(current), true);
  assert.strictEqual(current.added.length, 1);
  assert.strictEqual(current.added[0].permittedUsers.cleared, true);
  assert.strictEqual(current.added[0].permittedGroups.cleared, true);
  assert.strictEqual(communications.sendCurrentMessage(current), false);
  assert.strictEqual(current.added.length, 1);
}

function testNewReviewCycleCanSendAgain() {
  const oldText = communications.TEMPLATES.inactivity;
  const current = issue({
    stage: 'Inactivity Notice',
    noticeSent: 5000,
    now: 6000,
    comments: [{text: oldText, created: 2000}]
  });

  assert.strictEqual(communications.sendCurrentMessage(current), true);
  assert.strictEqual(current.added.length, 1);
}

function testMissingReporterFailsClosed() {
  const current = issue({stage: 'Final Reminder', reporter: null});

  assert.strictEqual(communications.sendCurrentMessage(current), false);
  assert.strictEqual(current.added.length, 0);
}

function testApprovedMessagesKeepSafetyWording() {
  assert.ok(communications.TEMPLATES.subjectToDeletion.includes('within the next **7 days**'));
  assert.ok(communications.TEMPLATES.accessRemoved.includes('personal Plex account has **not** been deleted'));
  assert.ok(communications.TEMPLATES.accessRetained.includes('your access will remain active'));
}

testInitialTemplateSelection();
testEveryAutomatedStageHasTheApprovedTemplate();
testPublicMessageIsSentOncePerCycle();
testNewReviewCycleCanSendAgain();
testMissingReporterFailsClosed();
testApprovedMessagesKeepSafetyWording();

console.log('CMA communications tests passed');
