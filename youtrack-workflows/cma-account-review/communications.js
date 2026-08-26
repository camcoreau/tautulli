const TEMPLATES = {
  inactivity: [
    'Hi,',
    '',
    "We've noticed that your **Cameron-Media** account hasn't been used recently.",
    '',
    'As part of our regular account and access reviews, we periodically check inactive accounts to ensure Cameron-Media remains secure, organised and available for members who actively use the service.',
    '',
    '## No action is required right now',
    '',
    'Your access is still active.',
    '',
    "If you'd like to keep your Cameron-Media access, simply continue using the service as normal.",
    '',
    "Accounts that remain inactive for an extended period may eventually be placed **subject to deletion**, at which point we'll contact you again before any access is removed.",
    '',
    'Thank you for being part of Cameron-Media.',
    '',
    '**CamCore Media**  ',
    '*Cameron-Media Account Administration*'
  ].join('\n'),
  neverUsed: [
    'Hi,',
    '',
    'Our account review shows that your **Cameron-Media** access has not yet been used.',
    '',
    'Your Plex account currently has access to Cameron-Media, but we have no recorded streaming activity associated with your membership.',
    '',
    '## Would you still like access?',
    '',
    'If you would like to keep your Cameron-Media access, please either:',
    '',
    '- Start using the Cameron-Media library; or',
    '- Reply to this email and let us know you still intend to use the service.',
    '',
    'Accounts that remain unused may be removed as part of our regular account and access reviews.',
    '',
    'If you no longer require access, no action is necessary.',
    '',
    '**CamCore Media**  ',
    '*Cameron-Media Account Administration*'
  ].join('\n'),
  subjectToDeletion: [
    'Hi,',
    '',
    'Your **Cameron-Media** account has been identified as inactive and is now **subject to deletion** as part of our regular account and access review.',
    '',
    '## Action required',
    '',
    'To keep your access, please do **one** of the following within the next **7 days**:',
    '',
    '- Stream something from Cameron-Media using your Plex account; or',
    '- Reply to this email and let us know that you would like to keep your access.',
    '',
    'If no activity or response is received within 7 days, your access to **Cameron-Media may be removed without further notice**.',
    '',
    '## What would be removed?',
    '',
    'Your personal Plex account will **not** be deleted.',
    '',
    'Only your access to the Cameron-Media library will be removed.',
    '',
    'If you would like access again in the future, you can contact CamCore Support and request a new invitation.',
    '',
    'Thank you for helping us keep Cameron-Media tidy and available for everyone.',
    '',
    '**CamCore Media**  ',
    '*Cameron-Media Account Administration*'
  ].join('\n'),
  finalReminder: [
    'Hi,',
    '',
    'This is a **final reminder** regarding your inactive Cameron-Media account.',
    '',
    'We previously contacted you because your account had been identified as inactive and was placed **subject to deletion**.',
    '',
    "We still haven't detected qualifying activity or received confirmation that you would like to retain your access.",
    '',
    '## Your access is scheduled for removal',
    '',
    'Unless you use Cameron-Media or reply before the end of your current grace period, your access to the **Cameron-Media Plex library will be removed**.',
    '',
    'No further reminder will be sent before removal.',
    '',
    'Your personal Plex account will not be affected.',
    '',
    'If you would like to keep your access, simply stream something from Cameron-Media or reply to this email.',
    '',
    '**CamCore Media**  ',
    '*Cameron-Media Account Administration*'
  ].join('\n'),
  accessRemoved: [
    'Hi,',
    '',
    'Your access to **Cameron-Media** has now been removed following an extended period of inactivity.',
    '',
    'Previous notices were sent providing an opportunity to retain your access. As no qualifying activity or response was received within the specified period, your Cameron-Media library access has now been withdrawn.',
    '',
    '## What has been removed?',
    '',
    'This action only removes your access to the **Cameron-Media Plex library**.',
    '',
    'Your personal Plex account has **not** been deleted or modified, and any other Plex services you use are unaffected.',
    '',
    '## Want to come back?',
    '',
    'If you would like to use Cameron-Media again in the future, you are welcome to contact **CamCore Support** and request access again.',
    '',
    'Any new access request will be reviewed in accordance with the current Cameron-Media membership and availability requirements.',
    '',
    'Thank you for previously being part of Cameron-Media.',
    '',
    '**CamCore Media**  ',
    '*Cameron-Media Account Administration*'
  ].join('\n'),
  accessRetained: [
    'Hi,',
    '',
    'Thanks for confirming that you would like to continue using **Cameron-Media**.',
    '',
    'Your account has been removed from the current inactivity review and **your access will remain active**.',
    '',
    "There's nothing further you need to do.",
    '',
    'Future inactivity reviews may still apply if the account goes unused for an extended period.',
    '',
    'Thanks for being part of Cameron-Media.',
    '',
    '**CamCore Media**  ',
    '*Cameron-Media Account Administration*'
  ].join('\n')
};

const SIGNATURES = {
  inactivity: "account hasn't been used recently",
  neverUsed: 'access has not yet been used',
  subjectToDeletion: 'now **subject to deletion**',
  finalReminder: 'This is a **final reminder**',
  accessRemoved: 'access to **Cameron-Media** has now been removed',
  accessRetained: 'removed from the current inactivity review'
};

function valueName(value) {
  return value ? value.name : null;
}

function messageKey(issue) {
  const stage = valueName(issue.fields['Review Stage']);
  const accountStatus = valueName(issue.fields['Account Status']);

  if (stage === 'Inactivity Notice') {
    return accountStatus === 'Never Used' ? 'neverUsed' : 'inactivity';
  }
  if (stage === 'Subject to Deletion') {
    return 'subjectToDeletion';
  }
  if (stage === 'Final Reminder') {
    return 'finalReminder';
  }
  if (stage === 'Access Removed') {
    return 'accessRemoved';
  }
  if (stage === 'Access Retained') {
    return 'accessRetained';
  }
  return null;
}

function cycleStartedAt(issue) {
  return issue.fields['Inactivity Notice Sent'] || 0;
}

function hasMessageSince(issue, signature, since) {
  let found = false;
  issue.comments.forEach(function(comment) {
    if (!found && !comment.deleted && comment.created >= since &&
        typeof comment.text === 'string' && comment.text.indexOf(signature) !== -1) {
      found = true;
    }
  });
  return found;
}

function needsMessage(issue) {
  const key = messageKey(issue);
  return Boolean(key) &&
    !hasMessageSince(issue, SIGNATURES[key], cycleStartedAt(issue));
}

function sendCurrentMessage(issue) {
  const key = messageKey(issue);
  if (!key || !needsMessage(issue)) {
    return false;
  }
  if (!issue.reporter) {
    console.warn('CMA automated message skipped because the issue has no reporter: ' + issue.id);
    return false;
  }

  const comment = issue.addComment(TEMPLATES[key]);
  comment.permittedUsers.clear();
  comment.permittedGroups.clear();
  return true;
}

exports.TEMPLATES = TEMPLATES;
exports.SIGNATURES = SIGNATURES;
exports.messageKey = messageKey;
exports.hasMessageSince = hasMessageSince;
exports.needsMessage = needsMessage;
exports.sendCurrentMessage = sendCurrentMessage;
