# Changelog

## 1.0.0 — 2026-08-27

- Add a CamCore-branded replacement for YouTrack's stock overdue issue email.
- Preserve the stock unresolved issue search, weekday 10:00 schedule, overdue guard,
  assignee recipient and project-leader fallback.
- Replace JetBrains/YouTrack subject and footer presentation with CamCore Operations
  branding and CamCore Tasks, Service Status and Support links.
- Render due dates as Melbourne calendar dates without the confusing stored 22:00
  time shown for YouTrack date fields in AEST/AEDT clients.
- Escape issue-controlled content before rendering it in HTML email.
