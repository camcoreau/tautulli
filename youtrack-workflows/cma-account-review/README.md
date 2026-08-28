# CMA account review workflow

This directory mirrors the project-specific workflow currently attached only to
the `CMA` Helpdesk project. It is kept in source control for review and recovery.

- `lifecycle-transitions.js` applies field and state outcomes when a stage changes.
- `audit-freshness-bridge.js` consumes a private, transient audit-confirmation
  pulse, stores it in app-owned issue state, completes a prepared message and
  evaluates review clocks in the same successful audit transaction.
- `notice-escalation.js` contains the seven-day notice decision used by that
  bridge, including automatic retention when streaming has resumed.
- `deadline-transitions.js` contains the six-day reminder and final 24-hour
  decisions used by the bridge.
- `communications.js` holds the approved public Helpdesk message text and a
  persistent per-stage delivery state machine.
- `stage-communications.js` posts the matching public message immediately when
  a review stage changes. YouTrack emails the public comment to the reporter.
- `lifecycle-catchup.js` normalizes incomplete legacy ticket fields without
  using message delivery state to rewrite lifecycle dates.
- `communication-catchup.js` retries only pending manual `Access Retained` and
  `Access Removed` confirmations once daily. It cannot release a telemetry-driven
  notice.
- `reporter-replies.js` treats any public reply from the ticket reporter as a
  conservative request to retain access and moves the review to
  `Access Retained`.

The messages for inactivity, never-used accounts, subject-to-deletion, final
reminder, access retained and access removed are automatic. Each stage change
creates a durable delivery token stored in YouTrack extension properties. The
event rule, audit bridge and manual-outcome retry share that token, so a prepared
delivery can complete once without posting twice. If a reporter is missing for a
telemetry notice, only a later successful audit pulse can release it and reset
its promised period from the actual delivery time. A comment-creation exception
is deliberately not swallowed, so YouTrack rolls the whole stage-change
transaction back. Historical tickets have no trustworthy cycle identifier, so
recovery leaves them completely untouched: it sends no comment, writes no
delivery state and cannot invent a pending delivery. This prevents bulk catch-up
updates or mail. A fresh stage transition is the only way to start a v2 delivery
cycle.

Telemetry-driven messages and transitions require a successful per-account
audit. The account-audit app writes `Account Audit Confirmed At` as a private
date-and-time pulse. The bridge copies the exact timestamp into this workflow's
extension storage and clears the field inside the same transaction. Review
clocks are evaluated only by that bridge; there is no hourly escalation fallback
that can advance a ticket when an audit fails or omits the account. Missing,
future, 24-hour-old or pre-message evidence fails closed. Manual `Access
Retained` and `Access Removed` confirmations remain available without telemetry.

Lifecycle deadlines use the exact successful public-comment timestamp, not the
date-only `Inactivity Notice Sent` or `Grace Period Ends` fields. The full seven
days, six-day reminder interval and final 24 hours must elapse as timestamps.
This prevents timezone normalization from changing duplicate detection or
shortening a promised response period.
Resumed Tautulli activity and reporter replies both retain access automatically.
The hourly repair pass also retains active legacy tickets that are still pending
and changes open review tickets from `New` to `Pending`. Internal legacy repairs
are notification-muted and cannot create a public Helpdesk message.

## Reviewed upload package

From the repository root, run:

```text
python .github/scripts/package_cma_workflow.py
```

This creates `dist/cma-account-review.zip` with only the two root JSON files and
the nine production workflow scripts. The builder rejects missing or unexpected
scripts, validates the delivery-property declaration and app identity, and checks
the archive inventory and integrity. Source line endings are normalized, so the
same reviewed text produces the same package on Windows and Linux. CI prints its
SHA-256 and publishes this same ZIP as the `cma-account-review-workflow` artifact.

Upload the ZIP as an update to the existing `cma-account-review` app. Do not
delete and recreate the app, because removing it also removes its stored delivery
properties.

## Guarded production update

The automated tests use API mocks; the live YouTrack server must still compile
the uploaded app and persist its extension properties. Use this order:

1. Keep `communication-catchup` detached, pause the external CMA account-audit
   worker and freeze other CMA stage changes.
2. Create `Account Audit Confirmed At` as an optional, private, CMA-only `date and
   time` field. Do not auto-attach it to any other project.
3. Upload the same-name workflow app in place first. Confirm it is CMA-only, the
   bridge compiled and the old hourly notice/deadline rules no longer exist.
4. Upload the same-name account-audit app in place and confirm it is CMA-only.
5. Use one harmless ticket whose reporter is CamCore staff. A successful sync
   must leave the transient field empty after the bridge stores the pulse
   privately. Verify one message, its delivery properties, one audit-driven
   transition and repeated checks with no duplicate.
6. Review a worker dry run, deploy its immutable image, then resume the worker.
   Reattach the manual-outcome retry only after the canary is clean.

Do not use a real member ticket as the canary. If a change freeze cannot be
guaranteed, validate on a separate YouTrack instance instead.

None of these rules can remove Plex access. `Removal Due` remains a manual queue.
After an administrator removes the Cameron-Media share in Plex, they set
`Review Stage` to `Access Removed`; the workflow records the outcome and removal
date, records the acting administrator when available, solves the ticket and
sends the confirmation message. The workflow also derives `Removal Reason` from
the account status when a review begins.
