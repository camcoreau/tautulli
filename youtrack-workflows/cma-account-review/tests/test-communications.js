const assert = require('assert');
const fs = require('fs');
const path = require('path');
const communications = require('../communications');

function emptyVisibility() {
  return {
    cleared: false,
    clear: function() {
      this.cleared = true;
    },
    isEmpty: function() {
      return true;
    }
  };
}

function issue(options) {
  options = options || {};
  const auditConfirmedAt = Object.prototype.hasOwnProperty.call(
    options,
    'auditConfirmedAt'
  ) ? options.auditConfirmedAt : Date.now();
  const comments = (options.comments || []).map(function(comment) {
    return Object.assign({deleted: false}, comment);
  });
  comments.forEach = Array.prototype.forEach.bind(comments);
  let failedAddsRemaining = options.failedAdds || 0;

  const current = {
    id: options.id || 'CMA-1',
    reporter: options.reporter === undefined ? {login: 'member'} : options.reporter,
    fields: {
      'Review Stage': {name: options.stage || 'Inactivity Notice'},
      'Account Status': {name: options.accountStatus || 'Inactive'},
      'Inactivity Notice Sent': options.noticeSent || null,
      'Grace Period Ends': options.graceEnds || null
    },
    comments: comments,
    added: [],
    addComment: function(text) {
      if (failedAddsRemaining > 0) {
        failedAddsRemaining -= 1;
        throw new Error('simulated comment failure');
      }
      const comment = {
        text: text,
        created: options.clock ? options.clock() : (options.now || 2000),
        deleted: false,
        permittedUsers: emptyVisibility(),
        permittedGroups: emptyVisibility()
      };
      comments.push(comment);
      this.added.push(comment);
      return comment;
    }
  };
  if (options.extensionPropertiesAvailable !== false) {
    current.extensionProperties = Object.assign({}, options.extensionProperties || {});
    if (auditConfirmedAt !== null && auditConfirmedAt !== undefined) {
      current.extensionProperties.cmaAccountAuditConfirmedAt = auditConfirmedAt;
    }
  }
  return current;
}

