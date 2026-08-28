const entities = require('@jetbrains/youtrack-scripting-api/entities');
const search = require('@jetbrains/youtrack-scripting-api/search');

const PROJECT_ID = 'CMA';
const MAX_FUTURE_SKEW_MS = 5 * 60 * 1000;
const ACCOUNT_STATUSES = ['Active', 'Inactive', 'Never Used'];
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
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(key + ' must be a non-negative safe integer or null');
  }
  return value;
}

function formatWatchTime(seconds) {
  const totalMinutes = Math.floor(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours ? hours + ' hrs ' + minutes + ' mins' : minutes + ' mins';
}

function validatePayload(payload, now) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('request body must be a JSON object');
  }

  const body = {
    plexUserId: requiredString(payload, 'plexUserId'),
    plexUsername: requiredString(payload, 'plexUsername'),
    email: requiredString(payload, 'email'),
    totalPlays: optionalInteger(payload, 'totalPlays'),
    watchSeconds: optionalInteger(payload, 'watchSeconds'),
    lastStreamedMs: optionalInteger(payload, 'lastStreamedMs'),
    watchTime: requiredString(payload, 'watchTime'),
    accountStatus: requiredString(payload, 'accountStatus'),
    reviewNeeded: payload.reviewNeeded
  };

  if (typeof body.reviewNeeded !== 'boolean') {
    throw new Error('reviewNeeded must be a boolean');
  }
  if (body.totalPlays === null || body.watchSeconds === null) {
    throw new Error('totalPlays and watchSeconds must be non-negative safe integers');
  }
  if (body.watchTime !== formatWatchTime(body.watchSeconds)) {
    throw new Error('watchTime does not match watchSeconds');
  }
  if (ACCOUNT_STATUSES.indexOf(body.accountStatus) === -1) {
    throw new Error('accountStatus must be Active, Inactive, or Never Used');
  }
  if (body.lastStreamedMs !== null && body.lastStreamedMs <= 0) {
    throw new Error('lastStreamedMs must be a positive timestamp or null');
  }
  if (body.lastStreamedMs !== null &&
      body.lastStreamedMs > now + MAX_FUTURE_SKEW_MS) {
    throw new Error('lastStreamedMs is too far in the future');
  }

  const hasNeverUsedFacts = body.totalPlays === 0 && body.lastStreamedMs === null;
  if ((body.accountStatus === 'Never Used') !== hasNeverUsedFacts) {
    throw new Error(
      'Never Used requires exactly zero plays and no last-streamed timestamp'
    );
  }
  if (body.totalPlays === 0 && body.lastStreamedMs !== null) {
    throw new Error('zero-play accounts cannot have a last-streamed timestamp');
  }
  if (body.totalPlays > 0 && body.lastStreamedMs === null) {
    throw new Error('accounts with plays require a last-streamed timestamp');
  }
  if (body.accountStatus === 'Active' &&
      (body.totalPlays <= 0 || body.lastStreamedMs === null || body.reviewNeeded)) {
    throw new Error(
      'Active requires plays, a last-streamed timestamp, and reviewNeeded=false'
    );
  }
  if (body.accountStatus === 'Inactive' && !body.reviewNeeded) {
    throw new Error('Inactive requires reviewNeeded=true');
  }
  return body;
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

function resolveIssue(ctx, body) {
  const idMatch = uniqueMatch(ctx, 'Plex User ID', body.plexUserId);
  const usernameMatch = uniqueMatch(ctx, 'Plex Username', body.plexUsername);
  if (idMatch && usernameMatch && idMatch.id !== usernameMatch.id) {
    throw new Error(
      'Plex User ID and Plex Username resolve to different CMA tickets; ' +
      'resolve the identity conflict before syncing'
    );
  }
  if (!idMatch && usernameMatch) {
    const storedId = usernameMatch.fields['Plex User ID'];
    if (storedId && String(storedId) !== body.plexUserId) {
      throw new Error(
        'Plex Username is already linked to a different Plex User ID; ' +
        'resolve the identity conflict before syncing'
      );
    }
  }
  return idMatch || usernameMatch;
}

function stageName(issue) {
  const value = issue.fields['Review Stage'];
  return value ? value.name : null;
}

function accountStatusName(issue) {
  const value = issue.fields['Account Status'];
  return value ? value.name : null;
}

function projectField(project, fieldName) {
  const field = project.findFieldByName(fieldName);
  if (!field) {
    throw new Error(fieldName + ' is not attached to project ' + project.shortName);
  }
  return field;
}

function projectValue(project, fieldName, valueName) {
  const field = projectField(project, fieldName);
  const value = field.findValueByName(valueName);
  if (!value) {
    throw new Error(fieldName + ' does not contain value ' + valueName);
  }
  return value;
}

