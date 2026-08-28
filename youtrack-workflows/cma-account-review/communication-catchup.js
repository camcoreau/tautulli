const entities = require('@jetbrains/youtrack-scripting-api/entities');
const communications = require('./communications');

exports.rule = entities.Issue.onSchedule({
  title: 'Retry pending CMA manual outcome messages',
  search: 'project: CMA',
  cron: '0 10 10 * * ?',
  muteUpdateNotifications: false,
  modifyUpdatedProperties: false,
  // Telemetry-driven notices are deliberately excluded. Only a successful
  // account-audit pulse can release or advance those messages.
  guard: (ctx) => communications.needsCatchUp(ctx.issue),
  action: (ctx) => {
    communications.sendCurrentMessage(ctx.issue, false);
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
    }
  }
});
