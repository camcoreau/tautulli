# OPS-271: onboarding confirmation content correction

Status: proposal for PR review; not deployed or accepted live. Controlling
records: OPS-271 and CMA-A-1. The initial approval on 5 September 2026 covered
preparation and offline tests. Subsequent approval, recorded at 18:51 AEST,
authorizes a narrow commit, fix-branch push and PR against master only. It does
not authorize merge, auto-merge, image publication, deployment, a live template
save or another email. Existing PR validation builds without publishing images
and may upload its normal review ZIP artifacts; no workflow trigger is changed.

## Observed defect and narrow correction

The staff-controlled CMA-22 creation email arrived on 5 September at 17:33 AEST.
Delivery succeeded, but its subject/body acknowledged an inbound administration
request instead of welcoming the new Cameron-Media member. The earlier
channel-metadata delivery hypothesis was withdrawn. The received layout matched
the online-form confirmation component. This proposal changes only that
component's CMA welcome branch, subject to live adapter/preview verification.
It does not edit the email-channel confirmation component.

App draft 1.3.2 adds a versioned formatting marker only to NEW onboarding
descriptions. The two proposed templates require all of:

- A readable CMA issue ID matching `CMA-[1-9][0-9]*` exactly.
- Exact summary `Welcome to Cameron-Media — Your access is ready`.
- Description beginning with `<!-- CamCore:CMA:onboarding:v1 -->`, a blank line,
  and the exact `## Welcome to Cameron-Media` heading plus newline.

LF and CRLF description line endings are accepted. Missing, null or non-string
summary/description and malformed IDs cannot select the welcome branch. This is
a formatting selector, NOT a security/authentication boundary: people who can
edit tickets can copy its marker. The branch contains only fixed public service
information. It never renders the description or username as HTML, changes a
recipient, sends an email itself, or grants access. A platform-supplied ticket
link is HTML-escaped; its origin and authorization remain YouTrack's responsibility.

The welcome has the approved Plex/Apps, CamCore, Media Requests, Service Status
and help links. Reply wording honors `commentFromReply`; it does not promise
email replies are attached when that flag is false. The main brand header and
logo reference are unchanged. A welcome-only footer is inlined in this body so
the shared live `helpdesk_footer.ftl` is NOT changed.

Existing tickets, including unmarked CMA-22, are not migrated, resent, reopened
or marked. App retries still find the lifetime ticket and perform no new send.
New welcome tickets remain Solved at Active review stage. No sender, lifecycle,
catch-up, Support, Operations, Reporter provisioning, worker, registry, budget
or Plex-access changes are part of this patch. The one-global-operation per
rolling 24 hours limit is unchanged.

## Files and provenance

`baseline/` is a read-only source capture from the CMA project override editor
on 5 September 2026. It contains the original online-form subject/body and
shared footer, solely for local comparison and rollback planning. CodeMirror
DOM whitespace was normalized: NBSP to ordinary space, zero-width empty-line
glyph to blank, LF endings, then one final newline. Its hash is NOT a claim
about raw server storage bytes. Independent DOM character/line counts and FNV
readback checks are in the tests; SHA-256 applies to local canonical artifacts.

`selector.ftl` and `welcome-content.ftl` are review source fragments.
`build_templates.py` deterministically produces exactly two standalone FTL
templates plus their checksum manifest. The fragments need not be installed in
YouTrack. No shared template file is produced for deployment. Unique source
anchors fail loudly if the captured baseline is changed. Always recapture and
diff the live overrides before a future save; do not overwrite intervening edits.

## Offline verification

The harness runs real Apache FreeMarker 2.3.34 using Java; it does NOT emulate
the FTL grammar. `issue` is a map standing in for YouTrack's documented adapter,
and `l10n` is a passthrough. The shared footer is the actual captured source.
The unexported `helpdesk_head_styles.ftl` include is a simple local head/meta
stub. Therefore offline output does not establish live adapter behavior, server
FreeMarker-version compatibility, email-client rendering, delivery or final
recipient-visible acceptance.

