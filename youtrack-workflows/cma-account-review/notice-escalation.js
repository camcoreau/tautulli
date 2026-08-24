const entities = require('@jetbrains/youtrack-scripting-api/entities');
const dateTime = require('@jetbrains/youtrack-scripting-api/date-time');

const REVIEW_TIME_ZONE = 'Australia/Melbourne';

function day(value) {
  return dateTime.format(value, 'yyyy-MM-dd', REVIEW_TIME_ZONE);
}

exports.rule = entities.Issue.onSchedule({
  title: 'Escalate CMA inactivity notices after seven days',
  search: 'project: CMA {Review Stage}: {Inactivity Notice} Outcome: Pending has: {Inactivity Notice Sent}',
  cron: '0 20 * * * ?',
  muteUpdateNotifications: false,
  modifyUpdatedProperties: false,
  guard: (ctx) => {
    const issue = ctx.issue;
    const noticeSent = issue.fields.InactivityNoticeSent;

    return noticeSent &&
      day(Date.now()) >= day(dateTime.after(noticeSent, '7d'));
  },
  action: (ctx) => {
    const issue = ctx.issue;
    const noticeDay = day(issue.fields.InactivityNoticeSent);
    const lastStreamed = issue.fields.LastStreamed;
    const resumedStreaming = lastStreamed && day(lastStreamed) >= noticeDay;

    issue.fields.ReviewStage = resumedStreaming ?
      ctx.ReviewStage.AccessRetained :
      ctx.ReviewStage.SubjectToDeletion;
  },
  requirements: {
    ReviewStage: {
      type: entities.EnumField.fieldType,
      name: 'Review Stage',
      InactivityNotice: {name: 'Inactivity Notice'},
      SubjectToDeletion: {name: 'Subject to Deletion'},
      AccessRetained: {name: 'Access Retained'}
    },
    Outcome: {
      type: entities.EnumField.fieldType,
      Pending: {}
    },
    InactivityNoticeSent: {
      type: entities.Field.dateType,
      name: 'Inactivity Notice Sent'
    },
    LastStreamed: {
      type: entities.Field.dateType,
      name: 'Last Streamed'
    }
  }
});
