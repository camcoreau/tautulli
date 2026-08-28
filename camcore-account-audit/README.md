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
- New inactive and never-used reviews begin at `Inactivity Notice`. The CMA
  YouTrack workflow owns the later seven-day notice and grace-period transitions.
- Missing or malformed Tautulli play counts, inconsistent play timestamps, and
  malformed watch-duration values abort the whole audit batch before any YouTrack
  synchronization. Plays greater than zero require a positive last-streamed
  timestamp; zero plays require no timestamp. Timestamps more than five minutes
  in the future are rejected.

The 14-day timer is based on the first time this worker observes a zero-play
account because Tautulli does not expose a reliable share-created timestamp in
the users-table API. The small registry at `/data/registry.json` preserves that
observation date across restarts.

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
2. Start from `compose.example.yml` and attach the service to the network that can
   reach Tautulli. Set `CMA_ACCOUNT_AUDIT_IMAGE` to the immutable `master-<sha>`
   image tag published by the release workflow.
3. Leave `DRY_RUN=true` for the first run and confirm the JSON decisions in logs.
4. Change `DRY_RUN=false` and redeploy after the decisions are reviewed.

`AUDIT_INTERVAL_SECONDS=86400` runs the worker daily. Set it to `0` for a
one-shot job driven by an external scheduler.

## Local validation

```bash
python -m unittest discover -s camcore-account-audit/tests -v
python -m py_compile camcore-account-audit/audit.py
```