function sameUser(left, right) {
  if (!left || !right) {
    return false;
  }
  if (left.id && right.id) {
    return left.id === right.id;
  }
  if (left.login && right.login) {
    return left.login === right.login;
  }
  return left === right;
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

function planReviewDecision(issue, body, previousAccountStatus) {
  const currentStage = issue ? stageName(issue) : null;

  if (body.accountStatus === 'Active' &&
      REVIEW_STAGES_IN_PROGRESS.indexOf(currentStage) !== -1) {
    return {action: 'retained', targetStage: 'Access Retained'};
  }

  if (!body.reviewNeeded) {
    return {action: 'facts-only', targetStage: null};
  }

  if (currentStage === 'Exempt' || currentStage === 'Access Removed') {
    return {action: 'protected-terminal-stage', targetStage: null};
  }

  if (currentStage === 'Access Retained') {
    if (previousAccountStatus === 'Active') {
      return {
        action: 'notice-restarted-after-active-baseline',
        targetStage: 'Inactivity Notice'
      };
    }
    return {action: 'retained-awaiting-new-active-baseline', targetStage: null};
  }

  if (REVIEW_STAGES_IN_PROGRESS.indexOf(currentStage) !== -1) {
    return {action: 'review-already-in-progress', targetStage: null};
  }

  return {action: 'notice-started', targetStage: 'Inactivity Notice'};
}

function preflightMutation(project, body, plan) {
  [
    'Plex User ID',
    'Plex Username',
    'Last Streamed',
    'Total Plays',
    'Watch Time',
    'Account Audit Confirmed At',
    'Review Stage'
  ].forEach(function(fieldName) {
    projectField(project, fieldName);
  });

  const values = {
    accountStatus: projectValue(project, 'Account Status', body.accountStatus),
    reviewStage: null
  };
  if (plan.targetStage) {
    values.reviewStage = projectValue(project, 'Review Stage', plan.targetStage);
  }
  return values;
}

function applyFacts(issue, body, values) {
  issue.fields['Plex User ID'] = body.plexUserId;
  issue.fields['Plex Username'] = body.plexUsername;
  issue.fields['Last Streamed'] = body.lastStreamedMs;
  issue.fields['Total Plays'] = body.totalPlays;
  issue.fields['Watch Time'] = body.watchTime;
  issue.fields['Account Status'] = values.accountStatus;
}

function applyReviewDecision(issue, plan, values) {
  if (plan.targetStage) {
    issue.fields['Review Stage'] = values.reviewStage;
  }
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
          body = validatePayload(ctx.request.json(), Date.now());
        } catch (error) {
          replyError(ctx, 400, error.message);
          return;
        }

        let issue;
        try {
          issue = resolveIssue(ctx, body);
        } catch (error) {
          replyError(ctx, 409, error.message);
          return;
        }

        if (!issue && !body.reviewNeeded) {
          ctx.response.json({result: 'healthy-no-ticket', plexUserId: body.plexUserId});
          return;
        }

        const reporter = entities.User.findUniqueByEmail(body.email);
        if (!reporter) {
          replyError(
            ctx,
            422,
            'No unique YouTrack Helpdesk reporter matches the Plex email address'
          );
          return;
        }
        if (issue && !sameUser(issue.reporter, reporter)) {
          replyError(
            ctx,
            409,
            'The existing CMA ticket reporter does not match the incoming Plex email'
          );
          return;
        }

        const previousAccountStatus = issue ? accountStatusName(issue) : null;
        const plan = planReviewDecision(issue, body, previousAccountStatus);
        let values;
        try {
          values = preflightMutation(ctx.project, body, plan);
        } catch (error) {
          replyError(ctx, 422, error.message);
          return;
        }

        const created = !issue;
        if (created) {
          issue = new entities.Issue(
            reporter,
            ctx.project,
            'Account Review — ' + body.plexUsername
          );
          issue.description = buildDescription(body);
        }

        // Keep every write in the request transaction. Mutation exceptions must
        // escape so YouTrack rolls the whole update back instead of acknowledging
        // a partial audit.
        applyFacts(issue, body, values);
        applyReviewDecision(issue, plan, values);
        issue.fields['Account Audit Confirmed At'] = Date.now();
        ctx.response.json({
          result: created ? 'created' : 'updated',
          action: plan.action,
          issueId: issue.id,
          reviewStage: stageName(issue),
          plexUserId: body.plexUserId
        });
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
    AccountAuditConfirmedAt: {
      type: entities.Field.dateTimeType,
      name: 'Account Audit Confirmed At'
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