The test fixture calls the actual app's `buildOnboardingDescription` and
`buildDescription` functions in a Node VM without YouTrack clients. Tests cover
both reply modes, CRLF, hostile description/username/subject values, escaping,
header preservation and 19 non-onboarding cases. Each negative case compares
both subject and body byte-for-byte against the baseline in both reply modes
(76 comparisons). No real member identity, live ticket link or credential is
used in these fixtures. The rendered preview's `example.invalid` ticket button
is deliberately non-functional.

Dependencies (keep outside the repository):

- Java 17 from the official Adoptium distribution.
- Maven Central `org.freemarker:freemarker:2.3.34` JAR SHA-256
  `9a9fb91cd64199232eb1ca9766148a5d30ef8944be5fac051018f96c70c8f6a3`.
- Python 3 and Node.js.

Set `CMA_TEST_JAVA`, `CMA_TEST_JAVAC`, `CMA_TEST_FREEMARKER_JAR` and
`CMA_TEST_NODE` to the local runtimes. Optionally set `CMA_TEST_PREVIEW_DIR`
to a disposable output directory. From the repository root:

```text
python -m unittest discover -s youtrack-notifications/cma-onboarding/tests -v
python -m unittest discover -s camcore-account-audit/tests -v
node youtrack-app/cma-account-audit/tests/test-account-sync.js
python youtrack-notifications/cma-onboarding/build_templates.py --output <review-output-directory>
python .github/scripts/package_cma_account_audit.py --output <review-output-directory>/cma-account-audit-1.3.2.zip
```

The existing nine other workflow JS suites must also pass. No workflow or image
build/publish trigger is changed by this proposal. These new renderer tests are
currently a manual offline gate, not a claimed GitHub Actions result.

## Separate deployment and live acceptance gate (not authorized here)

1. Record exact app/template hashes, current state, scope and rollback in OPS-271
   and CMA-A-1, then obtain action-time deployment approval. Confirm no intervening
   app or template change. Do not infer permission to restart a worker, publish
   an image, or activate Reporter provisioning.
2. Under that separate scope, verify YouTrack's real notification adapter can
   read the raw marker, summary and readable ID. Preview positive and negative
   fixtures using only staff-controlled data and no delivery. If the raw marker
   is stripped or the component differs, stop: do not broaden the selector or
   silently edit another template.
3. Coordinate the app marker update and the two project overrides so no eligible
   member operation can occur between partial changes. Template-first minimizes
   the partial-state effect but is not a substitute for a verified quiet window.
   A required worker pause/configuration change needs explicit scope/approval.
4. Re-read every saved value, confirm unchanged sender settings, shared templates,
   detached catch-up, project attachments and rolling budget history. Rollback
   restores only the prior app and these two overrides after checking intervening
   edits. Never roll back registry/permit history or undo delivered emails.
5. A new send remains separately gated and must be staff-only, constrained to one
   synthetic identity and one global allowance. Do not repurpose a real member,
   reopen CMA-22, reuse a completed lifetime ticket as a new-send test, or bypass
   its idempotency. The 5 September 17:30 operation consumed the current allowance;
   the earliest subsequent slot is approximately 6 September 17:30 AEST, subject
   to a fresh authoritative budget check and any intervening reservation.
6. Require one correct delivered welcome, one Solved lifetime ticket, unchanged
   seat count, and a same-identity repeat with no new ticket/comment/permit/email.
   Observe beyond the delivery queue delay and distinguish delivery from content.
   Keep full production Reporter onboarding activation separately gated until
   all identity and notification acceptance conditions pass.

References: [JetBrains notification template language](https://www.jetbrains.com/help/youtrack/server/notification-template-language-reference.html),
[JetBrains template configuration](https://www.jetbrains.com/help/youtrack/server/notification-templates.html),
[Apache FreeMarker 2.3.34](https://freemarker.apache.org/docs/versions_2_3_34.html).
