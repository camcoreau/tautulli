# Packaging

YouTrack imports JavaScript workflows as ZIP archives. Build the CamCore workflow
archive from this directory so `manifest.json` and `overdue-notifications.js` are
at the root of the ZIP:

```bash
zip -j camcore-due-date-notifications.zip manifest.json overdue-notifications.js
```

The repository-only `tests`, `README.md`, `CHANGELOG.md`, `.gitignore` and this
file are intentionally excluded from the uploaded workflow archive.
