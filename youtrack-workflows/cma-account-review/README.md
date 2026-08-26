# CMA account review workflow

This directory mirrors the project-specific workflow currently attached only to
the `CMA` Helpdesk project. It is kept in source control for review and recovery.

- `lifecycle-transitions.js` applies field and state outcomes when a stage changes.
- `notice-escalation.js` advances a seven-day inactivity notice, or retains an
  account when Tautulli reports a stream on or after the notice date.
- `deadline-transitions.js` moves the seven-day deletion grace period to final
  reminder one day before expiry and to removal due on expiry.
- `communications.js` holds the approved public Helpdesk message text and
  duplicate-prevention helpers.
- `stage-communications.js` posts the matching public message immediately when
  a review stage changes. YouTrack emails the public comment to the reporter.
- `lifecycle-catchup.js` normalizes incomplete legacy tickets before messages
  are sent and starts delayed notice periods from actual delivery.
- `communication-catchup.js` checks hourly for a missing message and posts it
  once, which also brings existing CMA reviews into the automated process.
- `reporter-replies.js` treats any public reply from the ticket reporter as a
  conservative request to retain access and moves the review to
  `Access Retained`.

The messages for inactivity, never-used accounts, subject-to-deletion, final
reminder, access retained and access removed are automatic and repeat-safe within
each review cycle. Resumed Tautulli activity and reporter replies both retain
access automatically. The hourly repair pass also retains active legacy tickets
that are still pending, changes open review tickets from `New` to `Pending`, and
guarantees the full promised seven days when the first notice was delayed.

None of these rules can remove Plex access. `Removal Due` remains a manual queue.
After an administrator removes the Cameron-Media share in Plex, they set
`Review Stage` to `Access Removed`; the workflow records the outcome and removal
date, records the acting administrator when available, solves the ticket and
sends the confirmation message. The workflow also derives `Removal Reason` from
the account status when a review begins.
