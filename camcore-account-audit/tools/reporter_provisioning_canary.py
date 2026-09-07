#!/usr/bin/env python3
"""OPS-343 Reporter-provisioning canary (one synthetic identity, one shot).

Runs inside the production camcore-account-audit container:

    python /app/tools/reporter_provisioning_canary.py preview
    CANARY_CONFIRM=yes python /app/tools/reporter_provisioning_canary.py run

It reuses the worker's reviewed provisioner from /app/runner.py and reads the
dedicated provisioning token only from the process environment. It never reads
Tautulli, never reads or writes the registry, never calls the CMA account-sync
endpoint, and never prints a token, a password or the canary email address.

Identity (all required, supplied by the operator):
    CANARY_PLEX_USER_ID   synthetic Plex user id, never a real member's id
    CANARY_USERNAME       display name for the Reporter (fullName)
    CANARY_EMAIL          a staff-controlled mailbox with NO YouTrack account

Modes:
    preview   enumerate the directory, report user-type counts and whether the
              canary email already matches an account. Read-only.
    run       preview, then exactly one create + readback, then a second
              enumeration. Requires CANARY_CONFIRM=yes. Refuses when the email
              already matches, when the worker is in DRY_RUN, or when the
              process-wide breaker is tripped.

Output: one sanitised JSON receipt on stdout. Exit codes: 0 ok, 2 usage,
3 configuration, 4 directory read failed, 5 held (email already matches or
confirm missing), 6 create/readback failed (see stderr event), 7 unexpected
post-create state.
"""

from __future__ import annotations

import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
for _path in (os.path.dirname(_HERE), "/app"):
    if _path not in sys.path:
        sys.path.insert(0, _path)
import audit  # noqa: E402
import runner  # noqa: E402


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sanitised(exc: BaseException) -> dict:
    out: dict = {"type": type(exc).__name__}
    status = getattr(exc, "status_code", None)
    if status is not None:
        out["httpStatus"] = status
        detail = getattr(exc, "detail", None)
        if isinstance(detail, str):
            try:
                payload = json.loads(detail)
                if isinstance(payload, dict):
                    out["error"] = str(payload.get("error", ""))[:120]
                    out["error_description"] = str(
                        payload.get("error_description", "")
                    )[:200]
            except Exception:  # noqa: BLE001
                pass
    else:
        message = str(exc)
        if "perm" in message.lower() or "bearer" in message.lower():
            message = "<redacted>"
        out["message"] = message[:240]
    return out


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "preview"
    if mode not in ("preview", "run"):
        print(json.dumps({"phase": "args", "error": "mode must be preview or run"}))
        return 2

    receipt: dict = {
        "diagnostic": "OPS-343 reporter-provisioning canary",
        "mode": mode,
        "startedAtUtc": now(),
        "createRequests": 0,
    }

    user_id = os.getenv("CANARY_PLEX_USER_ID", "").strip()
    username = os.getenv("CANARY_USERNAME", "").strip()
    email = os.getenv("CANARY_EMAIL", "").strip()
    if not (user_id and username and email):
        receipt.update(
            phase="args",
            error="CANARY_PLEX_USER_ID, CANARY_USERNAME and CANARY_EMAIL are required",
        )
        print(json.dumps(receipt))
        return 2
    if not user_id.startswith("ops343-"):
        receipt.update(
            phase="args", error="CANARY_PLEX_USER_ID must start with 'ops343-' (synthetic only)"
        )
        print(json.dumps(receipt))
        return 2

    try:
        config = audit.Config.from_env()
        http = audit.JsonHttpClient(config.timeout_seconds)
        # The canary decides enablement itself; the worker's own switch may still
        # be off. A DRY_RUN worker still refuses (enabled property checks it).
        provisioner = runner.ReporterProvisioner(
            config, http, enabled=True, max_per_cycle=1
        )
    except audit.ConfigurationError as exc:
        receipt.update(phase="config", error=sanitised(exc))
        print(json.dumps(receipt))
        return 3

    account = audit.Account(
        user_id=user_id,
        username=username,
        email=email,
        last_streamed=None,
        total_plays=0,
        watch_seconds=0,
    )
    receipt["identity"] = {
        "plexUserId": user_id,
        "username": username,
        "expectedLogin": runner.ReporterProvisioner.login_for(account),
    }
    receipt["youtrackApi"] = provisioner.api_url
    receipt["provisionerEnabled"] = provisioner.enabled
    receipt["dryRun"] = config.dry_run

    try:
        before = provisioner.enumerate_users()
        matches = provisioner.lookup(email)
    except audit.RemoteApiError as exc:
        receipt.update(phase="directory", error=sanitised(exc))
        print(json.dumps(receipt))
        return 4
    receipt["before"] = {
        "users": len(before),
        "userTypeCounts": provisioner.user_type_counts(before),
        "emailMatches": [runner.ReporterProvisioner.public_user(u) for u in matches],
    }

    if mode == "preview":
        receipt["phase"] = "preview-only"
        print(json.dumps(receipt))
        return 0

    if matches:
        receipt.update(phase="held", note="canary email already matches an account; nothing created")
        print(json.dumps(receipt))
        return 5
    if os.getenv("CANARY_CONFIRM", "").strip().lower() != "yes":
        receipt.update(phase="held", note="CANARY_CONFIRM=yes is required to create")
        print(json.dumps(receipt))
        return 5
    if not provisioner.enabled:
        receipt.update(
            phase="held",
            note="provisioner not enabled (DRY_RUN, missing token or breaker tripped)",
            tripped=runner.tripped_reason(),
        )
        print(json.dumps(receipt))
        return 5

    receipt["createRequests"] = 1
    try:
        created = provisioner.create(account)
    except audit.RemoteApiError as exc:
        receipt.update(
            phase="create-failed",
            error=sanitised(exc),
            tripped=runner.tripped_reason(),
        )
        print(json.dumps(receipt))
        return 6
    receipt["created"] = runner.ReporterProvisioner.public_user(created)

    try:
        after = provisioner.enumerate_users()
        after_matches = provisioner.lookup(email)
    except audit.RemoteApiError as exc:
        receipt.update(phase="post-create-directory", error=sanitised(exc))
        print(json.dumps(receipt))
        return 7
    receipt["after"] = {
        "users": len(after),
        "userTypeCounts": provisioner.user_type_counts(after),
        "emailMatches": [runner.ReporterProvisioner.public_user(u) for u in after_matches],
    }
    counts_before = receipt["before"]["userTypeCounts"]
    counts_after = receipt["after"]["userTypeCounts"]
    only_reporter_added = (
        counts_after.get(runner.REPORTER_USER_TYPE_ID, 0)
        == counts_before.get(runner.REPORTER_USER_TYPE_ID, 0) + 1
        and all(
            counts_after.get(key, 0) == counts_before.get(key, 0)
            for key in set(counts_before) | set(counts_after)
            if key != runner.REPORTER_USER_TYPE_ID
        )
    )
    receipt["accepted"] = (
        only_reporter_added
        and len(after_matches) == 1
        and after_matches[0].get("id") == created.get("id")
    )
    receipt["phase"] = "complete"
    receipt["finishedAtUtc"] = now()
    print(json.dumps(receipt))
    return 0 if receipt["accepted"] else 7


if __name__ == "__main__":
    sys.exit(main(sys.argv))
