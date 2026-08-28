const communications = require('./communications');

const DAY_MS = 24 * 60 * 60 * 1000;

function advanceIfReady(ctx) {
  const issue = ctx.issue;
  if (!issue.fields.is(ctx.Outcome, ctx.Outcome.Pending)) {
    return false;
  }

  const subjectToDeletion = issue.fields.is(
    ctx.ReviewStage,
    ctx.ReviewStage.SubjectToDeletion
  );
  const finalReminder = issue.fields.is(
    ctx.ReviewStage,
    ctx.ReviewStage.FinalReminder
  );
  const deliveredAt = communications.currentMessageDeliveredAt(issue);
  if ((!subjectToDeletion && !finalReminder) || !deliveredAt ||
      !communications.hasFreshAudit(issue, deliveredAt)) {
    return false;
  }

  const wait = subjectToDeletion ? 6 * DAY_MS : DAY_MS;
  if (Date.now() < deliveredAt + wait) {
    return false;
  }

  issue.fields.ReviewStage = subjectToDeletion ?
    ctx.ReviewStage.FinalReminder :
    ctx.ReviewStage.RemovalDue;
  return true;
}

exports.advanceIfReady = advanceIfReady;
