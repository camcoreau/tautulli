# Cameron-Media account audit worker

This worker reads the Tautulli users table and synchronizes account-review facts
into the `CMA` YouTrack Helpdesk project. It is intentionally unable to remove
Plex access. The final destructive action remains an administrator task in the
`Removal Due` queue.

## Policy

- A user becomes `Inactive` when their last stream is at least 60 days old.
- A zero-play account becomes reviewable after it has been observed for 14 days.
- `Guest` and `Local` are always excluded, case-insensitively.
- The stable Plex user ID is the idempotency key. Repeated runs update the same
  ticket instead of creating duplicates. If the ID and username resolve to
  different tickets, synchronization stops without changing either ticket.
- Accounts that stream again while a review is pending move to `Access Retained`.
- A retained ticket cannot restart from the same inactive evidence. It must first
  receive an `Active` audit result, then later become reviewable again.
- New inactive and never-used reviews are first staged at non-message `Active`;
  a later permitted cycle begins `Inactivity Notice`. The CMA YouTrack workflow
  owns the later seven-day notice and grace-period transitions.
- Missing or malformed Tautulli play counts, inconsistent play timestamps, and
  malformed watch-duration values abort the whole audit batch before any YouTrack
  synchronization. Plays greater than zero require a positive last-streamed
  timestamp; zero plays require no timestamp. Timestamps more than five minutes
  in the future are rejected.

The 14-day timer is based on the first time this worker observes a zero-play
account because Tautulli does not expose a reliable share-created timestamp in
the users-table API. The small registry at `/data/registry.json` preserves that
observation date across restarts.

## Member-notification safety gate

Live audit cycles use a fail-closed, two-pass protocol so the account-audit
system can permit no more than one member-visible notification in any rolling
24-hour window:

1. Before it reads the Tautulli account inventory, the live worker calls the
   app's read-only `protocol` endpoint and requires the exact reviewed policy,
   modes, one-notification limit and 24-hour window. The legacy app has no such
   endpoint, so a wrong-order worker deployment stops before any account sync
   request can mutate a ticket.
2. The worker sends every account through a `suppress` pass using one unique
   cycle ID. Every suppress request is read-only, including non-candidates: it
   may search, validate and plan, but cannot change facts, create tickets, pulse
   audit freshness, change stages, write global storage or add comments. A
   candidate returns a deferred receipt; a non-candidate returns strict
   `planned`.
3. Only when every suppress response is valid and the pass has no errors may the
   worker select one candidate deterministically. Persisted per-Plex-user permit
   timestamps rotate the backlog toward the least recently permitted candidate.
   The worker atomically records that history and a durable local reservation in
   the registry before repeating exactly that account in `permit` mode. All
   other candidates remain deferred.
4. The YouTrack app atomically reserves its independent `AppGlobalStorage`
   budget before any issue side effects. An unavailable server budget returns a
   determinate deferral with no issue writes. A permit request that is no longer
   a candidate also returns `planned` without reserving or writing. The endpoint
   mutates an issue only when a notification permit is required and the global
   reservation has succeeded.

New Helpdesk reviews are deliberately staged across two eligible daily permits.
The first creates an `Active` ticket without an audit pulse or lifecycle comment;
the second later transitions that existing ticket to `Inactivity Notice`. The
worker ranks an existing first notice ahead of creating another ticket so the
split sequence can complete without releasing two member emails in one window.

The local reservation and server budget both use a rolling 24-hour window. The
server budget prevents a second worker or a restored local registry from
bypassing the cap. Persisting the local reservation before the permit request
means a timeout or ambiguous response consumes the local window instead of
risking a duplicate notification.

Live mode completes its protocol handshake first. Every live or dry-run cycle
then acquires an exclusive, non-blocking process lock beside its selected
registry (for example, `/data/registry.json.lock`). The lock is held from
registry load through Tautulli enumeration, all YouTrack requests and the final
registry save. A second worker that targets the same registry fails before
inventory enumeration or synchronization instead of racing a permit. The small
lock file remains on disk intentionally; the operating-system lock is released
when the cycle exits or the process stops.

The registry deliberately retains `schemaVersion: 1`. The new notification gate
and per-user history are additional top-level keys, so the previous worker can
load the registry and preserves those keys when it saves. A previous-image
rollback must still remain `DRY_RUN=true` with the version 1.2 app installed:
the old worker does not understand the notification protocol, and its legacy
live requests are intentionally rejected by the updated app.

A cycle updates `lastCompletedAt` only after every required response is
determinate. Suppress errors, incompatible receipts and ambiguous permit calls
leave `lastCompletedAt` unchanged. The durable notification reservation is
still retained so a restart continues to fail closed. A server-budget deferral
or a valid response that no longer needs a permit is determinate and can safely
complete the cycle.

If two permit transactions race the same available server budget, YouTrack can
commit one and reject the losing transaction with its structured `400 Invalid
properties` optimistic-conflict response. The worker retries only that exact
permit-only conflict once with the identical cycle and payload. The committed
global budget then returns a determinate budget-exhausted receipt; every other
HTTP error, any suppress error, and a second conflict remain fail-closed.

Dry-run mode makes no YouTrack calls and neither reads nor reserves a remote
permit. It records only the local account classification and completion state in
the selected isolated registry.

## Required YouTrack app

Install and attach `youtrack-app/cma-account-audit` to the CMA project before
turning off dry-run mode. Its project-scoped endpoint creates tickets using the
existing Helpdesk reporter account that matches the Plex email address. It
returns HTTP 422 rather than creating a ticket under the automation identity when
there is no unique reporter match.

The service account behind `YOUTRACK_TOKEN` needs these CMA-only permissions:

- Create Issue
- Update Issue
- Read Issue and Read Issue Private Fields
- Update Issue Private Fields

Do not grant the account access to Support or Operations.

## Deployment

1. Store the Tautulli API key and the CMA-scoped YouTrack token in the deployment
   secret store. Never place either value in this repository.
2. Keep the existing worker in dry-run and keep `communication-catchup`
   detached. Upload the same-name `cma-account-audit` app update in place and
   confirm it remains attached only to CMA. The app must be updated before the
   worker because the live worker requires the new read-only handshake and
   rejects legacy or mismatched protocol receipts before account enumeration.
3. Start from `compose.example.yml` and attach the service to the network that can
   reach Tautulli. Set `CMA_ACCOUNT_AUDIT_IMAGE` to the immutable `master-<sha>`
   image tag published by the release workflow.
4. Preserve the live registry, clone it to the isolated dry-run registry and
   deploy the new immutable image with `DRY_RUN=true`. Confirm the JSON decisions
   and projected review set in logs without contacting YouTrack or members.
5. Validate the new app protocol with a staff-only canary. Change to
   `DRY_RUN=false` and `/data/registry.json` only after the canary and fresh
   projection pass the one-notification gate. Keep the immutable image, volume,
   network, secrets and daily interval unchanged during that cutover.

`AUDIT_INTERVAL_SECONDS=86400` runs the worker daily. Set it to `0` for a
one-shot job driven by an external scheduler.

This safety rollout changes only the CMA account-audit app and worker. It does
not reattach `communication-catchup` or change Support, Operations overdue
workflows, CMA lifecycle rules or public message text, sender configuration,
real ticket reporters, or Plex access. The worker remains unable to remove Plex
access.

## Local validation

```bash
python -m unittest discover -s camcore-account-audit/tests -v
python -m py_compile camcore-account-audit/audit.py
```
