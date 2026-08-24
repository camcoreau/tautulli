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

The app must only be attached and activated for `CMA`. Its endpoint also rejects
any other project short name.

## Package

Create a ZIP with `manifest.json` and `account-sync.js` at the archive root, then
upload it from YouTrack Administration > Apps. Attach the app to Cameron-Media
Account Administration after installation.
