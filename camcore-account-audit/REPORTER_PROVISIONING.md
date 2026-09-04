# CMA Helpdesk reporter provisioning

> **STATUS: PARKED — not in use as of 4 September 2026. See OPS-271.**
>
> This feature was armed and executed once, on 3 September 2026 at 20:06 AEST, creating two accounts intended to be Reporters that were subsequently observed to consume licence seats and were removed the following day.
>
> Provisioning is gated on the in-source constant `REPORTER_PROVISIONING_ENABLED` in `runner.py`, currently `False`. While parked:
>
> - `runner.main()` does **not** call `install()`. The ordinary `audit.YouTrackClient` stays active and `ReporterProvisioner` is never constructed, so its unconditional `YOUTRACK_HUB_URL` validation never runs either.
> - Supplying `YOUTRACK_REPORTER_PROVISION_TOKEN` makes the worker **exit 2 at startup**, before the scheduled run loop begins, emitting `{"event": "startup-aborted"}` on stderr. It does not silently re-arm.
> - Both `YOUTRACK_REPORTER_PROVISION_TOKEN` and `YOUTRACK_HUB_URL` have been removed from `compose.example.yml`.
>
> Re-enabling requires a reviewed source change and a new pinned image. It cannot be done by configuration alone.
>
> **Do not re-arm before resolving why accounts created with `userType: REPORTER` consumed licence seats.** Any test of that question must use a test instance or a staff-controlled synthetic identity, never a real member.
>
> Reporter creation is currently a manual step performed at Plex onboarding time.
>
> The sections below describe the feature as designed, and apply only if it is un-parked.

The CMA account-audit worker can provision a missing YouTrack Helpdesk Reporter account when a genuinely new Plex member is first observed after the onboarding baseline.

## Why this exists

A new Plex member may already be visible in Tautulli before they have ever contacted the CamCore Helpdesk. In that state the CMA YouTrack app cannot create the member's lifetime welcome ticket because `User.findUniqueByEmail(...)` has no reporter to attach to the ticket.

The production runner now treats that exact onboarding-only condition as recoverable. It creates a Reporter-type user in YouTrack Hub, waits for the account to become visible to YouTrack, and retries the same read-only suppress request. The normal notification gate still decides whether a welcome ticket can be created.

## Safety boundaries

Reporter provisioning is deliberately narrower than the CMA ticket-sync token.

- `YOUTRACK_TOKEN` remains the CMA project-scoped token used by the account-sync app.
- `YOUTRACK_REPORTER_PROVISION_TOKEN` must be a separate token. The runner rejects a configuration that reuses `YOUTRACK_TOKEN`.
- The provisioning identity needs only the user-management permissions required to look up and create users: `Read User Basic` and `Create User`.
- Do not grant the provisioning identity project roles, Support access, Operations access, or CMA issue mutation permissions.
- Provisioning is attempted only when all of the following are true:
  - the worker is live (`DRY_RUN=false`);
  - the registry already marks the Plex account as pending onboarding;
  - the YouTrack app returns the exact deterministic `reporter-match-unavailable` response;
  - the request is the read-only `suppress` phase.
- Dry-run never provisions users.
- Permit mode never provisions users.
- A non-exact or duplicate Hub email lookup fails closed.
- The reporter login is deterministic from the stable Plex user ID and does not expose the member email address.
- The member email is stored as an unverified contact. The automation does not falsely mark ownership of the email address as verified.
- Reporter creation itself does not bypass the one-member-notification-per-24-hours gate. Welcome-ticket creation still requires the normal permit.
- If the newly created Reporter account does not become a unique YouTrack email match after bounded read-only retries, the entire audit cycle fails closed instead of continuing with an ambiguous identity.

## Required settings

```text
YOUTRACK_REPORTER_PROVISION_TOKEN=<dedicated permanent token>
YOUTRACK_HUB_URL=https://support.camcore.au/hub/api/rest
```

`YOUTRACK_HUB_URL` defaults to `/hub/api/rest` on the same scheme and host as the configured YouTrack sync endpoint. The runner rejects a different host so the provisioning token cannot be sent to an unrelated service through configuration error.

## Reactivation gate

There is **no approved production rollout procedure for this feature.** The previous rollout
steps were removed deliberately: they restored the shared production worker to `DRY_RUN=false`
before the canary, which would point a provisioning-enabled all-account worker at the live
Tautulli inventory. That is the exact hazard this gate exists to prevent.

Before reporter provisioning may be reactivated:

- Reporter provisioning remains **parked**. It has no approved production rollout procedure.
- Reactivation requires a **separate reviewed PR and validation plan**, prepared only after the
  cause of licence-seat consumption by accounts created with `userType: REPORTER` has been
  resolved.
- Any user-creation canary must run through an **isolated one-shot harness whose input contains
  exactly one staff-controlled synthetic identity**.
- **Never point a provisioning-enabled all-account worker at the live Tautulli inventory during a
  canary.**
- The **shared production worker stays unchanged throughout canary validation** - not
  reconfigured, not restarted, not switched out of its current mode.
- **Canary completion does not authorize production.** Activation requires separate explicit
  approval.

## Rollback

Remove `YOUTRACK_REPORTER_PROVISION_TOKEN` and redeploy or restart the worker. With no provisioning token the runner preserves the previous behavior: a missing reporter remains pending and is skipped with `reporter-match-unavailable` until the identity exists by another route.
