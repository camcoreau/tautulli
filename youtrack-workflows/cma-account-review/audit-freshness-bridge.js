const entities = require('@jetbrains/youtrack-scripting-api/entities');
const dateTime = require('@jetbrains/youtrack-scripting-api/date-time');
const communications = require('./communications');
const noticeEscalation = require('./notice-escalation');
const deadlineTransitions = require('./deadline-transitions');

const AUDIT_PULSE_MAX_AGE_MS = 5 * 60 * 1000;

function alignTimersWithDelivery(issue, key) {
  const deliveredAt = communications.currentMessageDeliveredAt(issue);
  if (!deliveredAt) {
    return;
  }
  if (key === 'inactivity' || key === 'neverUsed') {
    issue.fields['Inactivity Notice Sent'] = deliveredAt;
  } else if (key === 'subjectToDeletion') {
    issue.fields['Grace Period Ends'] = dateTime.after(deliveredAt, '7d');
  } else if (key === 'finalReminder') {
    issue.fields['Grace Period Ends'] = dateTime.after(deliveredAt, '1d');
  }
}

exports.rule = entities.Issue.onChange({
  title: 'Store successful CMA account-audit evidence privately',
  guard: (ctx) => ctx.issue.fields.isChanged(ctx.AccountAuditConfirmedAt) &&
    Boolean(ctx.issue.fields.AccountAuditConfirmedAt),
  action: (ctx) => {
    const issue = ctx.issue;
    const confirmedAt = Number(issue.fields.AccountAuditConfirmedAt);
    const now = Date.now();
    if (!Number.isSafeInteger(confirmedAt) || confirmedAt <= 0 ||
        confirmedAt > now || now - confirmedAt > AUDIT_PULSE_MAX_AGE_MS) {
      throw new Error('CMA account-audit confirmation timestamp is invalid');
    }
    if (!issue.extensionProperties) {
      throw new Error('CMA audit freshness storage is unavailable for ' + issue.id);
    }

    // The custom field is a private, transient cross-app pulse. Persist the
    // evidence in this workflow app's own storage and leave no daily field
    // value behind that could appear in a customer-facing issue update.
    issue.extensionProperties.cmaAccountAuditConfirmedAt = confirmedAt;
    issue.fields.AccountAuditConfirmedAt = null;

    const key = communications.currentDeliveryKey(issue);
    if (communications.sendCurrentMessage(issue, true)) {
      alignTimersWithDelivery(issue, key);
    }
    // Review clocks only evaluate inside this successful audit transaction.
    // There is no hourly fallback that can advance a ticket on stale facts.
    noticeEscalation.advanceIfReady(ctx);
    deadlineTransitions.advanceIfReady(ctx);
  },
  requirements: {
    AccountAuditConfirmedAt: {
      type: entities.Field.dateTimeType,
      name: 'Account Audit Confirmed At'
    },
    ReviewStage: {
      type: entities.EnumField.fieldType,
      name: 'Review Stage',
      InactivityNotice: {name: 'Inactivity Notice'},
      SubjectToDeletion: {name: 'Subject to Deletion'},
      FinalReminder: {name: 'Final Reminder'},
      RemovalDue: {name: 'Removal Due'},
      AccessRemoved: {name: 'Access Removed'},
      AccessRetained: {name: 'Access Retained'}
    },
    AccountStatus: {
      type: entities.EnumField.fieldType,
      name: 'Account Status',
      NeverUsed: {name: 'Never Used'}
    },
    Outcome: {
      type: entities.EnumField.fieldType,
      Pending: {}
    },
    LastStreamed: {
      type: entities.Field.dateType,
      name: 'Last Streamed'
    },
    InactivityNoticeSent: {
      type: entities.Field.dateType,
      name: 'Inactivity Notice Sent'
    },
    GracePeriodEnds: {
      type: entities.Field.dateType,
      name: 'Grace Period Ends'
    }
  }
});

exports.alignTimersWithDelivery = alignTimersWithDelivery;
