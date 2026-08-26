const entities = require('@jetbrains/youtrack-scripting-api/entities');
const dateTime = require('@jetbrains/youtrack-scripting-api/date-time');

function sevenDaysFromNow() {
  return dateTime.after(Date.now(), '7d');
}

function setReviewerWhenAvailable(issue, ctx) {
  const field = issue.project.findFieldByName(ctx.ReviewedBy.name);
  const reviewer = field && field.findValueByLogin(ctx.currentUser.login);
  if (reviewer) {
    issue.fields.ReviewedBy = reviewer;
  }
}

exports.rule = entities.Issue.onChange({
  title: 'Apply CMA account review lifecycle transitions',
  guard: (ctx) => ctx.issue.fields.isChanged(ctx.ReviewStage),
  action: (ctx) => {
    const issue = ctx.issue;

    if (issue.fields.becomes(ctx.ReviewStage, ctx.ReviewStage.InactivityNotice)) {
      issue.fields.InactivityNoticeSent = Date.now();
      issue.fields.Outcome = ctx.Outcome.Pending;
      issue.fields.State = ctx.State.Pending;
      issue.fields.RemovalReason = issue.fields.is(
        ctx.AccountStatus,
        ctx.AccountStatus.NeverUsed
      ) ? ctx.RemovalReason.NeverUsed : ctx.RemovalReason.Inactivity;
    } else if (issue.fields.becomes(ctx.ReviewStage, ctx.ReviewStage.SubjectToDeletion)) {
      issue.fields.GracePeriodEnds = sevenDaysFromNow();
      issue.fields.Outcome = ctx.Outcome.Pending;
      issue.fields.State = ctx.State.Pending;
    } else if (issue.fields.becomes(ctx.ReviewStage, ctx.ReviewStage.AccessRetained)) {
      issue.fields.Outcome = ctx.Outcome.Retained;
      issue.fields.State = ctx.State.Solved;
    } else if (issue.fields.becomes(ctx.ReviewStage, ctx.ReviewStage.AccessRemoved)) {
      issue.fields.Outcome = ctx.Outcome.Removed;
      issue.fields.RemovalCompleted = Date.now();
      issue.fields.State = ctx.State.Solved;
      setReviewerWhenAvailable(issue, ctx);
    } else if (issue.fields.becomes(ctx.ReviewStage, ctx.ReviewStage.Exempt)) {
      issue.fields.Outcome = ctx.Outcome.Exempt;
      issue.fields.State = ctx.State.Solved;
      setReviewerWhenAvailable(issue, ctx);
    }
  },
  requirements: {
    ReviewStage: {
      type: entities.EnumField.fieldType,
      name: 'Review Stage',
      InactivityNotice: {name: 'Inactivity Notice'},
      SubjectToDeletion: {name: 'Subject to Deletion'},
      AccessRetained: {name: 'Access Retained'},
      AccessRemoved: {name: 'Access Removed'},
      Exempt: {}
    },
    InactivityNoticeSent: {
      type: entities.Field.dateType,
      name: 'Inactivity Notice Sent'
    },
    GracePeriodEnds: {
      type: entities.Field.dateType,
      name: 'Grace Period Ends'
    },
    Outcome: {
      type: entities.EnumField.fieldType,
      Pending: {},
      Retained: {},
      Removed: {},
      Exempt: {}
    },
    RemovalCompleted: {
      type: entities.Field.dateType,
      name: 'Removal Completed'
    },
    AccountStatus: {
      type: entities.EnumField.fieldType,
      name: 'Account Status',
      NeverUsed: {name: 'Never Used'}
    },
    RemovalReason: {
      type: entities.EnumField.fieldType,
      name: 'Removal Reason',
      Inactivity: {},
      NeverUsed: {name: 'Never Used'}
    },
    ReviewedBy: {
      type: entities.User.fieldType,
      name: 'Reviewed By'
    },
    State: {
      type: entities.State.fieldType,
      Pending: {},
      Solved: {}
    }
  }
});
