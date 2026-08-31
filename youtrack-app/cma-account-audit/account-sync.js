const entities = require('@jetbrains/youtrack-scripting-api/entities');
const search = require('@jetbrains/youtrack-scripting-api/search');

const PROJECT_ID = 'CMA';
const MAX_FUTURE_SKEW_MS = 5 * 60 * 1000;
const MEMBER_NOTIFICATION_WINDOW_MS = 24 * 60 * 60 * 1000;
const NOTIFICATION_POLICY_VERSION = 1;
const NOTIFICATION_PROTOCOL_ID = 'cma-account-audit-member-notification';
const ONBOARDING_PROTOCOL_VERSION = 1;
const NOTIFICATION_MODE_SUPPRESS = 'suppress';
const NOTIFICATION_MODE_PERMIT = 'permit';
const NOTIFICATION_DEFERRED_ACTION = 'member-notification-deferred';
const NOTIFICATION_BUDGET_EXHAUSTED_ACTION =
  'member-notification-budget-exhausted';
const TICKET_CREATED_AWAITING_NOTICE_ACTION =
  'ticket-created-awaiting-notice';
const ONBOARDING_TICKET_CREATED_ACTION = 'onboarding-ticket-created';
const ONBOARDING_EXISTING_TICKET_ACTION = 'onboarding-existing-ticket';
const CYCLE_ID_PATTERN = /^audit-[0-9a-f]{32}$/;
const ACCOUNT_STATUSES = ['Active', 'Inactive', 'Never Used'];
const REVIEW_STAGES_IN_PROGRESS = [
  'Inactivity Notice',
  'Subject to Deletion',
  'Final Reminder',
  'Removal Due'
];
const MEMBER_MESSAGE_STAGES = [
  'Inactivity Notice',
  'Subject to Deletion',
  'Final Reminder',
  'Access Removed',
  'Access Retained'
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
    reviewNeeded: payload.reviewNeeded,
    onboardingRequested: payload.onboardingRequested,
    notificationMode: requiredString(payload, 'notificationMode'),
    cycleId: requiredString(payload, 'cycleId')
  };

  if (typeof body.reviewNeeded !== 'boolean') {
    throw new Error('reviewNeeded must be a boolean');
  }
  if (typeof body.onboardingRequested !== 'boolean') {
    throw new Error('onboardingRequested must be a boolean');
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
  if (payload.notificationMode !== body.notificationMode ||
      (body.notificationMode !== NOTIFICATION_MODE_SUPPRESS &&
       body.notificationMode !== NOTIFICATION_MODE_PERMIT)) {
    throw new Error('notificationMode must be suppress or permit');
  }
  if (payload.cycleId !== body.cycleId || !CYCLE_ID_PATTERN.test(body.cycleId)) {
    throw new Error('cycleId must use the audit- prefix and 32 lowercase hex characters');
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

function buildOnboardingDescription(body) {
  return [
    '## Welcome to Cameron-Media',
    '',
    'Hi ' + body.plexUsername + ',',
    '',
    'Your Cameron-Media access is ready. Sign in with the same Plex account that received the library invitation.',
    '',
    '### Get started',
    '',
    '1. Accept the Plex library invitation if it is still waiting in your inbox.',
    '2. Open the [Plex Web App](https://app.plex.tv/desktop/) and select Cameron-Media from the sidebar.',
    '3. Install a Plex player for your TV, phone, tablet or computer from [Plex Apps & Devices](https://www.plex.tv/apps-devices/).',
    '4. Pin the Cameron-Media libraries you use most so they stay easy to find.',
    '',
    '### Need help?',
    '',
    'Reply to this ticket or email help@camcore.au and include the device you are using plus a screenshot of any error.',
    '',
    'Enjoy Cameron-Media!'
  ].join('\n');
}

function planReviewDecision(issue, body, previousAccountStatus) {
  const currentStage = issue ? stageName(issue) : null;

  if (body.onboardingRequested) {
    if (issue) {
      return {action: ONBOARDING_EXISTING_TICKET_ACTION, targetStage: null};
    }
    return {action: ONBOARDING_TICKET_CREATED_ACTION, targetStage: 'Active'};
  }

  if (!issue) {
    // Creating a Helpdesk ticket can notify its reporter. Keep the public
    // inactivity notice in a later permit window so one request cannot release
    // both the ticket-created email and a lifecycle-comment email.
    return {
      action: TICKET_CREATED_AWAITING_NOTICE_ACTION,
      targetStage: 'Active'
    };
  }

  const isStagedBeforeFirstNotice = currentStage === 'Active' &&
    previousAccountStatus !== 'Active';
  if (body.accountStatus === 'Active' &&
      (isStagedBeforeFirstNotice ||
       REVIEW_STAGES_IN_PROGRESS.indexOf(currentStage) !== -1)) {
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

function isMemberNotificationCandidate(issue, plan) {
  if (plan.action === ONBOARDING_TICKET_CREATED_ACTION) {
    return true;
  }
  if (plan.action === TICKET_CREATED_AWAITING_NOTICE_ACTION) {
    return true;
  }
  if (plan.targetStage && MEMBER_MESSAGE_STAGES.indexOf(plan.targetStage) !== -1) {
    return true;
  }
  return Boolean(issue) && MEMBER_MESSAGE_STAGES.indexOf(stageName(issue)) !== -1;
}

function globalBudgetStorage(ctx) {
  if (!ctx.globalStorage || !ctx.globalStorage.extensionProperties) {
    throw new Error('CMA member-notification budget storage is unavailable');
  }
  return ctx.globalStorage.extensionProperties;
}

function notificationBudget(ctx, now) {
  const storage = globalBudgetStorage(ctx);
  const reservedAt = storage.cmaMemberNotificationReservedAt;
  if (reservedAt === null || reservedAt === undefined || reservedAt === 0) {
    return {storage: storage, available: true, remaining: 1};
  }
  if (!Number.isSafeInteger(reservedAt) || reservedAt <= 0 || reservedAt > now) {
    throw new Error('CMA member-notification budget timestamp is invalid');
  }
  if (!CYCLE_ID_PATTERN.test(storage.cmaMemberNotificationCycleId || '') ||
      typeof storage.cmaMemberNotificationPlexUserId !== 'string' ||
      !storage.cmaMemberNotificationPlexUserId.trim()) {
    throw new Error('CMA member-notification budget reservation is invalid');
  }
  const available = now - reservedAt >= MEMBER_NOTIFICATION_WINDOW_MS;
  return {storage: storage, available: available, remaining: available ? 1 : 0};
}

function reserveNotificationBudget(budget, body, now) {
  budget.storage.cmaMemberNotificationReservedAt = now;
  budget.storage.cmaMemberNotificationCycleId = body.cycleId;
  budget.storage.cmaMemberNotificationPlexUserId = body.plexUserId;
  budget.available = false;
  budget.remaining = 0;
}

function receipt(
  body,
  permitRequired,
  permitReserved,
  budgetRemaining,
  onboardingCompleted
) {
  return {
    notificationPolicyVersion: NOTIFICATION_POLICY_VERSION,
    notificationMode: body.notificationMode,
    cycleId: body.cycleId,
    memberNotificationPermitRequired: permitRequired,
    memberNotificationPermitReserved: permitReserved,
    memberNotificationBudgetRemaining: budgetRemaining,
    onboardingRequested: body.onboardingRequested,
    onboardingCompleted: onboardingCompleted
  };
}

function protocolReceipt() {
  return {
    appName: NOTIFICATION_PROTOCOL_ID,
    notificationPolicyVersion: NOTIFICATION_POLICY_VERSION,
    notificationModes: [NOTIFICATION_MODE_SUPPRESS, NOTIFICATION_MODE_PERMIT],
    memberNotificationLimit: 1,
    memberNotificationWindowSeconds: MEMBER_NOTIFICATION_WINDOW_MS / 1000,
    onboardingProtocolVersion: ONBOARDING_PROTOCOL_VERSION
  };
}

function deferredResponse(body, issue, plan, action, budgetRemaining) {
  return Object.assign({
    result: 'deferred',
    action: action,
    plannedAction: plan.action,
    issueId: issue ? issue.id : null,
    reviewStage: issue ? stageName(issue) : null,
    plexUserId: body.plexUserId
  }, receipt(body, true, false, budgetRemaining, false));
}

function plannedResponse(body, issue, plan, budgetRemaining) {
  return Object.assign({
    result: 'planned',
    action: plan.action,
    plannedAction: plan.action,
    issueId: issue ? issue.id : null,
    reviewStage: issue ? stageName(issue) : null,
    plexUserId: body.plexUserId
  }, receipt(
    body,
    false,
    false,
    budgetRemaining,
    body.onboardingRequested && plan.action === ONBOARDING_EXISTING_TICKET_ACTION
  ));
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

        const now = Date.now();
        let body;
        try {
          body = validatePayload(ctx.request.json(), now);
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

        let budget;
        try {
          budget = notificationBudget(ctx, now);
        } catch (error) {
          replyError(ctx, 503, error.message);
          return;
        }

        if (!issue && !body.reviewNeeded && !body.onboardingRequested) {
          ctx.response.json(plannedResponse(
            body,
            null,
            {action: 'facts-only'},
            budget.remaining
          ));
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
        if (sameUser(ctx.currentUser, reporter)) {
          replyError(
            ctx,
            403,
            'The CMA account-audit caller cannot be the ticket reporter'
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

        const permitRequired = isMemberNotificationCandidate(issue, plan);
        if (!permitRequired) {
          // Both protocol modes are read-only until a member-visible operation
          // requires and successfully reserves the single global permit.
          ctx.response.json(plannedResponse(body, issue, plan, budget.remaining));
          return;
        }
        if (permitRequired && body.notificationMode === NOTIFICATION_MODE_SUPPRESS) {
          ctx.response.json(deferredResponse(
            body,
            issue,
            plan,
            NOTIFICATION_DEFERRED_ACTION,
            budget.remaining
          ));
          return;
        }
        if (permitRequired && !budget.available) {
          ctx.response.json(deferredResponse(
            body,
            issue,
            plan,
            NOTIFICATION_BUDGET_EXHAUSTED_ACTION,
            0
          ));
          return;
        }

        const permitReserved = permitRequired &&
          body.notificationMode === NOTIFICATION_MODE_PERMIT;
        if (permitReserved) {
          // Reserve the global allowance before creating or changing an issue.
          // Any later exception escapes this handler so YouTrack rolls the
          // reservation, issue fields and public comments back together.
          reserveNotificationBudget(budget, body, now);
        }

        const created = !issue;
        if (created) {
          issue = new entities.Issue(
            reporter,
            ctx.project,
            plan.action === ONBOARDING_TICKET_CREATED_ACTION ?
              'Welcome to Cameron-Media — ' + body.plexUsername :
              'Account Review — ' + body.plexUsername
          );
          issue.description = plan.action === ONBOARDING_TICKET_CREATED_ACTION ?
            buildOnboardingDescription(body) :
            buildDescription(body);
        }

        // Keep every write in the request transaction. Mutation exceptions must
        // escape so YouTrack rolls the whole update back instead of acknowledging
        // a partial audit.
        applyFacts(issue, body, values);
        applyReviewDecision(issue, plan, values);
        if (plan.action !== TICKET_CREATED_AWAITING_NOTICE_ACTION) {
          issue.fields['Account Audit Confirmed At'] = now;
        }
        ctx.response.json(Object.assign({
          result: created ? 'created' : 'updated',
          action: plan.action,
          plannedAction: plan.action,
          issueId: issue.id,
          reviewStage: stageName(issue),
          plexUserId: body.plexUserId
        }, receipt(
          body,
          permitRequired,
          permitReserved,
          budget.remaining,
          body.onboardingRequested &&
            (plan.action === ONBOARDING_TICKET_CREATED_ACTION ||
             plan.action === ONBOARDING_EXISTING_TICKET_ACTION)
        )));
      }
    },
    {
      scope: 'project',
      method: 'GET',
      path: 'protocol',
      permissions: ['UPDATE_ISSUE'],
      handle: function(ctx) {
        if (ctx.project.shortName !== PROJECT_ID) {
          replyError(ctx, 403, 'This endpoint can only be used with the CMA project');
          return;
        }
        try {
          // Validate the declared storage and any persisted reservation without
          // changing either. The worker requires this exact read-only receipt
          // before it enumerates accounts or calls the sync endpoint.
          notificationBudget(ctx, Date.now());
        } catch (error) {
          replyError(ctx, 503, error.message);
          return;
        }
        ctx.response.json(protocolReceipt());
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
