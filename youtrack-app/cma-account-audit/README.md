# CMA Account Audit YouTrack app

This project-scoped app exposes one authenticated endpoint:

```text
POST /api/admin/projects/CMA/extensionEndpoints/cma-account-audit/account-sync/sync-account
```

It uses the stable `Plex User ID` to update the same account ticket on every
daily audit. Exact `Plex Username` matching is a one-time fallback that lets the
first run backfill IDs onto tickets that predate the integration.

New tickets are constructed with the unique YouTrack user whose email matches the
Plex email. This preserves the Helpdesk reporter relationship so public comments
continue to reach the member. A missing or ambiguous reporter returns HTTP 422;
the app never silently substitutes the automation account.

Because an agent-created Helpdesk ticket can itself email the reporter, a new
review uses two permit windows. The first permitted request creates the ticket
at the non-message `Active` review stage with action
`ticket-created-awaiting-notice`; it does not set `Account Audit Confirmed At`
or enter `Inactivity Notice`. On a later eligible daily cycle, the existing
`Active` ticket plans `notice-started` and a fresh permit releases the one public
inactivity notice. This prevents one request from producing both a ticket-created
email and a lifecycle-comment email.

The app must only be attached and activated for `CMA`. Its endpoint also rejects
any other project short name.

Every request is validated against the canonical account-state matrix before a
ticket lookup. Existing tickets must have the same unique Helpdesk reporter as
the incoming Plex email, and all required project fields and enum values are
preflighted before any write. Apart from the intentionally unstamped staged
ticket-creation action, a successful atomic update pulses the private `Account
Audit Confirmed At` date-and-time field for the CMA workflow to consume; failed
or ambiguous requests never stamp freshness.

## Fail-closed notification protocol

The project-scoped `GET protocol` endpoint is read-only. It validates the app's
global budget storage and returns a closed receipt containing the app identity,
policy version, supported modes, notification limit and window. Live workers
must validate that exact receipt before they enumerate Tautulli accounts or send
any `sync-account` request. Version 1.1 has no protocol endpoint, so deploying a
new live worker before this in-place app update fails before ticket mutations.

Protocol version 1 requires every request to include one audit `cycleId` and a
`notificationMode` of either `suppress` or `permit`. Every successful response
echoes the policy version, mode, cycle ID and Plex user ID, and includes
`plannedAction`, `memberNotificationPermitRequired`,
`memberNotificationPermitReserved` and
`memberNotificationBudgetRemaining`. The worker rejects missing, incompatible
or contradictory receipts.

The worker first submits the complete audit in `suppress` mode. This pass is
universally read-only: it can search, validate and plan, but cannot change issue
facts, create tickets, pulse audit freshness, change review stages, write
`AppGlobalStorage` or add comments. A notification candidate returns
`deferred/member-notification-deferred`; every non-candidate returns the strict
`planned` receipt without writes.

After a clean suppress pass, the worker may repeat exactly one selected
candidate in `permit` mode. The app atomically stores one permit in
`AppGlobalStorage` before issue side effects. That server-side reservation
allows at most one member notification across all workers in a rolling 24-hour
window, measured from its `reservedAt` timestamp. If the window has not elapsed,
the endpoint returns `deferred/member-notification-budget-exhausted` with no
issue writes. If the operation is no longer a candidate, permit mode also returns
`planned` without reserving or writing. Thus issue mutations occur only after a
required global permit has been successfully reserved. A local registry
reservation provides a second durable gate and is
persisted before the permit request, so network ambiguity cannot safely be
retried as a new notification.

Install this app update before deploying a worker that uses the protocol. The
new live worker deliberately rejects a missing or incompatible read-only
handshake before account enumeration; it must remain in dry-run until the
in-place CMA-only app update and a staff-only canary have been verified.

## Package

From the repository root, run:

```text
python .github/scripts/package_cma_account_audit.py
```

This creates `dist/cma-account-audit.zip` with only `manifest.json`,
`entity-extensions.json` and `account-sync.js` at the archive root. The entity
extension declares the three `AppGlobalStorage` budget properties. The builder
normalizes source line endings; CI prints the ZIP's SHA-256 and publishes it as
the `cma-account-audit-app` artifact. Upload it as an in-place update from
YouTrack Administration > Apps; do not create a duplicate app. If a separately
reviewed release also changes the CMA workflow bridge, install that same-name
workflow update first; otherwise leave the workflow untouched. Keep this app
attached only to Cameron-Media Account Administration.

Updating this app does not authorize changes to Support, Operations overdue
workflows, CMA lifecycle rules or public message text, sender configuration,
real ticket reporters, Plex access, or the detached `communication-catchup`
rule.