function setStage(current, stage, accountStatus) {
  current.fields['Review Stage'] = {name: stage};
  if (accountStatus) {
    current.fields['Account Status'] = {name: accountStatus};
  }
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

function testTemplateSelection() {
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

function testEveryMessageStageIsIdempotentAcrossRepeatedRecoveryRuns() {
  const scenarios = [
    {stage: 'Inactivity Notice', accountStatus: 'Inactive'},
    {stage: 'Inactivity Notice', accountStatus: 'Never Used'},
    {stage: 'Subject to Deletion'},
    {stage: 'Final Reminder'},
    {stage: 'Access Removed'},
    {stage: 'Access Retained'}
  ];

  scenarios.forEach(function(scenario) {
    const current = issue(scenario);
    assert.strictEqual(communications.sendForStageChange(current), true, scenario.stage);
    for (let run = 0; run < 48; run += 1) {
      assert.strictEqual(communications.needsCatchUp(current), false, scenario.stage);
      assert.strictEqual(communications.sendCurrentMessage(current), false, scenario.stage);
    }
    assert.strictEqual(current.added.length, 1, scenario.stage);
    assert.strictEqual(current.added[0].permittedUsers.cleared, true, scenario.stage);
    assert.strictEqual(current.added[0].permittedGroups.cleared, true, scenario.stage);
  });
}

function testDateOnlyMarkerCannotCauseARepeat() {
  const current = issue({
    stage: 'Inactivity Notice',
    noticeSent: 9999999999999,
    now: 1000
  });

  assert.strictEqual(communications.sendForStageChange(current), true);
  assert.strictEqual(communications.sendCurrentMessage(current), false);
  assert.strictEqual(current.added.length, 1);
}

function testHistoricalIssuesStayQuarantinedWithoutSendingOrStateWrites() {
  const historicalComments = [
    [],
    [{text: communications.TEMPLATES.inactivity, created: 1000}],
    [{text: communications.TEMPLATES.inactivity, created: 1000, internal: true}],
    [{text: 'Member quoted: ' + communications.TEMPLATES.inactivity, created: 1000}]
  ];

  historicalComments.forEach(function(comments) {
    const current = issue({
      stage: 'Inactivity Notice',
      noticeSent: 5000,
      comments: comments,
      auditConfirmedAt: null
    });

    for (let run = 0; run < 48; run += 1) {
      assert.strictEqual(communications.needsCatchUp(current), false);
      assert.strictEqual(communications.sendCurrentMessage(current), false);
    }
    assert.strictEqual(current.added.length, 0);
    assert.deepStrictEqual(current.extensionProperties, {});
    assert.strictEqual(communications.currentMessageDeliveredAt(current), 0);
  });
}

function testHistoricalTerminalStagesCannotBulkEmail() {
  ['Access Retained', 'Access Removed'].forEach(function(stage) {
    const current = issue({stage: stage, auditConfirmedAt: null});
    assert.strictEqual(communications.sendCurrentMessage(current), false, stage);
    assert.strictEqual(communications.needsCatchUp(current), false, stage);
    assert.strictEqual(current.added.length, 0, stage);
    assert.deepStrictEqual(current.extensionProperties, {}, stage);
  });
}

function testNewReviewCycleCanSendAfterHistoricalMigration() {
  const current = issue({stage: 'Inactivity Notice'});
  assert.strictEqual(communications.sendCurrentMessage(current), false);

  setStage(current, 'Removal Due');
  assert.strictEqual(communications.sendForStageChange(current), false);
  setStage(current, 'Inactivity Notice');
  assert.strictEqual(communications.sendForStageChange(current), true);
  assert.strictEqual(current.added.length, 1);
}

function testIntermediateNonMessageStageStillCreatesANewCycle() {
  const current = issue({stage: 'Inactivity Notice'});
  assert.strictEqual(communications.sendForStageChange(current), true);

  setStage(current, 'Removal Due');
  assert.strictEqual(communications.sendForStageChange(current), false);
  setStage(current, 'Inactivity Notice');
  assert.strictEqual(communications.sendForStageChange(current), true);
  assert.strictEqual(current.added.length, 2);
}

function testAccountSubtypeChangeDoesNotChangePendingTemplate() {
  const current = issue({
    stage: 'Inactivity Notice',
    accountStatus: 'Never Used',
    reporter: null
  });

  assert.strictEqual(communications.sendForStageChange(current), false);
  assert.strictEqual(communications.currentDeliveryKey(current), 'neverUsed');
  current.fields['Account Status'] = {name: 'Inactive'};
  current.reporter = {login: 'member'};
  assert.strictEqual(communications.sendCurrentMessage(current, true), true);
  assert.strictEqual(current.added[0].text, communications.TEMPLATES.neverUsed);
  assert.strictEqual(communications.sendCurrentMessage(current), false);
}

function testMissingReporterRetriesTheSameToken() {
  const current = issue({stage: 'Access Removed', reporter: null});

  assert.strictEqual(communications.sendForStageChange(current), false);
  const token = current.extensionProperties.cmaPendingMessageToken;
  assert.ok(token);
  assert.strictEqual(current.extensionProperties.cmaDeliveredMessageToken, undefined);

  current.reporter = {login: 'member'};
  assert.strictEqual(communications.sendCurrentMessage(current), true);
  assert.strictEqual(current.extensionProperties.cmaDeliveredMessageToken, token);
  assert.strictEqual(communications.sendCurrentMessage(current), false);
  assert.strictEqual(current.added.length, 1);
}

function testTelemetryMessageWaitsForFreshAudit() {
  const now = 10 * 24 * 60 * 60 * 1000;
  withNow(now, function() {
    const current = issue({stage: 'Inactivity Notice', auditConfirmedAt: null});

    assert.strictEqual(communications.sendForStageChange(current), false);
    assert.ok(current.extensionProperties.cmaPendingMessageToken);
    assert.strictEqual(communications.needsCatchUp(current), false);
    assert.strictEqual(current.added.length, 0);

    current.extensionProperties.cmaAccountAuditConfirmedAt = now;
    assert.strictEqual(communications.needsCatchUp(current), false);
    assert.strictEqual(communications.sendCurrentMessage(current), false);
    assert.strictEqual(communications.sendCurrentMessage(current, true), true);
    assert.strictEqual(communications.sendCurrentMessage(current), false);
    assert.strictEqual(current.added.length, 1);
  });
}

function testAuditFreshnessFailsClosedAtBoundaryAndForFutureValues() {
  const day = 24 * 60 * 60 * 1000;
  const now = 20 * day;
  withNow(now, function() {
    assert.strictEqual(
      communications.hasFreshAudit(issue({auditConfirmedAt: now - day}), 0),
      false
    );
    assert.strictEqual(
      communications.hasFreshAudit(issue({auditConfirmedAt: now + 1}), 0),
      false
    );
    assert.strictEqual(
      communications.hasFreshAudit(issue({auditConfirmedAt: now - day + 1}), 0),
      true
    );
    assert.strictEqual(
      communications.hasFreshAudit(
        issue({auditConfirmedAt: now - 1}),
        now - 1
      ),
      false
    );
  });
}

function testManualOutcomeMessageDoesNotRequireAuditTelemetry() {
  const current = issue({stage: 'Access Retained', auditConfirmedAt: null});
  assert.strictEqual(communications.sendForStageChange(current), true);
  assert.strictEqual(current.added.length, 1);
}

function testFailedCommentCreationPropagatesForTransactionRollback() {
  const current = issue({stage: 'Subject to Deletion', failedAdds: 1});

  assert.throws(function() {
    communications.sendForStageChange(current);
  }, /simulated comment failure/);
  assert.strictEqual(current.added.length, 0);
}

function testExactDeliveryTimestampIsPersisted() {
  const current = issue({stage: 'Final Reminder', now: 123456789});
  assert.strictEqual(communications.sendForStageChange(current), true);
  assert.strictEqual(communications.currentMessageDeliveredAt(current), 123456789);
}

function testPendingNewCycleCannotReuseAnOlderDeliveryTimestamp() {
  const current = issue({stage: 'Inactivity Notice', now: 1000});
  assert.strictEqual(communications.sendForStageChange(current), true);
  assert.strictEqual(communications.currentMessageDeliveredAt(current), 1000);

  current.reporter = null;
  setStage(current, 'Subject to Deletion');
  assert.strictEqual(communications.sendForStageChange(current), false);
  assert.strictEqual(communications.currentMessageDeliveredAt(current), 0);
}

function testStageMismatchCannotInventADelivery() {
  const current = issue({stage: 'Inactivity Notice'});
  assert.strictEqual(communications.sendForStageChange(current), true);
  const sequence = current.extensionProperties.cmaMessageSequence;

  setStage(current, 'Subject to Deletion');
  assert.strictEqual(communications.needsCatchUp(current), false);
  assert.strictEqual(communications.sendCurrentMessage(current), false);
  assert.strictEqual(current.extensionProperties.cmaMessageSequence, sequence);
  assert.strictEqual(current.added.length, 1);
}

function testInternalRepairCanSuppressAStageMessage() {
  const current = issue({stage: 'Access Retained'});
  communications.suppressStageMessage(current, 'Access Retained');
  assert.strictEqual(communications.sendForStageChange(current), false);
  assert.strictEqual(current.added.length, 0);
  assert.strictEqual(communications.needsCatchUp(current), false);
  assert.strictEqual(communications.currentMessageDeliveredAt(current), 0);
  assert.strictEqual(current.extensionProperties.cmaSuppressedReviewStage, '');
}

function testStaleRepairSuppressionCannotHideAnotherStage() {
  const current = issue({stage: 'Access Retained'});
  communications.suppressStageMessage(current, 'Access Retained');
  setStage(current, 'Inactivity Notice');
  assert.strictEqual(communications.sendForStageChange(current), true);
  assert.strictEqual(current.added.length, 1);
  assert.strictEqual(current.extensionProperties.cmaSuppressedReviewStage, '');
}

function testMissingExtensionStateFailsClosedBeforeAddingAComment() {
  const current = issue({
    stage: 'Inactivity Notice',
    extensionPropertiesAvailable: false
  });
  assert.throws(function() {
    communications.sendForStageChange(current);
  }, /delivery state is unavailable/);
  assert.strictEqual(current.added.length, 0);
}

function testApprovedMessagesKeepSafetyWording() {
  assert.ok(communications.TEMPLATES.subjectToDeletion.includes('within the next **7 days**'));
  assert.ok(communications.TEMPLATES.accessRemoved.includes('personal Plex account has **not** been deleted'));
  assert.ok(communications.TEMPLATES.accessRetained.includes('your access will remain active'));
}

function testImplementationDoesNotTrustDateFieldsOrHistoricalComments() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'communications.js'), 'utf8');
  const recovery = source.slice(
    source.indexOf('function prepareCatchUpDelivery'),
    source.indexOf('function sendPreparedMessage')
  );
  assert.ok(!source.includes("fields['Inactivity Notice Sent']"));
  assert.ok(!source.includes('issue.comments'));
  assert.ok(!recovery.includes('startDelivery'));
  assert.ok(!source.includes('migrateHistoricalState'));
  assert.ok(source.includes('cmaPendingMessageToken'));
  assert.ok(source.includes('cmaDeliveredMessageToken'));
}

