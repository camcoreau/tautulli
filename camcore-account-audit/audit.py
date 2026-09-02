#!/usr/bin/env python3
"""Synchronize Tautulli account activity into the CMA YouTrack helpdesk project."""

from __future__ import annotations

import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


UTC = timezone.utc
DEFAULT_USER_AGENT = "CamCore-CMA-Account-Audit/1.0"
JS_MAX_SAFE_INTEGER = (2**53) - 1
MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)
MEMBER_NOTIFICATION_WINDOW = timedelta(hours=24)
NOTIFICATION_POLICY_VERSION = 1
NOTIFICATION_PROTOCOL_ID = "cma-account-audit-member-notification"
NOTIFICATION_PROTOCOL_MODES = ("suppress", "permit")
NOTIFICATION_MODE_SUPPRESS = "suppress"
NOTIFICATION_MODE_PERMIT = "permit"
NOTIFICATION_DEFERRED_ACTION = "member-notification-deferred"
NOTIFICATION_BUDGET_EXHAUSTED_ACTION = "member-notification-budget-exhausted"
TICKET_CREATED_AWAITING_NOTICE_ACTION = "ticket-created-awaiting-notice"
ONBOARDING_PROTOCOL_VERSION = 1
ONBOARDING_TICKET_CREATED_ACTION = "onboarding-ticket-created"
ONBOARDING_EXISTING_TICKET_ACTION = "onboarding-existing-ticket"
ONBOARDING_STATES = frozenset({"baseline", "pending", "completed"})
TRANSIENT_GET_RETRY_DELAY_SECONDS = 1.0
PERMIT_CONFLICT_RETRY_DELAYS_SECONDS = (0.25, 0.5, 1.0)
NOTIFICATION_GATE_STATUSES = frozenset(
    {
        "reserved",
        "confirmed",
        "server-budget-exhausted",
        "no-longer-required",
    }
)
NOTIFICATION_PLANNED_ACTIONS = frozenset(
    {
        "facts-only",
        "notice-restarted-after-active-baseline",
        "notice-started",
        "protected-terminal-stage",
        "retained",
        "retained-awaiting-new-active-baseline",
        "review-already-in-progress",
        ONBOARDING_TICKET_CREATED_ACTION,
        ONBOARDING_EXISTING_TICKET_ACTION,
        TICKET_CREATED_AWAITING_NOTICE_ACTION,
    }
)
# A current message stage can require a permit even when its account-plan action
# is otherwise facts-only or terminal. The endpoint is the authority on that
# stage-sensitive decision; the worker only accepts actions from this closed set.
NOTIFICATION_PERMIT_ACTIONS = NOTIFICATION_PLANNED_ACTIONS


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


class RemoteApiError(RuntimeError):
    """Raised when Tautulli or YouTrack rejects a request."""


