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

Every request is validated against the canonical account-state matrix before a
ticket lookup. Existing tickets must have the same unique Helpdesk reporter as
the incoming Plex email, and all required project fields and enum values are
preflighted before any write. A successful atomic update pulses the private
`Account Audit Confirmed At` date-and-time field for the CMA workflow to consume;
failed or ambiguous requests never stamp freshness.

## Package

From the repository root, run:

```text
python .github/scripts/package_cma_account_audit.py
```

This creates `dist/cma-account-audit.zip` with only `manifest.json` and
`account-sync.js` at the archive root. The builder normalizes source line endings;
CI prints the ZIP's SHA-256 and publishes it as the `cma-account-audit-app`
artifact. Upload it as an in-place update from YouTrack Administration > Apps;
do not create a duplicate app. Install the updated CMA workflow bridge first,
and keep this app attached only to Cameron-Media Account Administration.
