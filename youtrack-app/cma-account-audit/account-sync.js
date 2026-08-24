const entities = require('@jetbrains/youtrack-scripting-api/entities');
const search = require('@jetbrains/youtrack-scripting-api/search');

const PROJECT_ID = 'CMA';
const REVIEW_STAGES_IN_PROGRESS = [
  'Inactivity Notice',
  'Subject to Deletion',
  'Final Reminder',
  'Removal Due'
];

function replyError(ctx, code, message) {
  ctx.response.code = code;
  ctx.response.json({error: message});
}

function requiredString(body, key) {
  const value = body[key];
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(key + ' must be a non-empty string');
  }
  return value.trim();
}

function optionalInteger(body, key) {
  const value = body[key];
  if (value === null || value === undefined) {
    return null;
  }
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(key + ' must be a non-negative integer or null');
  }
  return value;
}

function queryValue(value) {
  return '{' + value.replace(/([\\{}"])/g, '\\$1') + '}';
}

function exactMatches(project, fieldName, value, user) {
  if (!value) {
    return [];
  }
  const matches = search.search(
    project,
    {query: '{' + fieldName + '}: ' + queryValue(value)},
    user
  );
  const exact = [];
  matches.forEach(function(issue) {
    const fieldValue = issue.fields[fieldName];
    if (fieldValue !== null && String(fieldValue) === value) {
      exact.push(issue);
    }
  });
  return exact;
}

function uniqueMatch(ctx, fieldName, value) {
  const matches = exactMatches(ctx.project, fieldName, value, ctx.currentUser);
  if (matches.length > 1) {
    throw new Error(
      'Multiple CMA tickets have the same ' + fieldName + '; resolve the duplicate before syncing'
    );
  }
  return matches.length === 1 ? matches[0] : null;
}

function stageName(issue) {
  const value = issue.fields['Review Stage'];
  return value ? value.name : null;
}

function statusValue(ctx, name) {
  if (name === 'Active') {
    return ctx.AccountStatus.Active;
  }
  if (name === 'Inactive') {
    return ctx.AccountStatus.Inactive;
  }
  if (name === 'Never Used') {
    return ctx.AccountStatus.NeverUsed;
  }
  throw new Error('accountStatus must be Active, Inactive, or Never Used');
}

function buildDescription(body) {
  const lastStreamed = body.lastStreamedMs ?
    new Date(body.lastStreamedMs).toISOString().slice(0, 10) :
    'Never';

  return [
    '## Cameron-Media Account Review',
    '',
    '**Plex Username:** ' + body.plexUsername,
    '**Plex User ID:** ' + body.plexUserId,
    '**Last Streamed:** ' + lastStreamed,
    '**Total Plays:** ' + body.totalPlays,
    '**Total Watch Time:** ' + body.watchTime,
    '',
    '### Review',
    '',
    'This ticket records the Cameron-Media inactivity review and any resulting account-access action.',
    '',
    'All customer-facing notices, responses and administrative decisions should be recorded on this ticket.'
  ].join('\n');
}

function applyFacts(issue, body, ctx) {
  issue.fields['Plex User ID'] = body.plexUserId;
  issue.fields['Plex Username'] = body.plexUsername;
  issue.fields['Last Streamed'] = body.lastStreamedMs;
  issue.fields['Total Plays'] = body.totalPlays;
  issue.fields['Watch Time'] = body.watchTime;
  issue.fields['Account Status'] = statusValue(ctx, body.accountStatus);
}

function applyReviewDecision(issue, body, ctx) {
  const currentStage = stageName(issue);

  if (body.accountStatus === 'Active' &&
      REVIEW_STAGES_IN_PROGRESS.indexOf(currentStage) !== -1) {
    issue.fields['Review Stage'] = ctx.ReviewStage.AccessRetained;
    return 'retained';
  }

  if (!body.reviewNeeded) {
    return 'facts-only';
  }

  if (currentStage === 'Exempt' || currentStage === 'Access Removed') {
    return 'protected-terminal-stage';
  }

  if (REVIEW_STAGES_IN_PROGRESS.indexOf(currentStage) !== -1) {
    return 'review-already-in-progress';
  }

  issue.fields['Review Stage'] = ctx.ReviewStage.InactivityNotice;
  return 'notice-started';
}

exports.httpHandler = {
  endpoints: [
    {
      scope: 'project',
      method: 'POST',
      path: 'sync-account',
      permissions: ['UPDATE_ISSUE'],
      handle: function(ctx) {
        if (ctx.project.shortName !== PROJECT_ID) {
          replyError(ctx, 403, 'This endpoint can only be used with the CMA project');
          return;
        }

        let body;
        try {
          body = ctx.request.json();
          body.plexUserId = requiredString(body, 'plexUserId');
          body.plexUsername = requiredString(body, 'plexUsername');
          body.totalPlays = optionalInteger(body, 'totalPlays');
          body.watchSeconds = optionalInteger(body, 'watchSeconds');
          body.lastStreamedMs = optionalInteger(body, 'lastStreamedMs');
          body.watchTime = requiredString(body, 'watchTime');
          body.accountStatus = requiredString(body, 'accountStatus');
          if (typeof body.reviewNeeded !== 'boolean') {
            throw new Error('reviewNeeded must be a boolean');
          }
        } catch (error) {
          replyError(ctx, 400, error.message);
          return;
        }

        let issue;
        try {
          issue = uniqueMatch(ctx, 'Plex User ID', body.plexUserId);
          if (!issue) {
            issue = uniqueMatch(ctx, 'Plex Username', body.plexUsername);
          }
        } catch (error) {
          replyError(ctx, 409, error.message);
          return;
        }

        let created = false;
        if (!issue && !body.reviewNeeded) {
          ctx.response.json({result: 'healthy-no-ticket', plexUserId: body.plexUserId});
          return;
        }

        if (!issue) {
          const email = typeof body.email === 'string' ? body.email.trim() : '';
          const reporter = email ? entities.User.findUniqueByEmail(email) : null;
          if (!reporter) {
            replyError(
              ctx,
              422,
              'No unique YouTrack Helpdesk reporter matches the Plex email address'
            );
            return;
          }
          issue = new entities.Issue(
            reporter,
            ctx.project,
            'Account Review — ' + body.plexUsername
          );
          issue.description = buildDescription(body);
          created = true;
        }

        try {
          applyFacts(issue, body, ctx);
          const action = applyReviewDecision(issue, body, ctx);
          ctx.response.json({
            result: created ? 'created' : 'updated',
            action: action,
            issueId: issue.id,
            reviewStage: stageName(issue),
            plexUserId: body.plexUserId
          });
        } catch (error) {
          replyError(ctx, 400, error.message);
        }
      }
    }
  ],
  requirements: {
    PlexUserId: {
      type: entities.Field.stringType,
      name: 'Plex User ID'
    },
    PlexUsername: {
      type: entities.Field.stringType,
      name: 'Plex Username'
    },
    LastStreamed: {
      type: entities.Field.dateType,
      name: 'Last Streamed'
    },
    TotalPlays: {
      type: entities.Field.integerType,
      name: 'Total Plays'
    },
    WatchTime: {
      type: entities.Field.stringType,
      name: 'Watch Time'
    },
    AccountStatus: {
      type: entities.EnumField.fieldType,
      name: 'Account Status',
      Active: {},
      Inactive: {},
      NeverUsed: {name: 'Never Used'}
    },
    ReviewStage: {
      type: entities.EnumField.fieldType,
      name: 'Review Stage',
      Active: {},
      InactivityNotice: {name: 'Inactivity Notice'},
      SubjectToDeletion: {name: 'Subject to Deletion'},
      FinalReminder: {name: 'Final Reminder'},
      RemovalDue: {name: 'Removal Due'},
      AccessRemoved: {name: 'Access Removed'},
      AccessRetained: {name: 'Access Retained'},
      Exempt: {}
    }
  }
};

