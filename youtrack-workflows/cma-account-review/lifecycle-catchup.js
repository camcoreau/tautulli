const entities = require('@jetbrains/youtrack-scripting-api/entities');
const dateTime = require('@jetbrains/youtrack-scripting-api/date-time');
const communications = require('./communications');

function sevenDaysFromNow() {
  return dateTime.after(Date.now(), '7d');
}

function valueName(value) {
  return value ? value.name : null;
}

function isValue(issue, field, value) {
  return issue.fields.is(field, value);
}

function needsRepair(ctx) {
  const issue = ctx.issue;
  const stage = valueName(issue.fields.ReviewStage);

  if (!stage) {
    return isValue(issue, ctx.Outcome, ctx.Outcome.Pending) &&
      isValue(issue, ctx.AccountStatus, ctx.AccountStatus.Active);
  }

  if (stage === ctx.ReviewStage.InactivityNotice.name) {
    return !issue.fields.InactivityNoticeSent ||
      communications.needsMessage(issue) ||
      !isValue(issue, ctx.Outcome, ctx.Outcome.Pending) ||
      !isValue(issue, ctx.State, ctx.State.Pending) ||
      !issue.fields.RemovalReason;
  }

  if (stage === ctx.ReviewStage.SubjectToDeletion.name) {
    return !issue.fields.GracePeriodEnds ||
      communications.needsMessage(issue) ||
      !isValue(issue, ctx.Outcome, ctx.Outcome.Pending) ||
      !isValue(issue, ctx.State, ctx.State.Pending);
  }

  if (stage === ctx.ReviewStage.FinalReminder.name ||
      stage === ctx.ReviewStage.RemovalDue.name) {
    return !isValue(issue, ctx.Outcome, ctx.Outcome.Pending) ||
      !isValue(issue, ctx.State, ctx.State.Pending);
  }

  if (stage === ctx.ReviewStage.AccessRetained.name) {
    return !isValue(issue, ctx.Outcome, ctx.Outcome.Retained) ||
      !isValue(issue, ctx.State, ctx.State.Solved);
  }

  if (stage === ctx.ReviewStage.AccessRemoved.name) {
    return !isValue(issue, ctx.Outcome, ctx.Outcome.Removed) ||
      !issue.fields.RemovalCompleted ||
      !isValue(issue, ctx.State, ctx.State.Solved);
  }

  if (stage === ctx.ReviewStage.Exempt.name) {
    return !isValue(issue, ctx.Outcome, ctx.Outcome.Exempt) ||
      !isValue(issue, ctx.State, ctx.State.Solved);
  }

  return false;
}

function repair(ctx) {
  const issue = ctx.issue;
  const stage = valueName(issue.fields.ReviewStage);

  if (!stage) {
    issue.fields.ReviewStage = ctx.ReviewStage.AccessRetained;
    return;
  }

  if (stage === ctx.ReviewStage.InactivityNotice.name) {
    if (!issue.fields.InactivityNoticeSent || communications.needsMessage(issue)) {
      // Start the timer when the first public notice can actually be sent.
      issue.fields.InactivityNoticeSent = Date.now();
    }
    issue.fields.Outcome = ctx.Outcome.Pending;
    issue.fields.State = ctx.State.Pending;
    issue.fields.RemovalReason = isValue(
      issue,
      ctx.AccountStatus,
      ctx.AccountStatus.NeverUsed
    ) ? ctx.RemovalReason.NeverUsed : ctx.RemovalReason.Inactivity;
    return;
  }

  if (stage === ctx.ReviewStage.SubjectToDeletion.name) {
    if (!issue.fields.GracePeriodEnds || communications.needsMessage(issue)) {
      // A delayed catch-up notice still receives the full promised seven days.
      issue.fields.GracePeriodEnds = sevenDaysFromNow();
    }
    issue.fields.Outcome = ctx.Outcome.Pending;
    issue.fields.State = ctx.State.Pending;
    return;
  }

  if (stage === ctx.ReviewStage.FinalReminder.name ||
      stage === ctx.ReviewStage.RemovalDue.name) {
    issue.fields.Outcome = ctx.Outcome.Pending;
    issue.fields.State = ctx.State.Pending;
    return;
  }

  if (stage === ctx.ReviewStage.AccessRetained.name) {
    issue.fields.Outcome = ctx.Outcome.Retained;
    issue.fields.State = ctx.State.Solved;
    return;
  }

  if (stage === ctx.ReviewStage.AccessRemoved.name) {
    issue.fields.Outcome = ctx.Outcome.Removed;
    issue.fields.RemovalCompleted = issue.fields.RemovalCompleted || Date.now();
    issue.fields.State = ctx.State.Solved;
    return;
  }

  if (stage === ctx.ReviewStage.Exempt.name) {
    issue.fields.Outcome = ctx.Outcome.Exempt;
    issue.fields.State = ctx.State.Solved;
  }
}

exports.rule = entities.Issue.onSchedule({
  title: 'Repair incomplete CMA lifecycle state before communications',
  search: 'project: CMA',
  cron: '0 2 * * * ?',
  muteUpdateNotifications: false,
  modifyUpdatedProperties: false,
  guard: needsRepair,
  action: repair,
  requirements: {
    ReviewStage: {
      type: entities.EnumField.fieldType,
      name: 'Review Stage',
      InactivityNotice: {name: 'Inactivity Notice'},
      SubjectToDeletion: {name: 'Subject to Deletion'},
      FinalReminder: {name: 'Final Reminder'},
      RemovalDue: {name: 'Removal Due'},
      AccessRemoved: {name: 'Access Removed'},
      AccessRetained: {name: 'Access Retained'},
      Exempt: {}
    },
    AccountStatus: {
      type: entities.EnumField.fieldType,
      name: 'Account Status',
      Active: {},
      NeverUsed: {name: 'Never Used'}
    },
    Outcome: {
      type: entities.EnumField.fieldType,
      name: 'Outcome',
      Pending: {},
      Retained: {},
      Removed: {},
      Exempt: {}
    },
    RemovalReason: {
      type: entities.EnumField.fieldType,
      name: 'Removal Reason',
      Inactivity: {},
      NeverUsed: {name: 'Never Used'}
    },
    InactivityNoticeSent: {
      type: entities.Field.dateType,
      name: 'Inactivity Notice Sent'
    },
    GracePeriodEnds: {
      type: entities.Field.dateType,
      name: 'Grace Period Ends'
    },
    RemovalCompleted: {
      type: entities.Field.dateType,
      name: 'Removal Completed'
    },
    State: {
      type: entities.State.fieldType,
      name: 'State',
      Pending: {},
      Solved: {}
    }
  }
});

exports.needsRepair = needsRepair;
exports.repair = repair;
