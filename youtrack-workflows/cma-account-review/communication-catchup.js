const entities = require('@jetbrains/youtrack-scripting-api/entities');
const communications = require('./communications');

exports.rule = entities.Issue.onSchedule({
  title: 'Send any missing CMA lifecycle messages',
  search: 'project: CMA',
  cron: '0 10 * * * ?',
  muteUpdateNotifications: false,
  modifyUpdatedProperties: false,
  guard: (ctx) => communications.needsMessage(ctx.issue),
  action: (ctx) => {
    communications.sendCurrentMessage(ctx.issue);
  },
  requirements: {
    ReviewStage: {
      type: entities.EnumField.fieldType,
      name: 'Review Stage',
      InactivityNotice: {name: 'Inactivity Notice'},
      SubjectToDeletion: {name: 'Subject to Deletion'},
      FinalReminder: {name: 'Final Reminder'},
      AccessRemoved: {name: 'Access Removed'},
      AccessRetained: {name: 'Access Retained'}
    },
    AccountStatus: {
      type: entities.EnumField.fieldType,
      name: 'Account Status',
      NeverUsed: {name: 'Never Used'}
    },
    InactivityNoticeSent: {
      type: entities.Field.dateType,
      name: 'Inactivity Notice Sent'
    }
  }
});
