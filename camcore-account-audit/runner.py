#!/usr/bin/env python3
"""Run the CMA audit with optional, fail-closed Helpdesk reporter provisioning."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
from typing import Any

import audit


REPORTER_PROVISION_TOKEN_ENV = "YOUTRACK_REPORTER_PROVISION_TOKEN"
REPORTER_HUB_URL_ENV = "YOUTRACK_HUB_URL"
REPORTER_VISIBILITY_RETRY_DELAYS_SECONDS = (0.25, 0.5, 1.0)


class ReporterProvisioner:
    """Create one Reporter-type YouTrack account for a new Plex member."""

    def __init__(
        self,
        config: audit.Config,
        http: audit.JsonHttpClient,
        *,
        token: str | None = None,
        hub_url: str | None = None,
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
        self.hub_url = self._validated_hub_url(hub_url)

    @property
    def enabled(self) -> bool:
        return bool(self.token) and not self.config.dry_run

    def _validated_hub_url(self, override: str | None) -> str:
        sync = urllib.parse.urlsplit(self.config.youtrack_sync_url)
        if sync.scheme not in {"http", "https"} or not sync.netloc:
            raise audit.ConfigurationError("YOUTRACK_SYNC_URL cannot locate the YouTrack host")

        raw = (
            override
            if override is not None
            else os.getenv(REPORTER_HUB_URL_ENV, "").strip()
        )
        if not raw:
            raw = urllib.parse.urlunsplit(
                (sync.scheme, sync.netloc, "/hub/api/rest", "", "")
            )
        hub = urllib.parse.urlsplit(raw.rstrip("/"))
        if hub.scheme != sync.scheme or hub.netloc != sync.netloc:
            raise audit.ConfigurationError(
                f"{REPORTER_HUB_URL_ENV} must use the same YouTrack scheme and host"
            )
        return urllib.parse.urlunsplit(
            (hub.scheme, hub.netloc, hub.path.rstrip("/"), "", "")
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def _exact_email(user: Any) -> str | None:
        if not isinstance(user, dict):
            return None
        profile = user.get("profile")
        if not isinstance(profile, dict):
            return None
        email = profile.get("email")
        if not isinstance(email, dict):
            return None
        value = email.get("email")
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _lookup(self, email: str) -> dict[str, Any] | None:
        query = urllib.parse.urlencode(
            {
                "query": f"email:{email}",
                "fields": "id,login,name,userType(id),profile(email)",
            }
        )
        payload = self.http.request(
            f"{self.hub_url}/users?{query}",
            headers=self._headers(),
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("users"), list):
            raise audit.RemoteApiError("YouTrack Hub reporter lookup returned invalid JSON")

        users = payload["users"]
        exact = [
            user
            for user in users
            if (self._exact_email(user) or "").casefold() == email.casefold()
        ]
        if len(exact) > 1:
            raise audit.RemoteApiError(
                "Multiple YouTrack users already match the Plex email address"
            )
        if len(exact) == 1:
            return exact[0]
        if users:
            raise audit.RemoteApiError(
                "YouTrack Hub reporter lookup returned non-exact email matches"
            )
        return None

    @staticmethod
    def _login(account: audit.Account) -> str:
        digest = hashlib.sha256(account.user_id.encode("utf-8")).hexdigest()[:16]
        return f"cma-plex-{digest}"

    def _create(self, account: audit.Account) -> dict[str, Any]:
        if not account.email:
            raise audit.RemoteApiError("Cannot provision a Helpdesk reporter without email")
        query = urllib.parse.urlencode(
            {"fields": "id,login,name,userType(id),profile(email)"}
        )
        payload = {
            "login": self._login(account),
            "name": account.username,
            "userType": {"id": "REPORTER"},
            "profile": {
                "email": {
                    "email": account.email,
                    "verified": False,
                }
            },
        }
        created = self.http.request(
            f"{self.hub_url}/users?{query}",
            method="POST",
            headers=self._headers(),
            body=payload,
        )
        if not isinstance(created, dict):
            raise audit.RemoteApiError("YouTrack Hub reporter creation returned invalid JSON")
        if (self._exact_email(created) or "").casefold() != account.email.casefold():
            raise audit.RemoteApiError(
                "YouTrack Hub reporter creation did not return the requested email"
            )
        user_type = created.get("userType")
        if not isinstance(user_type, dict) or user_type.get("id") != "REPORTER":
            raise audit.RemoteApiError(
                "YouTrack Hub reporter creation did not return Reporter user type"
            )
        return created

    def ensure(self, account: audit.Account) -> str:
        if not self.enabled:
            raise audit.ConfigurationError("Helpdesk reporter provisioning is not enabled")
        if not account.email:
            raise audit.RemoteApiError("Cannot provision a Helpdesk reporter without email")
        existing = self._lookup(account.email)
        if existing is not None:
            return "existing"
        self._create(account)
        return "created"


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
            eligible = (
                self.reporter_provisioner.enabled
                and onboarding_requested
                and notification_mode == audit.NOTIFICATION_MODE_SUPPRESS
                and self._is_missing_reporter(exc)
            )
            if not eligible:
                raise

        outcome = self.reporter_provisioner.ensure(account)
        print(
            json.dumps(
                {
                    "event": "reporter-provisioned",
                    "plexUserId": account.user_id,
                    "username": account.username,
                    "outcome": outcome,
                },
                sort_keys=True,
            )
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
            except audit.RemoteHttpError as exc:
                if not self._is_missing_reporter(exc):
                    raise
                last_missing = exc

        raise audit.RemoteApiError(
            "Provisioned Helpdesk reporter did not become a unique YouTrack email match"
        ) from last_missing


def install() -> None:
    audit.YouTrackClient = ProvisioningYouTrackClient


def main() -> int:
    install()
    return audit.main()


if __name__ == "__main__":
    raise SystemExit(main())
