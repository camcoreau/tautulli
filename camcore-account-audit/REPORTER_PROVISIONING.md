# CMA Helpdesk reporter provisioning

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

## Rollout

1. Create or use a dedicated YouTrack service identity for Reporter provisioning.
2. Grant only `Read User Basic` and `Create User`.
3. Create a permanent token for that identity and store it in the deployment secret store as `YOUTRACK_REPORTER_PROVISION_TOKEN`.
4. Deploy the immutable CMA account-audit image with the existing registry, network and CMA token unchanged.
5. Keep `DRY_RUN=true` for the first image validation. Dry-run must not call Hub user creation.
6. Confirm the image and tests are clean, then restore the existing production `DRY_RUN=false` configuration.
7. Use one pending new Plex member as the canary. The first live suppress pass should emit a `reporter-provisioned` event and then return an onboarding notification candidate.
8. Do not force a notification permit. Let the existing rolling 24-hour gate determine when the welcome ticket is allowed to be created.
9. Confirm the created reporter has the expected email, the CMA ticket is reported by that user, and the member receives the expected Helpdesk welcome notification before declaring the change fully validated.

## Rollback

Remove `YOUTRACK_REPORTER_PROVISION_TOKEN` and redeploy or restart the worker. With no provisioning token the runner preserves the previous behavior: a missing reporter remains pending and is skipped with `reporter-match-unavailable` until the identity exists by another route.
