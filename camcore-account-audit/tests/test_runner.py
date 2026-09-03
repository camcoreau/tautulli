import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "audit.py"
RUNNER_PATH = ROOT / "runner.py"

AUDIT_SPEC = importlib.util.spec_from_file_location("audit", AUDIT_PATH)
audit = importlib.util.module_from_spec(AUDIT_SPEC)
assert AUDIT_SPEC.loader is not None
sys.modules["audit"] = audit
AUDIT_SPEC.loader.exec_module(audit)

RUNNER_SPEC = importlib.util.spec_from_file_location("cma_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(RUNNER_SPEC)
assert RUNNER_SPEC.loader is not None
sys.modules[RUNNER_SPEC.name] = runner
RUNNER_SPEC.loader.exec_module(runner)


NOW = datetime(2026, 9, 3, 7, 0, tzinfo=timezone.utc)
MISSING_REPORTER = audit.RemoteHttpError(
    "missing reporter",
    status_code=422,
    detail=json.dumps(
        {"error": "No unique YouTrack Helpdesk reporter matches the Plex email address"}
    ),
)


def config(*, dry_run=False, token="sync-token"):
    return audit.Config(
        tautulli_url="https://tautulli.example.invalid",
        tautulli_api_key="tautulli-token",
        youtrack_sync_url=(
            "https://youtrack.example.invalid/api/admin/projects/CMA/"
            "extensionEndpoints/cma-account-audit/account-sync/sync-account"
        ),
        youtrack_token=token,
        registry_path=Path("registry.json"),
        dry_run=dry_run,
    )


def member():
    return audit.Account(
        user_id="845723198",
        username="justi8202",
        email="justi@example.invalid",
        last_streamed=None,
        total_plays=0,
        watch_seconds=0,
    )


def decision():
    return audit.Decision(
        account_status="Never Used",
        review_needed=False,
        reason="no plays; observation period is under 14 days",
    )


class RecordingHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected HTTP call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class ReporterProvisionerTests(unittest.TestCase):
    def test_rejects_reusing_the_sync_token_for_global_user_creation(self):
        with self.assertRaisesRegex(audit.ConfigurationError, "separate least-privilege"):
            runner.ReporterProvisioner(
                config(),
                RecordingHttp([]),
                token="sync-token",
            )

    def test_lookup_requires_an_exact_unique_email(self):
        http = RecordingHttp(
            [
                {
                    "users": [
                        {
                            "id": "1",
                            "login": "one",
                            "profile": {
                                "email": {
                                    "email": "other@example.invalid",
                                    "verified": False,
                                }
                            },
                        }
                    ]
                }
            ]
        )
        provisioner = runner.ReporterProvisioner(
            config(),
            http,
            token="provision-token",
        )
        with self.assertRaisesRegex(audit.RemoteApiError, "non-exact"):
            provisioner.ensure(member())

    def test_creates_reporter_with_deterministic_login_and_unverified_email(self):
        created = {
            "id": "hub-user-1",
            "login": runner.ReporterProvisioner._login(member()),
            "name": "justi8202",
            "userType": {"id": "REPORTER"},
            "profile": {
                "email": {
                    "email": "justi@example.invalid",
                    "verified": False,
                }
            },
        }
        http = RecordingHttp([{"users": []}, created])
        provisioner = runner.ReporterProvisioner(
            config(),
            http,
            token="provision-token",
        )

        self.assertEqual("created", provisioner.ensure(member()))
        self.assertEqual(2, len(http.calls))
        create_url, create_kwargs = http.calls[1]
        self.assertIn("/hub/api/rest/users?", create_url)
        self.assertEqual("POST", create_kwargs["method"])
        self.assertEqual(
            {"Authorization": "Bearer provision-token"},
            create_kwargs["headers"],
        )
        self.assertEqual("REPORTER", create_kwargs["body"]["userType"]["id"])
        self.assertEqual(
            "justi@example.invalid",
            create_kwargs["body"]["profile"]["email"]["email"],
        )
        self.assertFalse(create_kwargs["body"]["profile"]["email"]["verified"])
        self.assertNotIn("justi", create_kwargs["body"]["login"])


class ProvisioningYouTrackClientTests(unittest.TestCase):
    def call_sync(self, client):
        return client.sync(
            member(),
            decision(),
            onboarding_requested=True,
            notification_mode=audit.NOTIFICATION_MODE_SUPPRESS,
            cycle_id="audit-" + "a" * 32,
        )

    def test_live_onboarding_provisions_missing_reporter_then_retries_suppress(self):
        created = {
            "id": "hub-user-1",
            "login": runner.ReporterProvisioner._login(member()),
            "name": "justi8202",
            "userType": {"id": "REPORTER"},
            "profile": {
                "email": {
                    "email": "justi@example.invalid",
                    "verified": False,
                }
            },
        }
        planned = {"result": "deferred"}
        http = RecordingHttp(
            [
                MISSING_REPORTER,
                {"users": []},
                created,
                planned,
            ]
        )
        with mock.patch.dict(
            os.environ,
            {
                runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token",
                runner.REPORTER_HUB_URL_ENV: "https://youtrack.example.invalid/hub/api/rest",
            },
            clear=False,
        ):
            client = runner.ProvisioningYouTrackClient(config(), http)
            output = io.StringIO()
            with redirect_stdout(output):
                result = self.call_sync(client)

        self.assertIs(planned, result)
        self.assertEqual(4, len(http.calls))
        event = json.loads(output.getvalue().strip())
        self.assertEqual("reporter-provisioned", event["event"])
        self.assertEqual("created", event["outcome"])
        self.assertEqual("justi8202", event["username"])
        self.assertNotIn("example.invalid", output.getvalue())

    def test_dry_run_never_provisions_a_reporter(self):
        http = RecordingHttp([MISSING_REPORTER])
        with mock.patch.dict(
            os.environ,
            {runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token"},
            clear=False,
        ):
            client = runner.ProvisioningYouTrackClient(config(dry_run=True), http)
            with self.assertRaises(audit.RemoteHttpError):
                self.call_sync(client)

        self.assertEqual(1, len(http.calls))
        self.assertNotIn("/hub/api/rest/users", http.calls[0][0])

    def test_non_onboarding_sync_does_not_provision(self):
        http = RecordingHttp([MISSING_REPORTER])
        with mock.patch.dict(
            os.environ,
            {runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token"},
            clear=False,
        ):
            client = runner.ProvisioningYouTrackClient(config(), http)
            with self.assertRaises(audit.RemoteHttpError):
                client.sync(
                    member(),
                    decision(),
                    onboarding_requested=False,
                    notification_mode=audit.NOTIFICATION_MODE_SUPPRESS,
                    cycle_id="audit-" + "a" * 32,
                )
        self.assertEqual(1, len(http.calls))

    def test_permit_mode_never_provisions_a_reporter(self):
        http = RecordingHttp([MISSING_REPORTER])
        with mock.patch.dict(
            os.environ,
            {runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token"},
            clear=False,
        ):
            client = runner.ProvisioningYouTrackClient(config(), http)
            with self.assertRaises(audit.RemoteHttpError):
                client.sync(
                    member(),
                    decision(),
                    onboarding_requested=True,
                    notification_mode=audit.NOTIFICATION_MODE_PERMIT,
                    cycle_id="audit-" + "a" * 32,
                )
        self.assertEqual(1, len(http.calls))

    def test_persistent_missing_reporter_after_provisioning_fails_closed(self):
        created = {
            "id": "hub-user-1",
            "login": runner.ReporterProvisioner._login(member()),
            "name": "justi8202",
            "userType": {"id": "REPORTER"},
            "profile": {
                "email": {
                    "email": "justi@example.invalid",
                    "verified": False,
                }
            },
        }
        http = RecordingHttp(
            [
                MISSING_REPORTER,
                {"users": []},
                created,
                MISSING_REPORTER,
                MISSING_REPORTER,
                MISSING_REPORTER,
                MISSING_REPORTER,
            ]
        )
        with mock.patch.dict(
            os.environ,
            {runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token"},
            clear=False,
        ), mock.patch.object(runner.time, "sleep"):
            client = runner.ProvisioningYouTrackClient(config(), http)
            with self.assertRaisesRegex(audit.RemoteApiError, "did not become a unique"):
                self.call_sync(client)

        self.assertEqual(7, len(http.calls))


if __name__ == "__main__":
    unittest.main()
