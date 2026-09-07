# CMA Helpdesk Reporter provisioning

> **Status: implemented, off by default (OPS-343).** Activation is a separately
> approved production change recorded on OPS-343. Until then the worker behaves
> exactly as accepted under OPS-271: a new Plex member with no matching YouTrack
> account is skipped fail-closed with `reporter-match-unavailable`.

The CMA account-audit worker can create the missing YouTrack Helpdesk **Reporter**
account for a genuinely new Plex member, so the member's lifetime welcome ticket
and welcome email go out without a manual step.

## Why this exists

A new Plex member is visible in Tautulli before they have ever contacted the
CamCore Helpdesk. The CMA YouTrack app attaches the welcome ticket to the user
that `User.findUniqueByEmail(...)` returns for the Plex email; with no such user
it answers HTTP 422 and the worker skips the member every day.

## What changed since the parked design

The first implementation (3 September 2026) created users through the Hub REST
API with `userType: {"id": "REPORTER"}`. Since YouTrack 2026.1, Hub no longer
persists the user type, so those accounts became licensed Standard users and
consumed seats (OPS-271). JetBrains' current guidance for 2026.1+ is:

```
POST /api/users?fields=id,login,fullName,email,userType(id)
{"login": "...", "fullName": "...", "email": "...", "password": "...",
 "userType": {"id": "REPORTER"}}
```

`password` is required on create. This worker now uses exactly that call. The
Hub path is gone; setting `YOUTRACK_HUB_URL` makes the worker refuse to start.

## How it works

Provisioning is attempted only when **all** of the following hold:

- `REPORTER_PROVISIONING_ENABLED=true` **and** `YOUTRACK_REPORTER_PROVISION_TOKEN`
  is set, and the token differs from `YOUTRACK_TOKEN`;
- the worker is live (`DRY_RUN=false`);
- the request is the read-only `suppress` planning pass;
- the registry marks the Plex account as pending onboarding;
- the CMA app returned the exact deterministic `reporter-match-unavailable`
  response and the account has an email;
- the per-cycle budget (`REPORTER_PROVISIONING_MAX_PER_CYCLE`, default 1) is not
  yet spent; and
- the process-wide circuit breaker has not tripped.

When it runs:

1. **Lookup first.** The worker enumerates `GET /api/users` page by page and
   matches the email exactly (case-insensitive). Any existing account with that
   email, of any type, means nothing is created; the member stays a deterministic
   skip and a `reporter-provisioning-skipped` event names the reason
   (`existing-account-not-unique-match`). If the directory is empty or exposes no
   email at all (missing *Read User Details*), "no match" is not believed and the
   cycle fails closed instead of creating duplicates.
2. **Create.** `POST /api/users` with a deterministic login
   (`cma-plex-<sha256(plexUserId)[:16]>`, never the email), the Plex username as
   `fullName`, the Plex email, a random 32-byte password that is never logged,
   stored or reused (Reporters authenticate by email link), and
   `userType REPORTER`.
3. **Verify.** The create response **and** a fresh `GET /api/users/{id}` readback
   must both carry the requested login, exact email and `REPORTER` type.
4. **Retry the plan.** The worker repeats the same read-only `suppress` request a
   few times; the normal one-member-notification-per-24-hours gate then decides
   when the welcome ticket is actually created. Provisioning never touches permit
   mode, the allowance or the registry history.

### Circuit breaker

If step 3 finds anything other than the requested Reporter identity, the worker
prints `reporter-provisioning-tripped` (with the account id and login, never the
email) to stderr and disables provisioning for the rest of the process. At most
one questionable account can therefore be created per worker lifetime. Correct
or remove that account in *Administration → Users*, then restart the worker.

### Events

- `reporter-provisioning` — startup state (`enabled` / `disabled`, token present,
  max per cycle).
- `reporter-provisioned` — one account created and read back (id, login, type).
- `reporter-provisioning-skipped` — `cycle-budget-exhausted` or
  `existing-account-not-unique-match`.
- `reporter-provisioning-tripped` — breaker tripped; see above.

## Required settings

```text
REPORTER_PROVISIONING_ENABLED=true
YOUTRACK_REPORTER_PROVISION_TOKEN=<dedicated permanent token, YouTrack service only>
REPORTER_PROVISIONING_MAX_PER_CYCLE=1          # optional, default 1
YOUTRACK_API_URL=https://support.camcore.au/api # optional; must be the sync host's /api
```

The provisioning identity needs only *Read User Basic*, *Create User* and *Read
User Details* (email visibility) in Global. Do not grant it project roles,
Support or Operations access, or CMA issue permissions.

## Canary before activation

`tools/reporter_provisioning_canary.py` ships in the image at
`/app/tools/`. Run it from the container console with the worker's normal
environment plus one synthetic identity:

```text
CANARY_PLEX_USER_ID=ops343-<anything>   # must start with ops343-
CANARY_USERNAME=<display name>
CANARY_EMAIL=<staff-controlled mailbox with NO YouTrack account>

python /app/tools/reporter_provisioning_canary.py preview
CANARY_CONFIRM=yes python /app/tools/reporter_provisioning_canary.py run
```

`preview` is read-only and reports user-type counts and whether the email already
matches. `run` creates exactly one Reporter, reads it back, enumerates again and
reports `accepted: true` only when the Reporter count rose by exactly one and no
other user-type count changed. The canary never reads Tautulli, the registry or
the CMA sync endpoint, and never prints a token, password or email address.

Canary completion does not authorise production. Activation
(`REPORTER_PROVISIONING_ENABLED=true` on the production worker) is a separate
explicit approval on OPS-343.

## Rollback

Set `REPORTER_PROVISIONING_ENABLED=false` (or remove the token) and redeploy.
A missing Reporter is then skipped fail-closed until the identity exists by
another route, exactly as before. Never reset the registry or the notification
allowance history as part of a rollback.