testTemplateSelection();
testEveryMessageStageIsIdempotentAcrossRepeatedRecoveryRuns();
testDateOnlyMarkerCannotCauseARepeat();
testHistoricalIssuesStayQuarantinedWithoutSendingOrStateWrites();
testHistoricalTerminalStagesCannotBulkEmail();
testNewReviewCycleCanSendAfterHistoricalMigration();
testIntermediateNonMessageStageStillCreatesANewCycle();
testAccountSubtypeChangeDoesNotChangePendingTemplate();
testMissingReporterRetriesTheSameToken();
testTelemetryMessageWaitsForFreshAudit();
testAuditFreshnessFailsClosedAtBoundaryAndForFutureValues();
testManualOutcomeMessageDoesNotRequireAuditTelemetry();
testFailedCommentCreationPropagatesForTransactionRollback();
testExactDeliveryTimestampIsPersisted();
testPendingNewCycleCannotReuseAnOlderDeliveryTimestamp();
testStageMismatchCannotInventADelivery();
testInternalRepairCanSuppressAStageMessage();
testStaleRepairSuppressionCannotHideAnotherStage();
testMissingExtensionStateFailsClosedBeforeAddingAComment();
testApprovedMessagesKeepSafetyWording();
testImplementationDoesNotTrustDateFieldsOrHistoricalComments();

console.log('CMA communications tests passed');
