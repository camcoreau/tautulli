const entities = require('@jetbrains/youtrack-scripting-api/entities');

function isPublic(comment) {
  return comment.permittedGroups.isEmpty() && comment.permittedUsers.isEmpty();
}

function hasReporterReply(issue) {
  let found = false;
  issue.comments.added.forEach(function(comment) {
    if (!found && comment.author && issue.reporter &&
        comment.author.login === issue.reporter.login && isPublic(comment)) {
      found = true;
    }
  });
  return found;
}

exports.rule = entities.Issue.onChange({
  title: 'Retain CMA access when the reporter replies',
  guard: (ctx) => {
    const issue = ctx.issue;
    const activeReview =
      issue.fields.is(ctx.ReviewStage, ctx.ReviewStage.InactivityNotice) ||
      issue.fields.is(ctx.ReviewStage, ctx.ReviewStage.SubjectToDeletion) ||
      issue.fields.is(ctx.ReviewStage, ctx.ReviewStage.FinalReminder) ||
      issue.fields.is(ctx.ReviewStage, ctx.ReviewStage.RemovalDue);

    return activeReview &&
      issue.fields.is(ctx.Outcome, ctx.Outcome.Pending) &&
      issue.comments.added.isNotEmpty() &&
      hasReporterReply(issue);
  },
  action: (ctx) => {
    ctx.issue.fields.ReviewStage = ctx.ReviewStage.AccessRetained;
  },
  requirements: {
    ReviewStage: {
      type: entities.EnumField.fieldType,
      name: 'Review Stage',
      InactivityNotice: {name: 'Inactivity Notice'},
      SubjectToDeletion: {name: 'Subject to Deletion'},
      FinalReminder: {name: 'Final Reminder'},
      RemovalDue: {name: 'Removal Due'},
      AccessRetained: {name: 'Access Retained'}
    },
    Outcome: {
      type: entities.EnumField.fieldType,
      Pending: {}
    }
  }
});
