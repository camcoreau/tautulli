const dateTime = require('@jetbrains/youtrack-scripting-api/date-time');
const communications = require('./communications');

const REVIEW_TIME_ZONE = 'Australia/Melbourne';
const DAY_MS = 24 * 60 * 60 * 1000;

function day(value) {
  return dateTime.format(value, 'yyyy-MM-dd', REVIEW_TIME_ZONE);
}

function advanceIfReady(ctx) {
  const issue = ctx.issue;
  if (!issue.fields.is(ctx.ReviewStage, ctx.ReviewStage.InactivityNotice) ||
      !issue.fields.is(ctx.Outcome, ctx.Outcome.Pending)) {
    return false;
  }

  const deliveredAt = communications.currentMessageDeliveredAt(issue);
  if (!deliveredAt || !communications.hasFreshAudit(issue, deliveredAt) ||
      Date.now() < deliveredAt + 7 * DAY_MS) {
    return false;
  }

  const noticeDay = day(deliveredAt);
  const lastStreamed = issue.fields.LastStreamed;
  const resumedStreaming = lastStreamed && day(lastStreamed) >= noticeDay;
  issue.fields.ReviewStage = resumedStreaming ?
    ctx.ReviewStage.AccessRetained :
    ctx.ReviewStage.SubjectToDeletion;
  return true;
}

exports.advanceIfReady = advanceIfReady;
