const entities = require('@jetbrains/youtrack-scripting-api/entities');
const dateTime = require('@jetbrains/youtrack-scripting-api/date-time');

const REVIEW_TIME_ZONE = 'Australia/Melbourne';

function calendarDate(timestamp) {
  return dateTime.format(timestamp, 'yyyy-MM-dd', REVIEW_TIME_ZONE);
}

exports.rule = entities.Issue.onSchedule({
  title: 'Advance CMA account reviews at grace-period deadlines',
  search: 'project: CMA has: {Grace Period Ends} Outcome: Pending',
  cron: '0 5 * * * ?',
  muteUpdateNotifications: false,
  modifyUpdatedProperties: false,
  guard: (ctx) => {
    const issue = ctx.issue;
    const stageIsActive =
      issue.fields.is(ctx.ReviewStage, ctx.ReviewStage.SubjectToDeletion) ||
      issue.fields.is(ctx.ReviewStage, ctx.ReviewStage.FinalReminder);

    return Boolean(issue.fields.GracePeriodEnds) && stageIsActive;
  },
  action: (ctx) => {
    const issue = ctx.issue;
    const graceDate = calendarDate(issue.fields.GracePeriodEnds);
    const today = calendarDate(Date.now());
    const tomorrow = calendarDate(dateTime.after(Date.now(), '1d'));

    if (graceDate <= today) {
      issue.fields.ReviewStage = ctx.ReviewStage.RemovalDue;
    } else if (
      graceDate <= tomorrow &&
      issue.fields.is(ctx.ReviewStage, ctx.ReviewStage.SubjectToDeletion)
    ) {
      issue.fields.ReviewStage = ctx.ReviewStage.FinalReminder;
    }
  },
  requirements: {
    GracePeriodEnds: {
      type: entities.Field.dateType,
      name: 'Grace Period Ends'
    },
    ReviewStage: {
      type: entities.EnumField.fieldType,
      name: 'Review Stage',
      SubjectToDeletion: {name: 'Subject to Deletion'},
      FinalReminder: {name: 'Final Reminder'},
      RemovalDue: {name: 'Removal Due'}
    },
    Outcome: {
      type: entities.EnumField.fieldType,
      Pending: {}
    }
  }
});
