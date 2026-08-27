const assert = require('assert');
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'overdue-notifications.js'),
  'utf8'
);

function includes(value, message) {
  assert.ok(source.includes(value), message || ('Expected workflow source to include: ' + value));
}

function excludes(value, message) {
  assert.ok(!source.includes(value), message || ('Expected workflow source not to include: ' + value));
}

function testStockDueDateBehaviourIsPreserved() {
  includes("search: '#Unresolved has: {Due Date}'");
  includes("cron: '0 0 10 ? * MON-FRI'");
  includes('ctx.issue.fields.DueDate < Date.now()');
  includes('issue.fields.Assignee || issue.project.leader');
}

function testCamCorePresentationIsRequired() {
  includes("const SUBJECT = 'Action required | CamCore task overdue'");
  includes('CAMCORE OPERATIONS • TASKS');
  includes('Task overdue');
  includes('Open in CamCore Tasks');
  includes('CamCore Operations');
  includes('https://tasks.camcore.network/');
  includes('https://status.camcore.au/');
  includes('https://camcore.au/support.html');
  includes('mailto:help@camcore.au');
}

function testJetBrainsPresentationDoesNotReturn() {
  excludes('[' + 'YouTrack, Issue is overdue]');
  excludes('Sincerely yours, ' + 'YouTrack');
}

function testIssueContentIsEscapedBeforeHtmlRendering() {
  includes('const issueId = escapeHtml(issue.id)');
  includes('const summary = escapeHtml(issue.summary || issue.id)');
  includes('const issueUrl = escapeHtml(issue.url)');
  includes("dateTime.format(issue.fields.DueDate, 'dd MMM yyyy', CAMCORE_TIME_ZONE)");
}

testStockDueDateBehaviourIsPreserved();
testCamCorePresentationIsRequired();
testJetBrainsPresentationDoesNotReturn();
testIssueContentIsEscapedBeforeHtmlRendering();

console.log('CamCore overdue notification tests passed');
