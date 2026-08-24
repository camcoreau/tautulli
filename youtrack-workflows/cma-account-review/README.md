# CMA account review workflow

This directory mirrors the project-specific workflow currently attached only to
the `CMA` Helpdesk project. It is kept in source control for review and recovery.

- `lifecycle-transitions.js` applies field and state outcomes when a stage changes.
- `notice-escalation.js` advances a seven-day inactivity notice, or retains an
  account when Tautulli reports a stream on or after the notice date.
- `deadline-transitions.js` moves the seven-day deletion grace period to final
  reminder one day before expiry and to removal due on expiry.

None of these rules can remove Plex access. `Removal Due` remains a manual queue.
