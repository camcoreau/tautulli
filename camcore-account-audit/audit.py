#!/usr/bin/env python3
"""Synchronize Tautulli account activity into the CMA YouTrack helpdesk project."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


UTC = timezone.utc
DEFAULT_USER_AGENT = "CamCore-CMA-Account-Audit/1.0"
JS_MAX_SAFE_INTEGER = (2**53) - 1
MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


class RemoteApiError(RuntimeError):
    """Raised when Tautulli or YouTrack rejects a request."""


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
        if not dry_run and not sync_url:
            missing.append("YOUTRACK_URL or YOUTRACK_SYNC_URL")
        if not dry_run and not youtrack_token:
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

        request = urllib.request.Request(
            url,
            data=encoded_body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RemoteApiError(
                f"{method} {display_url} returned HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RemoteApiError(f"{method} {display_url} failed: {exc.reason}") from exc

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

    def sync(self, account: Account, decision: Decision) -> Any:
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
        }
        return self.http.request(
            self.config.youtrack_sync_url,
            method="POST",
            headers={"Authorization": f"Bearer {self.config.youtrack_token}"},
            body=payload,
        )


class Registry:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {"schemaVersion": 1, "users": {}}

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"Cannot read registry {self.path}: {exc}") from exc
        if loaded.get("schemaVersion") != 1 or not isinstance(loaded.get("users"), dict):
            raise ConfigurationError(f"Unsupported registry format in {self.path}")
        self.data = loaded

    def first_seen(self, account: Account, observed_at: datetime) -> datetime:
        users = self.data["users"]
        entry = users.setdefault(
            account.user_id,
            {
                "firstSeenAt": observed_at.isoformat(),
                "lastSeenAt": observed_at.isoformat(),
                "username": account.username,
            },
        )
        entry["lastSeenAt"] = observed_at.isoformat()
        entry["username"] = account.username
        try:
            return datetime.fromisoformat(entry["firstSeenAt"]).astimezone(UTC)
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Invalid firstSeenAt for Plex user ID {account.user_id}"
            ) from exc

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(self.path.name + ".tmp")
        temp_path.write_text(
            json.dumps(self.data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, self.path)


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
    registry.load()

    errors = 0
    processed = 0
    excluded = 0
    for account in tautulli.accounts():
        if account.username.casefold() in config.excluded_users:
            excluded += 1
            print(json.dumps({"event": "excluded", "username": account.username}))
            continue

        first_seen = registry.first_seen(account, observed_at)
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
        }

        if config.dry_run:
            print(json.dumps(event, sort_keys=True))
            processed += 1
            continue

        try:
            event["youtrack"] = youtrack.sync(account, decision)
            print(json.dumps(event, sort_keys=True))
            processed += 1
        except RemoteApiError as exc:
            errors += 1
            print(
                json.dumps(
                    {
                        "event": "sync-error",
                        "username": account.username,
                        "message": str(exc),
                    }
                ),
                file=sys.stderr,
            )

    registry.data["lastCompletedAt"] = observed_at.isoformat()
    registry.save()
    print(
        json.dumps(
            {
                "event": "complete",
                "processed": processed,
                "excluded": excluded,
                "errors": errors,
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