class RemoteHttpError(RemoteApiError):
    """A remote dependency returned a structured HTTP error response."""

    def __init__(self, message: str, *, status_code: int, detail: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


DETERMINISTIC_IDENTITY_REJECTIONS = {
    (400, "email must be a non-empty string"): "email-unavailable",
    (
        422,
        "No unique YouTrack Helpdesk reporter matches the Plex email address",
    ): "reporter-match-unavailable",
}


def deterministic_identity_skip_reason(exc: RemoteApiError) -> str | None:
    if not isinstance(exc, RemoteHttpError):
        return None
    try:
        payload = json.loads(exc.detail)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or set(payload) != {"error"}:
        return None
    message = payload.get("error")
    if not isinstance(message, str):
        return None
    return DETERMINISTIC_IDENTITY_REJECTIONS.get((exc.status_code, message))


def is_youtrack_transaction_conflict(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("error") == "Invalid properties":
        return True
    if payload.get("error") != "invalid_properties":
        return False
    children = payload.get("error_children")
    if not isinstance(children, list):
        return False
    return any(
        isinstance(child, dict)
        and child.get("error") == "PluggedStringAttribute-is-invalid"
        and child.get("error_developer_message") == "Value should be unique"
        for child in children
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"Invalid boolean value: {value!r}")


def positive_int(name: str, value: str | None, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return parsed


@dataclass(frozen=True)
class Config:
    tautulli_url: str
    tautulli_api_key: str
    youtrack_sync_url: str
    youtrack_token: str
    registry_path: Path
    inactive_days: int = 60
    never_used_days: int = 14
    excluded_users: frozenset[str] = frozenset({"guest", "local"})
    timeout_seconds: int = 20
    dry_run: bool = True
    interval_seconds: int = 0

    @classmethod
    def from_env(cls) -> "Config":
        dry_run = parse_bool(os.getenv("DRY_RUN"), default=True)
        tautulli_url = os.getenv("TAUTULLI_URL", "").strip().rstrip("/")
        tautulli_api_key = os.getenv("TAUTULLI_API_KEY", "").strip()
        youtrack_token = os.getenv("YOUTRACK_TOKEN", "").strip()
        sync_url = os.getenv("YOUTRACK_SYNC_URL", "").strip()

        if not sync_url:
            youtrack_url = os.getenv("YOUTRACK_URL", "").strip().rstrip("/")
            project_id = os.getenv("YOUTRACK_PROJECT_ID", "CMA").strip()
            if youtrack_url:
                sync_url = (
                    f"{youtrack_url}/api/admin/projects/"
                    f"{urllib.parse.quote(project_id, safe='')}/extensionEndpoints/"
                    "cma-account-audit/account-sync/sync-account"
                )

        missing = []
        if not tautulli_url:
            missing.append("TAUTULLI_URL")
        if not tautulli_api_key:
            missing.append("TAUTULLI_API_KEY")
        if not sync_url:
            missing.append("YOUTRACK_URL or YOUTRACK_SYNC_URL")
        if not youtrack_token:
            missing.append("YOUTRACK_TOKEN")
        if missing:
            raise ConfigurationError("Missing required settings: " + ", ".join(missing))

        excluded = frozenset(
            part.strip().casefold()
            for part in os.getenv("EXCLUDED_USERS", "Guest,Local").split(",")
            if part.strip()
        )
        interval_raw = os.getenv("AUDIT_INTERVAL_SECONDS", "0")
        try:
            interval_seconds = int(interval_raw)
        except ValueError as exc:
            raise ConfigurationError("AUDIT_INTERVAL_SECONDS must be an integer") from exc
        if interval_seconds < 0:
            raise ConfigurationError("AUDIT_INTERVAL_SECONDS cannot be negative")

        return cls(
            tautulli_url=tautulli_url,
            tautulli_api_key=tautulli_api_key,
            youtrack_sync_url=sync_url,
            youtrack_token=youtrack_token,
            registry_path=Path(os.getenv("REGISTRY_PATH", "/data/registry.json")),
            inactive_days=positive_int("INACTIVE_DAYS", os.getenv("INACTIVE_DAYS"), 60),
            never_used_days=positive_int(
                "NEVER_USED_DAYS", os.getenv("NEVER_USED_DAYS"), 14
            ),
            excluded_users=excluded,
            timeout_seconds=positive_int(
                "HTTP_TIMEOUT_SECONDS", os.getenv("HTTP_TIMEOUT_SECONDS"), 20
            ),
            dry_run=dry_run,
            interval_seconds=interval_seconds,
        )


@dataclass(frozen=True)
class Account:
    user_id: str
    username: str
    email: str | None
    last_streamed: datetime | None
    total_plays: int
    watch_seconds: int


@dataclass(frozen=True)
class Decision:
    account_status: str
    review_needed: bool
    reason: str


class JsonHttpClient:
    def __init__(self, timeout_seconds: int):
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        display_url = urllib.parse.urlsplit(url)._replace(query="", fragment="").geturl()
        request_headers = {
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        request_headers.update(headers or {})
        encoded_body = None
        if body is not None:
            request_headers["Content-Type"] = "application/json"
            encoded_body = json.dumps(body, separators=(",", ":")).encode("utf-8")

        for attempt in range(2):
            request = urllib.request.Request(
                url,
                data=encoded_body,
                headers=request_headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout_seconds
                ) as response:
                    payload = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise RemoteHttpError(
                    f"{method} {display_url} returned HTTP {exc.code}: {detail}",
                    status_code=exc.code,
                    detail=detail,
                ) from exc
            except urllib.error.URLError as exc:
                if method == "GET" and attempt == 0:
                    time.sleep(TRANSIENT_GET_RETRY_DELAY_SECONDS)
                    continue
                raise RemoteApiError(
                    f"{method} {display_url} failed: {exc.reason}"
                ) from exc
            except (OSError, http.client.HTTPException) as exc:
                if method == "GET" and attempt == 0:
                    time.sleep(TRANSIENT_GET_RETRY_DELAY_SECONDS)
                    continue
                raise RemoteApiError(f"{method} {display_url} failed: {exc}") from exc

        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RemoteApiError(f"{method} {display_url} returned invalid JSON") from exc


class TautulliClient:
    def __init__(self, config: Config, http: JsonHttpClient):
        self.config = config
        self.http = http

    def accounts(self) -> list[Account]:
        query = urllib.parse.urlencode(
            {
                "apikey": self.config.tautulli_api_key,
                "cmd": "get_users_table",
                "start": 0,
                "length": 10000,
                "order_column": "friendly_name",
                "order_dir": "asc",
            }
        )
        payload = self.http.request(f"{self.config.tautulli_url}/api/v2?{query}")
        response = payload.get("response", {}) if isinstance(payload, dict) else {}
        if response.get("result") != "success":
            message = response.get("message") or "unknown Tautulli API error"
            raise RemoteApiError(f"Tautulli get_users_table failed: {message}")

        result_data = response.get("data", {})
        rows = result_data.get("data", []) if isinstance(result_data, dict) else []
        if not isinstance(rows, list):
            raise RemoteApiError("Tautulli get_users_table returned an invalid data list")

        accounts = []
        observed_at = utc_now()
        for row in rows:
            try:
                account = account_from_row(row, observed_at=observed_at)
            except ValueError as exc:
                raise RemoteApiError(
                    f"Tautulli get_users_table contained unsafe account telemetry: {exc}"
                ) from exc
            if account is not None:
                accounts.append(account)
        return accounts


class YouTrackClient:
    def __init__(self, config: Config, http: JsonHttpClient):
        self.config = config
        self.http = http

    def protocol(self) -> Any:
        parsed = urllib.parse.urlsplit(self.config.youtrack_sync_url)
        sync_path = parsed.path.rstrip("/")
        parent_path, separator, _ = sync_path.rpartition("/")
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not separator
        ):
            raise ConfigurationError("YOUTRACK_SYNC_URL cannot locate its protocol endpoint")
        protocol_url = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parent_path + "/protocol", "", "")
        )
        return self.http.request(
            protocol_url,
            headers={"Authorization": f"Bearer {self.config.youtrack_token}"},
        )

    def sync(
        self,
        account: Account,
        decision: Decision,
        *,
        onboarding_requested: bool,
        notification_mode: str,
        cycle_id: str,
    ) -> Any:
        payload = {
            "plexUserId": account.user_id,
            "plexUsername": account.username,
            "email": account.email,
            "lastStreamedMs": (
                int(account.last_streamed.timestamp() * 1000)
                if account.last_streamed
                else None
            ),
            "totalPlays": account.total_plays,
            "watchSeconds": account.watch_seconds,
            "watchTime": format_watch_time(account.watch_seconds),
            "accountStatus": decision.account_status,
            "reviewNeeded": decision.review_needed,
            "reviewReason": decision.reason,
            "onboardingRequested": onboarding_requested,
            "notificationMode": notification_mode,
            "cycleId": cycle_id,
        }
        def submit() -> Any:
            return self.http.request(
                self.config.youtrack_sync_url,
                method="POST",
                headers={"Authorization": f"Bearer {self.config.youtrack_token}"},
                body=payload,
            )

        for attempt in range(len(PERMIT_CONFLICT_RETRY_DELAYS_SECONDS) + 1):
            try:
                return submit()
            except RemoteHttpError as exc:
                # Two permit transactions can both preflight the same available
                # AppGlobalStorage budget before YouTrack commits one and rejects
                # the loser with its structured optimistic-conflict response.
                # Give the winning commit time to become visible, then retry only
                # this determinate permit conflict with the identical payload. A
                # successful winner makes the retry return budget-exhausted; if
                # the winner rolled back, one retry can safely reserve the sole
                # permit. All other POST failures remain fail-closed.
                try:
                    error_payload = json.loads(exc.detail)
                except json.JSONDecodeError:
                    error_payload = None
                is_transaction_conflict = (
                    notification_mode == NOTIFICATION_MODE_PERMIT
                    and exc.status_code == 400
                    and is_youtrack_transaction_conflict(error_payload)
                )
                if (
                    not is_transaction_conflict
                    or attempt == len(PERMIT_CONFLICT_RETRY_DELAYS_SECONDS)
                ):
                    raise
                time.sleep(PERMIT_CONFLICT_RETRY_DELAYS_SECONDS[attempt])


class RegistryLock:
    """Hold one non-blocking, cross-process lock for a complete audit run."""

    def __init__(self, registry_path: Path):
        self.path = registry_path.with_name(registry_path.name + ".lock")
        self._handle: Any | None = None

    def __enter__(self) -> "RegistryLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = self.path.open("a+b")
        except OSError as exc:
            raise ConfigurationError(
                f"Cannot open exclusive registry lock {self.path}: {exc}"
            ) from exc

        try:
            # Windows byte-range locks require the selected byte to exist. Keep
            # the lock file permanently so deleting/recreating its inode cannot
            # let a second process bypass a lock held by the first.
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError) as exc:
            handle.close()
            raise ConfigurationError(
                f"Cannot acquire exclusive registry lock {self.path}: {exc}"
            ) from exc

        self._handle = handle
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class Registry:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {
            # Keep the original schema marker so the previous worker can load
            # this file during rollback and preserve the additional safety keys.
            "schemaVersion": 1,
            "users": {},
            "memberNotificationPermitHistory": {},
        }

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"Cannot read registry {self.path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigurationError(f"Unsupported registry format in {self.path}")
        schema_version = loaded.get("schemaVersion")
        if (
            isinstance(schema_version, bool)
            or schema_version != 1
            or not isinstance(loaded.get("users"), dict)
        ):
            raise ConfigurationError(f"Unsupported registry format in {self.path}")
        loaded.setdefault("memberNotificationPermitHistory", {})
        self.data = loaded
        self._notification_gate()
        self._notification_permit_history()
        self.onboarding_baseline_ready()

    def _notification_permit_history(self) -> dict[str, str]:
        history = self.data.setdefault("memberNotificationPermitHistory", {})
        if not isinstance(history, dict):
            raise ConfigurationError(
                f"Invalid memberNotificationPermitHistory in {self.path}"
            )
        for plex_user_id, reserved_at_raw in history.items():
            if not isinstance(plex_user_id, str) or not plex_user_id.strip():
                raise ConfigurationError(
                    f"Invalid memberNotificationPermitHistory Plex user ID in {self.path}"
                )
            try:
                reserved_at = datetime.fromisoformat(reserved_at_raw)
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(
                    f"Invalid memberNotificationPermitHistory timestamp in {self.path}"
                ) from exc
            if reserved_at.tzinfo is None or reserved_at.utcoffset() is None:
                raise ConfigurationError(
                    f"Invalid memberNotificationPermitHistory timezone in {self.path}"
                )
        return history

    def _notification_gate(self) -> tuple[dict[str, Any], datetime] | None:
        gate = self.data.get("memberNotificationGate")
        if gate is None:
            return None
        if not isinstance(gate, dict):
            raise ConfigurationError(
                f"Invalid memberNotificationGate in {self.path}"
            )
        policy_version = gate.get("policyVersion")
        if (
            isinstance(policy_version, bool)
            or not isinstance(policy_version, int)
            or policy_version != NOTIFICATION_POLICY_VERSION
        ):
            raise ConfigurationError(
                f"Invalid memberNotificationGate policy version in {self.path}"
            )
        if not isinstance(gate.get("cycleId"), str) or not gate["cycleId"].strip():
            raise ConfigurationError(
                f"Invalid memberNotificationGate cycle ID in {self.path}"
            )
        if not isinstance(gate.get("plexUserId"), str) or not gate[
            "plexUserId"
        ].strip():
            raise ConfigurationError(
                f"Invalid memberNotificationGate Plex user ID in {self.path}"
            )
        if gate.get("status") not in NOTIFICATION_GATE_STATUSES:
            raise ConfigurationError(
                f"Invalid memberNotificationGate status in {self.path}"
            )
        try:
            reserved_at = datetime.fromisoformat(gate["reservedAt"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Invalid memberNotificationGate reservation in {self.path}"
            ) from exc
        if reserved_at.tzinfo is None or reserved_at.utcoffset() is None:
            raise ConfigurationError(
                f"Invalid memberNotificationGate reservation timezone in {self.path}"
            )
        return gate, reserved_at.astimezone(UTC)

    def notification_permit_available(self, observed_at: datetime) -> bool:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ConfigurationError("Audit observation time must include a timezone")
        observed_at = observed_at.astimezone(UTC)
        for reserved_at_raw in self._notification_permit_history().values():
            reserved_at = datetime.fromisoformat(reserved_at_raw).astimezone(UTC)
            if reserved_at > observed_at + MAX_FUTURE_CLOCK_SKEW:
                raise ConfigurationError(
                    f"memberNotificationPermitHistory reservation is in the future in {self.path}"
                )
        gate_state = self._notification_gate()
        if gate_state is None:
            return True
        _, reserved_at = gate_state
        if reserved_at > observed_at + MAX_FUTURE_CLOCK_SKEW:
            raise ConfigurationError(
                f"memberNotificationGate reservation is in the future in {self.path}"
            )
        return observed_at - reserved_at >= MEMBER_NOTIFICATION_WINDOW

    def reserve_notification_permit(
        self,
        *,
        cycle_id: str,
        account: Account,
        observed_at: datetime,
    ) -> None:
        if not self.notification_permit_available(observed_at):
            raise ConfigurationError("Member-notification permit is already reserved")
        self.data["memberNotificationGate"] = {
            "policyVersion": NOTIFICATION_POLICY_VERSION,
            "cycleId": cycle_id,
            "plexUserId": account.user_id,
            "reservedAt": observed_at.isoformat(),
            "status": "reserved",
        }
        self._notification_permit_history()[account.user_id] = observed_at.isoformat()
        # Persist before the remote call. An ambiguous timeout therefore consumes
        # the local permit instead of allowing a restart to send another message.
        self.save()

    def confirm_notification_permit(self, *, cycle_id: str, status: str) -> None:
        if status not in NOTIFICATION_GATE_STATUSES - {"reserved"}:
            raise ConfigurationError("Invalid member-notification permit status")
        gate_state = self._notification_gate()
        if gate_state is None or gate_state[0].get("cycleId") != cycle_id:
            raise ConfigurationError("Member-notification permit reservation is missing")
        gate = gate_state[0]
        if gate.get("status") != "reserved":
            raise ConfigurationError("Member-notification permit is not reserved")
        gate["status"] = status
        self.save()

    def last_notification_permit_at(
        self,
        account: Account,
        observed_at: datetime,
    ) -> datetime:
        raw = self._notification_permit_history().get(account.user_id)
        if raw is None:
            return datetime.min.replace(tzinfo=UTC)
        reserved_at = datetime.fromisoformat(raw).astimezone(UTC)
        if reserved_at > observed_at.astimezone(UTC) + MAX_FUTURE_CLOCK_SKEW:
            raise ConfigurationError(
                f"memberNotificationPermitHistory reservation is in the future in {self.path}"
            )
        return reserved_at

    def onboarding_baseline_ready(self) -> bool:
        raw = self.data.get("onboardingBaselineCompletedAt")
        if raw is None:
            return False
        try:
            completed_at = datetime.fromisoformat(raw)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Invalid onboardingBaselineCompletedAt in {self.path}"
            ) from exc
        if completed_at.tzinfo is None or completed_at.utcoffset() is None:
            raise ConfigurationError(
                f"Invalid onboardingBaselineCompletedAt timezone in {self.path}"
            )
        return True

    def observe_account(
        self, account: Account, observed_at: datetime
    ) -> tuple[datetime, bool]:
        users = self.data["users"]
        known = account.user_id in users
        entry = users.setdefault(
            account.user_id,
            {
                "firstSeenAt": observed_at.isoformat(),
                "lastSeenAt": observed_at.isoformat(),
                "username": account.username,
            },
        )
        if not isinstance(entry, dict):
            raise ConfigurationError(
                f"Invalid registry entry for Plex user ID {account.user_id}"
            )
        entry["lastSeenAt"] = observed_at.isoformat()
        entry["username"] = account.username
        state = entry.get("onboardingState")
        if state is None:
            state = (
                "pending"
                if self.onboarding_baseline_ready() and not known
                else "baseline"
            )
            entry["onboardingState"] = state
        if state not in ONBOARDING_STATES:
            raise ConfigurationError(
                f"Invalid onboardingState for Plex user ID {account.user_id}"
            )
        try:
            first_seen = datetime.fromisoformat(entry["firstSeenAt"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Invalid firstSeenAt for Plex user ID {account.user_id}"
            ) from exc
        if first_seen.tzinfo is None or first_seen.utcoffset() is None:
            raise ConfigurationError(
                f"Invalid firstSeenAt timezone for Plex user ID {account.user_id}"
            )
        return first_seen.astimezone(UTC), state == "pending"

    def first_seen(self, account: Account, observed_at: datetime) -> datetime:
        first_seen, _ = self.observe_account(account, observed_at)
        return first_seen

    def complete_onboarding_baseline(
        self, observed_at: datetime, *, inventory_count: int
    ) -> None:
        if self.onboarding_baseline_ready():
            return
        if inventory_count <= 0:
            raise ConfigurationError(
                "Refusing to establish an empty Cameron-Media onboarding baseline"
            )
        self.data["onboardingBaselineCompletedAt"] = observed_at.isoformat()

    def confirm_onboarding(self, account: Account) -> None:
        entry = self.data["users"].get(account.user_id)
        if not isinstance(entry, dict) or entry.get("onboardingState") != "pending":
            raise ConfigurationError(
                f"Pending onboarding state is missing for Plex user ID {account.user_id}"
            )
        entry["onboardingState"] = "completed"

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(self.path.name + ".tmp")
        temp_path.write_text(
            json.dumps(self.data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, self.path)


def validate_sync_response(
    response: Any,
    *,
    notification_mode: str,
    cycle_id: str,
    plex_user_id: str,
    onboarding_requested: bool,
) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RemoteApiError("YouTrack account sync returned an invalid response")
    policy_version = response.get("notificationPolicyVersion")
    if (
        isinstance(policy_version, bool)
        or not isinstance(policy_version, int)
        or policy_version != NOTIFICATION_POLICY_VERSION
    ):
        raise RemoteApiError("YouTrack account sync notification policy is incompatible")
    if response.get("notificationMode") != notification_mode:
        raise RemoteApiError("YouTrack account sync returned the wrong notification mode")
    if response.get("cycleId") != cycle_id:
        raise RemoteApiError("YouTrack account sync returned the wrong cycle ID")
    if response.get("plexUserId") != plex_user_id:
        raise RemoteApiError("YouTrack account sync returned the wrong Plex user ID")
    if response.get("onboardingRequested") is not onboarding_requested:
        raise RemoteApiError("YouTrack account sync returned the wrong onboarding request")
    if not isinstance(response.get("onboardingCompleted"), bool):
        raise RemoteApiError("YouTrack account sync omitted its onboarding receipt")
    if response["onboardingCompleted"] and not onboarding_requested:
        raise RemoteApiError("YouTrack account sync returned a contradictory onboarding receipt")
    if not isinstance(response.get("memberNotificationPermitRequired"), bool):
        raise RemoteApiError("YouTrack account sync omitted its permit requirement")
    if not isinstance(response.get("memberNotificationPermitReserved"), bool):
        raise RemoteApiError("YouTrack account sync omitted its permit receipt")
    remaining = response.get("memberNotificationBudgetRemaining")
    if (
        isinstance(remaining, bool)
        or not isinstance(remaining, int)
        or remaining not in (0, 1)
    ):
        raise RemoteApiError("YouTrack account sync returned an invalid notification budget")

    permit_required = response["memberNotificationPermitRequired"]
    permit_reserved = response["memberNotificationPermitReserved"]
    action = response.get("action")
    result = response.get("result")
    planned_action = response.get("plannedAction")
    if planned_action not in NOTIFICATION_PLANNED_ACTIONS:
        raise RemoteApiError("YouTrack account sync returned an invalid planned action")
    onboarding_completed = response["onboardingCompleted"]
    if onboarding_completed:
        completed_by_creation = (
            planned_action == ONBOARDING_TICKET_CREATED_ACTION
            and notification_mode == NOTIFICATION_MODE_PERMIT
            and permit_required
            and permit_reserved
            and result == "created"
            and action == planned_action
        )
        completed_by_existing_ticket = (
            planned_action == ONBOARDING_EXISTING_TICKET_ACTION
            and not permit_required
            and not permit_reserved
            and result == "planned"
            and action == planned_action
        )
        if not completed_by_creation and not completed_by_existing_ticket:
            raise RemoteApiError(
                "YouTrack account sync returned an unsafe onboarding completion"
            )
    elif onboarding_requested and planned_action == ONBOARDING_EXISTING_TICKET_ACTION:
        raise RemoteApiError(
            "YouTrack account sync did not confirm the existing onboarding ticket"
        )
    if notification_mode == NOTIFICATION_MODE_SUPPRESS:
        if permit_reserved:
            raise RemoteApiError("Suppress mode unexpectedly reserved a notification permit")
        if permit_required:
            if planned_action not in NOTIFICATION_PERMIT_ACTIONS or (
                result != "deferred" or action != NOTIFICATION_DEFERRED_ACTION
            ):
                raise RemoteApiError("Suppress mode returned an unsafe candidate response")
        elif result != "planned" or action != planned_action:
            raise RemoteApiError("Suppress mode returned a non-read-only plan response")
    elif notification_mode == NOTIFICATION_MODE_PERMIT:
        exhausted = (
            result == "deferred" and action == NOTIFICATION_BUDGET_EXHAUSTED_ACTION
        )
        if permit_required:
            if planned_action not in NOTIFICATION_PERMIT_ACTIONS:
                raise RemoteApiError("Permit mode returned an unsafe planned action")
            if permit_reserved:
                if exhausted or result not in {"created", "updated"} or action != planned_action:
                    raise RemoteApiError(
                        "Permit mode returned a contradictory notification receipt"
                    )
                if remaining != 0:
                    raise RemoteApiError("Permit mode did not consume its notification budget")
            elif not exhausted or remaining != 0:
                raise RemoteApiError(
                    "Permit mode returned an indeterminate notification receipt"
                )
        elif (
            permit_reserved
            or exhausted
            or result != "planned"
            or action != planned_action
        ):
            raise RemoteApiError("Permit mode returned an invalid read-only plan receipt")
    else:
        raise RemoteApiError("Unsupported notification mode")
    return response


def validate_protocol_response(response: Any) -> dict[str, Any]:
    expected_keys = {
        "appName",
        "notificationPolicyVersion",
        "notificationModes",
        "memberNotificationLimit",
        "memberNotificationWindowSeconds",
        "onboardingProtocolVersion",
    }
    if not isinstance(response, dict) or set(response) != expected_keys:
        raise RemoteApiError("YouTrack account sync protocol receipt is incompatible")
    if response.get("appName") != NOTIFICATION_PROTOCOL_ID:
        raise RemoteApiError("YouTrack account sync protocol identity is incompatible")
    policy_version = response.get("notificationPolicyVersion")
    if (
        isinstance(policy_version, bool)
        or not isinstance(policy_version, int)
        or policy_version != NOTIFICATION_POLICY_VERSION
    ):
        raise RemoteApiError("YouTrack account sync notification policy is incompatible")
    if response.get("notificationModes") != list(NOTIFICATION_PROTOCOL_MODES):
        raise RemoteApiError("YouTrack account sync protocol modes are incompatible")
    onboarding_version = response.get("onboardingProtocolVersion")
    if (
        isinstance(onboarding_version, bool)
        or not isinstance(onboarding_version, int)
        or onboarding_version != ONBOARDING_PROTOCOL_VERSION
    ):
        raise RemoteApiError("YouTrack account sync onboarding protocol is incompatible")
    member_limit = response.get("memberNotificationLimit")
    if (
        isinstance(member_limit, bool)
        or not isinstance(member_limit, int)
        or member_limit != 1
    ):
        raise RemoteApiError("YouTrack account sync notification limit is incompatible")
    window_seconds = response.get("memberNotificationWindowSeconds")
    if (
        isinstance(window_seconds, bool)
        or not isinstance(window_seconds, int)
        or window_seconds != int(MEMBER_NOTIFICATION_WINDOW.total_seconds())
    ):
        raise RemoteApiError("YouTrack account sync notification window is incompatible")
    return response


def candidate_priority(response: dict[str, Any]) -> int:
    planned_action = response.get("plannedAction")
    priorities = {
        ONBOARDING_TICKET_CREATED_ACTION: -1,
        "retained": 0,
        "notice-started": 1,
        "notice-restarted-after-active-baseline": 1,
        "review-already-in-progress": 2,
        # Ticket creation can notify the reporter, but it should not start a
        # second member-visible notice until existing notice work is drained.
        TICKET_CREATED_AWAITING_NOTICE_ACTION: 3,
    }
    return priorities.get(planned_action, 3)


def required_non_negative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or value is None or str(value).strip() == "":
        raise ValueError(f"{name} is missing or invalid")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{name} is missing or invalid")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} is missing or invalid") from exc
    if parsed < 0 or parsed > JS_MAX_SAFE_INTEGER:
        raise ValueError(f"{name} is missing or invalid")
    return parsed


def optional_non_negative_int(name: str, value: Any, default: int = 0) -> int:
    if value is None or str(value).strip() == "":
        return default
    return required_non_negative_int(name, value)


def last_streamed_from_row(
    value: Any,
    *,
    total_plays: int,
    observed_at: datetime,
) -> datetime | None:
    if value is None or str(value).strip() == "":
        last_seen_epoch = None
    else:
        last_seen_epoch = required_non_negative_int("last_seen", value)

    if total_plays == 0:
        if last_seen_epoch not in (None, 0):
            raise ValueError("last_seen conflicts with zero plays")
        return None

    if last_seen_epoch in (None, 0):
        raise ValueError("last_seen is required when plays are greater than zero")
    try:
        last_streamed = datetime.fromtimestamp(last_seen_epoch, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("last_seen is missing or invalid") from exc
    if last_streamed > observed_at + MAX_FUTURE_CLOCK_SKEW:
        raise ValueError("last_seen is too far in the future")
    return last_streamed


def account_from_row(
    row: Any,
    *,
    observed_at: datetime | None = None,
) -> Account | None:
    if not isinstance(row, dict):
        return None
    user_id = str(row.get("user_id") or "").strip()
    username = str(row.get("username") or row.get("friendly_name") or "").strip()
    if not user_id or not username:
        return None

    observed_at = observed_at or utc_now()
    total_plays = required_non_negative_int("plays", row.get("plays"))
    last_streamed = last_streamed_from_row(
        row.get("last_seen"),
        total_plays=total_plays,
        observed_at=observed_at,
    )
    email = str(row.get("email") or "").strip() or None
    return Account(
        user_id=user_id,
        username=username,
        email=email,
        last_streamed=last_streamed,
        total_plays=total_plays,
        watch_seconds=optional_non_negative_int("duration", row.get("duration")),
    )


def classify_account(
    account: Account,
    *,
    first_seen: datetime,
    observed_at: datetime,
    inactive_days: int,
    never_used_days: int,
) -> Decision:
    if account.total_plays == 0:
        if account.last_streamed is not None:
            raise ValueError("zero-play accounts cannot have a last-streamed timestamp")
        age = observed_at - first_seen
        eligible = age >= timedelta(days=never_used_days)
        return Decision(
            account_status="Never Used",
            review_needed=eligible,
            reason=(
                f"no plays after {never_used_days} days"
                if eligible
                else f"no plays; observation period is under {never_used_days} days"
            ),
        )

    if account.last_streamed is None:
        raise ValueError("accounts with plays require a last-streamed timestamp")
    if account.last_streamed > observed_at + MAX_FUTURE_CLOCK_SKEW:
        raise ValueError("last-streamed timestamp is too far in the future")

    inactive_for = observed_at - account.last_streamed
    if inactive_for >= timedelta(days=inactive_days):
        return Decision(
            account_status="Inactive",
            review_needed=True,
            reason=f"last stream was at least {inactive_days} days ago",
        )

    return Decision(
        account_status="Active",
        review_needed=False,
        reason=f"last stream was within {inactive_days} days",
    )


def format_watch_time(seconds: int) -> str:
    total_minutes = max(0, seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours} hrs {minutes} mins"
    return f"{minutes} mins"


def public_account(account: Account) -> dict[str, Any]:
    data = asdict(account)
    data["last_streamed"] = (
        account.last_streamed.date().isoformat() if account.last_streamed else None
    )
    data["email"] = "present" if account.email else "missing"
    return data


def run_once(config: Config, observed_at: datetime | None = None) -> int:
    observed_at = observed_at or utc_now()
    http = JsonHttpClient(config.timeout_seconds)
    tautulli = TautulliClient(config, http)
    youtrack = YouTrackClient(config, http)
    registry = Registry(config.registry_path)
    # This read-only endpoint does not exist in the legacy app. Prove exact
    # suppress/permit compatibility before enumerating accounts. Dry-run uses
    # the same handshake and read-only suppress pass as live mode so its
    # projected notification set cannot diverge from the production planner.
    validate_protocol_response(youtrack.protocol())
    # Serialize the entire registry and remote-sync cycle. A second process
    # fails immediately instead of reading a stale gate or racing a reservation.
    with RegistryLock(config.registry_path):
        return _run_once_locked(config, observed_at, tautulli, youtrack, registry)


def _run_once_locked(
    config: Config,
    observed_at: datetime,
    tautulli: TautulliClient,
    youtrack: YouTrackClient,
    registry: Registry,
) -> int:
    registry.load()
    cycle_id = "audit-" + uuid.uuid4().hex

    errors = 0
    processed = 0
    excluded = 0
    entries: list[dict[str, Any]] = []
    for account in tautulli.accounts():
        if account.username.casefold() in config.excluded_users:
            excluded += 1
            print(json.dumps({"event": "excluded", "username": account.username}))
            continue

        first_seen, onboarding_requested = registry.observe_account(account, observed_at)
        decision = classify_account(
            account,
            first_seen=first_seen,
            observed_at=observed_at,
            inactive_days=config.inactive_days,
            never_used_days=config.never_used_days,
        )
        event = {
            "event": "evaluated",
            "account": public_account(account),
            "decision": asdict(decision),
            "dryRun": config.dry_run,
            "cycleId": cycle_id,
            "onboardingRequested": onboarding_requested,
        }
        entries.append({
            "account": account,
            "decision": decision,
            "event": event,
            "onboardingRequested": onboarding_requested,
        })

    registry.complete_onboarding_baseline(
        observed_at,
        inventory_count=len(entries),
    )

    candidates: list[dict[str, Any]] = []
    for entry in entries:
        account = entry["account"]
        decision = entry["decision"]
        event = entry["event"]
        try:
            response = youtrack.sync(
                account,
                decision,
                onboarding_requested=entry["onboardingRequested"],
                notification_mode=NOTIFICATION_MODE_SUPPRESS,
                cycle_id=cycle_id,
            )
            response = validate_sync_response(
                response,
                notification_mode=NOTIFICATION_MODE_SUPPRESS,
                cycle_id=cycle_id,
                plex_user_id=account.user_id,
                onboarding_requested=entry["onboardingRequested"],
            )
            event["youtrackSuppress"] = response
            if response["onboardingCompleted"]:
                registry.confirm_onboarding(account)
                entry["onboardingRequested"] = False
            if response["memberNotificationPermitRequired"]:
                candidates.append({**entry, "suppress": response})
            processed += 1
        except RemoteApiError as exc:
            skip_reason = deterministic_identity_skip_reason(exc)
            if skip_reason is not None:
                event["youtrackSuppressSkipped"] = skip_reason
                processed += 1
                continue
            errors += 1
            print(
                json.dumps(
                    {
                        "event": "sync-error",
                        "phase": NOTIFICATION_MODE_SUPPRESS,
                        "username": account.username,
                        "message": str(exc),
                    }
                ),
                file=sys.stderr,
            )

    if config.dry_run:
        for entry in entries:
            print(json.dumps(entry["event"], sort_keys=True))
        if errors == 0:
            registry.data["lastCompletedAt"] = observed_at.isoformat()
        registry.save()
        print(
            json.dumps(
                {
                    "event": "complete",
                    "processed": processed,
                    "excluded": excluded,
                    "errors": errors,
                    "notificationCandidates": len(candidates),
                    "notificationPermitStatus": (
                        "dry-run-preview"
                        if errors == 0
                        else "blocked-by-suppress-errors"
                    ),
                },
                sort_keys=True,
            )
        )
        return 1 if errors else 0

    permit_status = "not-needed"
    if candidates:
        permit_status = "deferred"
    # A daily scheduler can start the next cycle before 24 hours have elapsed
    # from the previous cycle's later outbound permit. Recheck against the
    # actual permit-attempt clock after suppression so a safe candidate is not
    # unnecessarily deferred until the following day. Keep observed_at fixed
    # for account classification and fail safely if the clock moves backwards.
    permit_attempt_at = max(observed_at.astimezone(UTC), utc_now())
    permit_available = registry.notification_permit_available(permit_attempt_at)
    if errors == 0 and candidates and permit_available:
        selected = min(
            candidates,
            key=lambda item: (
                candidate_priority(item["suppress"]),
                registry.last_notification_permit_at(item["account"], observed_at),
                item["account"].username.casefold(),
                item["account"].user_id,
            ),
        )
        selected_account = selected["account"]
        registry.reserve_notification_permit(
            cycle_id=cycle_id,
            account=selected_account,
            observed_at=permit_attempt_at,
        )
        permit_status = "reserved"
        try:
            permit_response = youtrack.sync(
                selected_account,
                selected["decision"],
                onboarding_requested=selected["onboardingRequested"],
                notification_mode=NOTIFICATION_MODE_PERMIT,
                cycle_id=cycle_id,
            )
            permit_response = validate_sync_response(
                permit_response,
                notification_mode=NOTIFICATION_MODE_PERMIT,
                cycle_id=cycle_id,
                plex_user_id=selected_account.user_id,
                onboarding_requested=selected["onboardingRequested"],
            )
            selected["event"]["youtrackPermit"] = permit_response
            if permit_response["onboardingCompleted"]:
                registry.confirm_onboarding(selected_account)
                selected["onboardingRequested"] = False
            if permit_response["memberNotificationPermitReserved"]:
                permit_status = "confirmed"
            elif permit_response.get("action") == NOTIFICATION_BUDGET_EXHAUSTED_ACTION:
                permit_status = "server-budget-exhausted"
            else:
                permit_status = "no-longer-required"
            registry.confirm_notification_permit(
                cycle_id=cycle_id,
                status=permit_status,
            )
        except RemoteApiError as exc:
            errors += 1
            permit_status = "ambiguous-failure"
            print(
                json.dumps(
                    {
                        "event": "sync-error",
                        "phase": NOTIFICATION_MODE_PERMIT,
                        "username": selected_account.username,
                        "message": str(exc),
                    }
                ),
                file=sys.stderr,
            )
    elif errors == 0 and candidates and not permit_available:
        permit_status = "local-budget-exhausted"
    elif errors:
        permit_status = "blocked-by-suppress-errors"

    for entry in entries:
        print(json.dumps(entry["event"], sort_keys=True))

    if errors == 0:
        registry.data["lastCompletedAt"] = observed_at.isoformat()
    registry.save()
    print(
        json.dumps(
            {
                "event": "complete",
                "processed": processed,
                "excluded": excluded,
                "errors": errors,
                "notificationCandidates": len(candidates),
                "notificationPermitStatus": permit_status,
            },
            sort_keys=True,
        )
    )
    return 1 if errors else 0


def run(config: Config) -> int:
    if config.interval_seconds == 0:
        return run_once(config)

    while True:
        try:
            exit_code = run_once(config)
        except (ConfigurationError, RemoteApiError) as exc:
            exit_code = 1
            print(json.dumps({"event": "run-error", "message": str(exc)}), file=sys.stderr)
        print(
            json.dumps(
                {
                    "event": "sleep",
                    "seconds": config.interval_seconds,
                    "previousExitCode": exit_code,
                }
            )
        )
        time.sleep(config.interval_seconds)


def main(argv: Iterable[str] | None = None) -> int:
    del argv
    try:
        return run(Config.from_env())
    except (ConfigurationError, RemoteApiError) as exc:
        print(json.dumps({"event": "fatal", "message": str(exc)}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
