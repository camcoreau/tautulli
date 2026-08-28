const entities = require('@jetbrains/youtrack-scripting-api/entities');
const communications = require('./communications');

exports.rule = entities.Issue.onChange({
  title: 'Send CMA lifecycle messages when the review stage changes',
  guard: (ctx) => ctx.issue.fields.isChanged(ctx.ReviewStage),
  action: (ctx) => {
    // Every stage transition receives a fresh delivery token. This remains
    // correct even when a later review returns to the same message stage.
    communications.sendForStageChange(ctx.issue);
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
