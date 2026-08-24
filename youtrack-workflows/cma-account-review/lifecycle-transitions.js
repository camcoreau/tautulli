const entities = require('@jetbrains/youtrack-scripting-api/entities');
const dateTime = require('@jetbrains/youtrack-scripting-api/date-time');

const REVIEW_TIME_ZONE = 'Australia/Melbourne';

function sevenDaysFromToday() {
  const targetDate = dateTime.format(
    dateTime.after(Date.now(), '7d'),
    'yyyy-MM-dd',
    REVIEW_TIME_ZONE
  );

  return dateTime.parse(
    targetDate + ' 12:00',
    'yyyy-MM-dd HH:mm',
    'UTC'
  );
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
    } else if (issue.fields.becomes(ctx.ReviewStage, ctx.ReviewStage.SubjectToDeletion)) {
      issue.fields.GracePeriodEnds = sevenDaysFromToday();
      issue.fields.Outcome = ctx.Outcome.Pending;
      issue.fields.State = ctx.State.Pending;
    } else if (issue.fields.becomes(ctx.ReviewStage, ctx.ReviewStage.AccessRetained)) {
      issue.fields.Outcome = ctx.Outcome.Retained;
      issue.fields.State = ctx.State.Solved;
    } else if (issue.fields.becomes(ctx.ReviewStage, ctx.ReviewStage.AccessRemoved)) {
      issue.fields.Outcome = ctx.Outcome.Removed;
      issue.fields.RemovalCompleted = Date.now();
      issue.fields.State = ctx.State.Solved;
    } else if (issue.fields.becomes(ctx.ReviewStage, ctx.ReviewStage.Exempt)) {
      issue.fields.Outcome = ctx.Outcome.Exempt;
      issue.fields.State = ctx.State.Solved;
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
    State: {
      type: entities.State.fieldType,
      Pending: {},
      Solved: {}
    }
  }
});
