const entities = require('@jetbrains/youtrack-scripting-api/entities');
const dateTime = require('@jetbrains/youtrack-scripting-api/date-time');

const CAMCORE_TIME_ZONE = 'Australia/Melbourne';
const SUBJECT = 'Action required | CamCore task overdue';

function escapeHtml(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function notificationBody(issue) {
  const issueId = escapeHtml(issue.id);
  const summary = escapeHtml(issue.summary || issue.id);
  const issueUrl = escapeHtml(issue.url);
  const dueDate = escapeHtml(
    dateTime.format(issue.fields.DueDate, 'dd MMM yyyy', CAMCORE_TIME_ZONE)
  );

  return '<!doctype html>' +
    '<html lang="en-AU">' +
    '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>' +
    '<body style="margin:0;padding:0;background:#edf3f6;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;color:#10212b;">' +
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="width:100%;background:#edf3f6;">' +
    '<tr><td align="center" style="padding:34px 12px;">' +
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="640" style="width:640px;max-width:640px;margin:0 auto;">' +
    '<tr><td style="padding:22px 32px 18px;background:#071827;border-radius:12px 12px 0 0;">' +
    '<div style="color:#ffffff;font-size:32px;line-height:38px;font-weight:800;letter-spacing:-0.6px;">CamCore</div>' +
    '<div style="margin-top:4px;color:#a9bbc6;font-size:12px;line-height:18px;font-weight:600;">Cameron Family Secure Network</div>' +
    '<div style="margin-top:14px;color:#a9bbc6;font-size:10px;line-height:15px;font-weight:700;letter-spacing:1.8px;">CAMCORE OPERATIONS • TASKS</div>' +
    '</td></tr>' +
    '<tr><td style="height:4px;line-height:4px;font-size:0;background:#12c4de;">&nbsp;</td></tr>' +
    '<tr><td style="padding:36px 32px 32px;background:#ffffff;">' +
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 16px;"><tr><td style="padding:5px 10px;background:#fff1f0;border:1px solid #f3c5c1;border-radius:999px;color:#b42318;font-size:10px;line-height:13px;font-weight:800;letter-spacing:1.2px;">ACTION REQUIRED</td></tr></table>' +
    '<h1 style="margin:0;color:#071827;font-size:31px;line-height:38px;font-weight:800;letter-spacing:-0.55px;">Task overdue</h1>' +
    '<p style="margin:18px 0 0;color:#435562;font-size:15px;line-height:24px;">This CamCore task has passed its scheduled due date and requires attention.</p>' +
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="width:100%;margin:24px 0 0;">' +
    '<tr><td style="padding:18px 20px;background:#f1f6f8;border:1px solid #d8e4e9;border-radius:9px;">' +
    '<div style="color:#718391;font-size:10px;line-height:14px;font-weight:750;letter-spacing:1.4px;">TASK</div>' +
    '<div style="margin-top:7px;color:#071827;font-size:17px;line-height:24px;font-weight:750;">' + summary + '</div>' +
    '<div style="margin-top:4px;color:#718391;font-size:12px;line-height:18px;">' + issueId + '</div>' +
    '<div style="margin-top:18px;color:#718391;font-size:10px;line-height:14px;font-weight:750;letter-spacing:1.4px;">DUE DATE</div>' +
    '<div style="margin-top:5px;color:#b42318;font-size:15px;line-height:22px;font-weight:750;">' + dueDate + '</div>' +
    '</td></tr></table>' +
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 0;"><tr><td bgcolor="#11bdd4" style="border-radius:7px;"><a href="' + issueUrl + '" style="display:inline-block;padding:13px 20px;color:#05202a;font-size:15px;line-height:20px;font-weight:700;text-decoration:none;border-radius:7px;">Open in CamCore Tasks</a></td></tr></table>' +
    '<p style="margin:22px 0 0;color:#718391;font-size:12px;line-height:19px;">This reminder is sent on weekdays while the task remains unresolved and overdue.</p>' +
    '</td></tr>' +
    '<tr><td style="padding:24px 32px 26px;background:#f8fafb;border-top:1px solid #e2eaee;border-radius:0 0 12px 12px;text-align:center;">' +
    '<div style="color:#10212b;font-size:13px;line-height:18px;font-weight:750;">CamCore Operations</div>' +
    '<div style="margin-top:2px;color:#718391;font-size:11px;line-height:16px;">Cameron Family Secure Network</div>' +
    '<div style="margin-top:12px;font-size:12px;line-height:19px;"><a href="https://tasks.camcore.network/" style="color:#0d879b;font-weight:650;text-decoration:none;">CamCore Tasks</a>&nbsp;&nbsp;•&nbsp;&nbsp;<a href="https://status.camcore.au/" style="color:#0d879b;font-weight:650;text-decoration:none;">Service Status</a>&nbsp;&nbsp;•&nbsp;&nbsp;<a href="https://camcore.au/support.html" style="color:#0d879b;font-weight:650;text-decoration:none;">CamCore Support</a></div>' +
    '<div style="margin-top:4px;font-size:12px;line-height:18px;"><a href="mailto:help@camcore.au" style="color:#0d879b;font-weight:650;text-decoration:none;">help@camcore.au</a></div>' +
    '</td></tr></table>' +
    '</td></tr></table>' +
    '</body></html>';
}

exports.rule = entities.Issue.onSchedule({
  title: 'Send CamCore-branded overdue task notifications',
  search: '#Unresolved has: {Due Date}',
  cron: '0 0 10 ? * MON-FRI',
  guard: (ctx) => {
    return ctx.issue.fields.DueDate < Date.now();
  },
  action: (ctx) => {
    const issue = ctx.issue;
    const userToNotify = issue.fields.Assignee || issue.project.leader;

    if (!userToNotify) {
      console.warn('CamCore overdue notification skipped because no assignee or project leader is available: ' + issue.id);
      return;
    }

    userToNotify.notify(SUBJECT, notificationBody(issue));
  },
  requirements: {
    DueDate: {
      type: entities.Field.dateType,
      name: 'Due Date'
    },
    Assignee: {
      type: entities.User.fieldType
    }
  }
});
