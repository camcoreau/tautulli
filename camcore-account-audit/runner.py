#!/usr/bin/env python3
"""Run the CMA audit with optional, fail-closed Helpdesk Reporter provisioning.

OPS-343. Reporter provisioning creates a YouTrack Helpdesk *Reporter* account for
a new Plex member who has no YouTrack account matching their Plex email, so the
existing welcome flow (CMA ticket, welcome email, automatic Solved) can proceed
without a manual step.

It uses the YouTrack REST endpoint ``POST /api/users`` with
``userType {"id": "REPORTER"}``, which JetBrains prescribes for YouTrack 2026.1
and later. The earlier Hub-based path (``/hub/api/rest/users``) is gone: since
2026.1 Hub no longer persists the user type, which is how the 3 September 2026
attempt created licensed accounts (OPS-271). Supplying ``YOUTRACK_HUB_URL`` now
refuses to start rather than silently doing nothing.

Enablement requires BOTH ``REPORTER_PROVISIONING_ENABLED=true`` and a dedicated
``YOUTRACK_REPORTER_PROVISION_TOKEN`` that differs from ``YOUTRACK_TOKEN``. The
defaults are off, so deploying this build without the switch changes nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
import urllib.parse
from typing import Any

import audit


REPORTER_PROVISION_TOKEN_ENV = "YOUTRACK_REPORTER_PROVISION_TOKEN"
REPORTER_PROVISIONING_ENABLED_ENV = "REPORTER_PROVISIONING_ENABLED"
REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV = "REPORTER_PROVISIONING_MAX_PER_CYCLE"
REPORTER_API_URL_ENV = "YOUTRACK_API_URL"
LEGACY_HUB_URL_ENV = "YOUTRACK_HUB_URL"

REPORTER_USER_TYPE_ID = "REPORTER"
USER_FIELDS = "id,login,fullName,email,banned,userType(id)"
USER_PAGE_SIZE = 100
# 50 pages x 100 users. CamCore has a few dozen accounts; a directory this large
# is a sign that something else is wrong, and enumeration fails closed.
USER_MAX_PAGES = 50
REPORTER_VISIBILITY_RETRY_DELAYS_SECONDS = (0.25, 0.5, 1.0)
DEFAULT_MAX_PER_CYCLE = 1

# Exit code used when startup configuration is contradictory.
STARTUP_ABORT_EXIT_CODE = 2

# Process-wide circuit breaker. Set (to a reason string) the first time a created
# or read-back account does not carry the exact requested identity and Reporter
# type. Once tripped, provisioning stays off until the worker process restarts,
# so at most one questionable account can be created per process lifetime.
_TRIPPED_REASON: str | None = None


def tripped_reason() -> str | None:
    return _TRIPPED_REASON


def reset_trip_for_tests() -> None:
    global _TRIPPED_REASON
    _TRIPPED_REASON = None


def _emit(event: dict[str, Any], *, stream: Any = None) -> None:
    print(json.dumps(event, sort_keys=True), file=stream or sys.stdout)


def provisioning_enabled_flag() -> bool:
    return audit.parse_bool(os.getenv(REPORTER_PROVISIONING_ENABLED_ENV), default=False)


def validate_provisioning_startup() -> tuple[bool, bool]:
    """Validate the provisioning environment once, at process startup.

    Returns (enabled, token_present). Raises ConfigurationError for a contradictory
    configuration. This runs before audit.main() so a refusal exits immediately
    instead of being caught by audit.run's per-cycle handler and slept over.
    """
    if os.getenv(LEGACY_HUB_URL_ENV, "").strip():
        raise audit.ConfigurationError(
            f"{LEGACY_HUB_URL_ENV} is set but the Hub provisioning path was removed "
            "(OPS-343). Reporter provisioning now uses YouTrack /api/users; remove "
            "the variable. Refusing to start."
        )
    token = os.getenv(REPORTER_PROVISION_TOKEN_ENV, "").strip()
    enabled = provisioning_enabled_flag()
    if enabled and not token:
        raise audit.ConfigurationError(
            f"{REPORTER_PROVISIONING_ENABLED_ENV} is true but "
            f"{REPORTER_PROVISION_TOKEN_ENV} is not set. Refusing to start."
        )
    if enabled and token == os.getenv("YOUTRACK_TOKEN", "").strip():
        raise audit.ConfigurationError(
            f"{REPORTER_PROVISION_TOKEN_ENV} must be a separate least-privilege token, "
            "not the CMA sync token. Refusing to start."
        )
    if enabled:
        audit.positive_int(
            REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV,
            os.getenv(REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV),
            DEFAULT_MAX_PER_CYCLE,
        )
    return enabled, bool(token)


class ReporterProvisioner:
    """Create one Reporter-type YouTrack account for a new Plex member.

    Every step fails closed: an exact-email lookup precedes any create, the
    directory must expose emails at all before "no match" is believed, and the
    created account is read back and must carry the requested login, email and
    REPORTER type. Any mismatch trips the process-wide breaker.
    """

    def __init__(
        self,
        config: audit.Config,
        http: audit.JsonHttpClient,
        *,
        token: str | None = None,
        api_url: str | None = None,
        enabled: bool | None = None,
        max_per_cycle: int | None = None,
    ) -> None:
        self.config = config
        self.http = http
        self.token = (
            token if token is not None else os.getenv(REPORTER_PROVISION_TOKEN_ENV, "")
        ).strip()
        if self.token and self.token == config.youtrack_token:
            raise audit.ConfigurationError(
                f"{REPORTER_PROVISION_TOKEN_ENV} must use a separate least-privilege token"
            )
        self.enabled_flag = (
            enabled if enabled is not None else provisioning_enabled_flag()
        )
        self.max_per_cycle = (
            max_per_cycle
            if max_per_cycle is not None
            else audit.positive_int(
                REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV,
                os.getenv(REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV),
                DEFAULT_MAX_PER_CYCLE,
            )
        )
        self.api_url = self._validated_api_url(api_url)
        self.created_count = 0

    # -- configuration -----------------------------------------------------

    @property
    def enabled(self) -> bool:
        return (
            self.enabled_flag
            and bool(self.token)
            and not self.config.dry_run
            and _TRIPPED_REASON is None
        )

    @property
    def cycle_budget_available(self) -> bool:
        return self.created_count < self.max_per_cycle

    def _validated_api_url(self, override: str | None) -> str:
        sync = urllib.parse.urlsplit(self.config.youtrack_sync_url)
        if sync.scheme not in {"http", "https"} or not sync.netloc:
            raise audit.ConfigurationError("YOUTRACK_SYNC_URL cannot locate the YouTrack host")

        raw = (
            override
            if override is not None
            else os.getenv(REPORTER_API_URL_ENV, "").strip()
        )
        if not raw:
            raw = urllib.parse.urlunsplit((sync.scheme, sync.netloc, "/api", "", ""))
        api = urllib.parse.urlsplit(raw.rstrip("/"))
        if api.scheme != sync.scheme or api.netloc != sync.netloc:
            raise audit.ConfigurationError(
                f"{REPORTER_API_URL_ENV} must use the same YouTrack scheme and host"
            )
        if api.path.rstrip("/") != "/api":
            raise audit.ConfigurationError(
                f"{REPORTER_API_URL_ENV} must point at the YouTrack /api root"
            )
        return urllib.parse.urlunsplit((api.scheme, api.netloc, "/api", "", ""))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    # -- identity helpers --------------------------------------------------

    @staticmethod
    def login_for(account: audit.Account) -> str:
        digest = hashlib.sha256(account.user_id.encode("utf-8")).hexdigest()[:16]
        return f"cma-plex-{digest}"

    @staticmethod
    def _email_of(user: Any) -> str | None:
        if not isinstance(user, dict):
            return None
        value = user.get("email")
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _user_type_of(user: Any) -> str | None:
        if not isinstance(user, dict):
            return None
        user_type = user.get("userType")
        if not isinstance(user_type, dict):
            return None
        value = user_type.get("id")
        return value if isinstance(value, str) else None

    @staticmethod
    def public_user(user: Any) -> dict[str, Any]:
        """Non-sensitive view of a user record for logs and receipts (no email)."""
        if not isinstance(user, dict):
            return {}
        return {
            "id": user.get("id"),
            "login": user.get("login"),
            "userType": ReporterProvisioner._user_type_of(user),
            "banned": user.get("banned"),
        }

    # -- directory access --------------------------------------------------

    def enumerate_users(self) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        for page in range(USER_MAX_PAGES):
            query = urllib.parse.urlencode(
                {"fields": USER_FIELDS, "$top": USER_PAGE_SIZE, "$skip": page * USER_PAGE_SIZE},
                safe="$",
            )
            payload = self.http.request(
                f"{self.api_url}/users?{query}", headers=self._headers()
            )
            if not isinstance(payload, list) or not all(
                isinstance(user, dict) for user in payload
            ):
                raise audit.RemoteApiError("YouTrack user enumeration returned invalid JSON")
            users.extend(payload)
            if len(payload) < USER_PAGE_SIZE:
                return users
        raise audit.RemoteApiError(
            "YouTrack user enumeration exceeded the supported directory size"
        )

    def user_type_counts(self, users: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for user in users:
            key = self._user_type_of(user) or "unknown"
            counts[key] = counts.get(key, 0) + 1
        return counts

    def lookup(self, email: str) -> list[dict[str, Any]]:
        """Return every existing user whose email equals ``email`` (case-insensitive).

        Fails closed when the directory is empty or exposes no email at all, since
        either would make "no match" meaningless and lead to duplicate accounts.
        """
        users = self.enumerate_users()
        if not users:
            raise audit.RemoteApiError("YouTrack user enumeration returned no users")
        if not any(self._email_of(user) for user in users):
            raise audit.RemoteApiError(
                "YouTrack user enumeration exposed no email addresses; "
                "Read User Details may be missing for the provisioning identity"
            )
        wanted = email.strip().casefold()
        return [
            user for user in users if (self._email_of(user) or "").casefold() == wanted
        ]

    # -- creation ------------------------------------------------------------

    def _verify_identity(
        self, user: Any, account: audit.Account, *, phase: str
    ) -> dict[str, Any]:
        problems = []
        if not isinstance(user, dict):
            self._trip(f"{phase}: response is not a user record", None)
            raise audit.RemoteApiError(f"YouTrack reporter {phase} returned invalid JSON")
        if not isinstance(user.get("id"), str) or not user["id"]:
            problems.append("missing id")
        if user.get("login") != self.login_for(account):
            problems.append("login mismatch")
        if (self._email_of(user) or "").casefold() != (account.email or "").casefold():
            problems.append("email mismatch")
        if self._user_type_of(user) != REPORTER_USER_TYPE_ID:
            problems.append("user type is not REPORTER")
        if problems:
            reason = f"{phase}: " + ", ".join(problems)
            self._trip(reason, user)
            raise audit.RemoteApiError(
                f"YouTrack reporter {phase} did not return the requested Reporter identity "
                f"({', '.join(problems)}); provisioning tripped until restart"
            )
        return user

    def _trip(self, reason: str, user: Any) -> None:
        global _TRIPPED_REASON
        _TRIPPED_REASON = reason
        _emit(
            {
                "event": "reporter-provisioning-tripped",
                "reason": reason,
                "user": self.public_user(user),
                "action": "provisioning disabled until the worker restarts; "
                "correct or remove the account in YouTrack Administration > Users",
            },
            stream=sys.stderr,
        )

    def create(self, account: audit.Account) -> dict[str, Any]:
        if not account.email:
            raise audit.RemoteApiError("Cannot provision a Helpdesk reporter without email")
        query = urllib.parse.urlencode({"fields": USER_FIELDS})
        body = {
            "login": self.login_for(account),
            "fullName": account.username,
            "email": account.email,
            # Required by POST /api/users. Reporters authenticate through email
            # links; this value is never logged, stored or reused.
            "password": secrets.token_urlsafe(32),
            "userType": {"id": REPORTER_USER_TYPE_ID},
        }
        created = self.http.request(
            f"{self.api_url}/users?{query}",
            method="POST",
            headers=self._headers(),
            body=body,
        )
        self.created_count += 1
        created = self._verify_identity(created, account, phase="creation")
        readback = self.http.request(
            f"{self.api_url}/users/{urllib.parse.quote(created['id'], safe='')}?{query}",
            headers=self._headers(),
        )
        return self._verify_identity(readback, account, phase="readback")

    def ensure(self, account: audit.Account) -> tuple[str, dict[str, Any] | None]:
        """Return ("existing", None) or ("created", user)."""
        if not self.enabled:
            raise audit.ConfigurationError("Helpdesk reporter provisioning is not enabled")
        if not account.email:
            raise audit.RemoteApiError("Cannot provision a Helpdesk reporter without email")
        if not self.cycle_budget_available:
            raise audit.ConfigurationError(
                "Reporter provisioning budget for this cycle is exhausted"
            )
        if self.lookup(account.email):
            return "existing", None
        return "created", self.create(account)


class ProvisioningYouTrackClient(audit.YouTrackClient):
    """Retry onboarding suppress once a missing reporter is safely provisioned."""

    def __init__(self, config: audit.Config, http: audit.JsonHttpClient) -> None:
        super().__init__(config, http)
        self.reporter_provisioner = ReporterProvisioner(config, http)

    @staticmethod
    def _is_missing_reporter(exc: audit.RemoteApiError) -> bool:
        return audit.deterministic_identity_skip_reason(exc) == "reporter-match-unavailable"

    def sync(
        self,
        account: audit.Account,
        decision: audit.Decision,
        *,
        onboarding_requested: bool,
        notification_mode: str,
        cycle_id: str,
    ) -> Any:
        try:
            return super().sync(
                account,
                decision,
                onboarding_requested=onboarding_requested,
                notification_mode=notification_mode,
                cycle_id=cycle_id,
            )
        except audit.RemoteHttpError as exc:
            provisioner = self.reporter_provisioner
            eligible = (
                provisioner.enabled
                and onboarding_requested
                and notification_mode == audit.NOTIFICATION_MODE_SUPPRESS
                and self._is_missing_reporter(exc)
                and bool(account.email)
            )
            if not eligible:
                raise
            if not provisioner.cycle_budget_available:
                # Leave the account as an ordinary deterministic skip this cycle.
                _emit(
                    {
                        "event": "reporter-provisioning-skipped",
                        "reason": "cycle-budget-exhausted",
                        "plexUserId": account.user_id,
                        "username": account.username,
                    }
                )
                raise
            missing = exc

        outcome, user = provisioner.ensure(account)
        if outcome == "existing":
            # An account with this email exists but the CMA app could not match it
            # uniquely. Never create a second account; keep the deterministic skip.
            _emit(
                {
                    "event": "reporter-provisioning-skipped",
                    "reason": "existing-account-not-unique-match",
                    "plexUserId": account.user_id,
                    "username": account.username,
                }
            )
            raise missing

        _emit(
            {
                "event": "reporter-provisioned",
                "plexUserId": account.user_id,
                "username": account.username,
                "outcome": outcome,
                "user": ReporterProvisioner.public_user(user),
                "cycleId": cycle_id,
            }
        )

        last_missing: audit.RemoteHttpError | None = None
        for delay in (0.0,) + REPORTER_VISIBILITY_RETRY_DELAYS_SECONDS:
            if delay:
                time.sleep(delay)
            try:
                return super().sync(
                    account,
                    decision,
                    onboarding_requested=onboarding_requested,
                    notification_mode=notification_mode,
                    cycle_id=cycle_id,
                )
            except audit.RemoteHttpError as retry_exc:
                if not self._is_missing_reporter(retry_exc):
                    raise
                last_missing = retry_exc

        raise audit.RemoteApiError(
            "Provisioned Helpdesk reporter did not become a unique YouTrack email match"
        ) from last_missing


def install() -> None:
    audit.YouTrackClient = ProvisioningYouTrackClient


def main() -> int:
    try:
        enabled, token_present = validate_provisioning_startup()
    except audit.ConfigurationError as exc:
        _emit(
            {
                "event": "startup-aborted",
                "reason": "reporter-provisioning-configuration",
                "detail": str(exc),
            },
            stream=sys.stderr,
        )
        return STARTUP_ABORT_EXIT_CODE
    _emit(
        {
            "event": "reporter-provisioning",
            "state": "enabled" if enabled else "disabled",
            "tokenPresent": token_present,
            "maxPerCycle": (
                audit.positive_int(
                    REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV,
                    os.getenv(REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV),
                    DEFAULT_MAX_PER_CYCLE,
                )
                if enabled
                else None
            ),
        }
    )
    if enabled:
        install()
    return audit.main()


if __name__ == "__main__":
    raise SystemExit(main())
