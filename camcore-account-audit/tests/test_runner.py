import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
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
        user_id="999000001",
        username="synthetic-member",
        email="synthetic-member@example.invalid",
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


def provisioning_enabled():
    """Enable the parked in-source provisioning gate for tests of the feature itself.

    REPORTER_PROVISIONING_ENABLED is False in shipped builds (OPS-271). Tests that
    exercise provisioning must opt in explicitly, so that each remaining gate
    (dry-run, onboarding, notification mode) is still proven in isolation rather
    than passing because the parked constant short-circuits everything.
    """
    return mock.patch.object(runner, "REPORTER_PROVISIONING_ENABLED", True)



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
        with provisioning_enabled():
            with self.assertRaisesRegex(audit.RemoteApiError, "non-exact"):
                provisioner.ensure(member())

    def test_creates_reporter_with_deterministic_login_and_unverified_email(self):
        created = {
            "id": "hub-user-1",
            "login": runner.ReporterProvisioner._login(member()),
            "name": "synthetic-member",
            "userType": {"id": "REPORTER"},
            "profile": {
                "email": {
                    "email": "synthetic-member@example.invalid",
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

        with provisioning_enabled():
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
            "synthetic-member@example.invalid",
            create_kwargs["body"]["profile"]["email"]["email"],
        )
        self.assertFalse(create_kwargs["body"]["profile"]["email"]["verified"])
        self.assertNotIn("synthetic", create_kwargs["body"]["login"])


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
            "name": "synthetic-member",
            "userType": {"id": "REPORTER"},
            "profile": {
                "email": {
                    "email": "synthetic-member@example.invalid",
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
        ), provisioning_enabled():
            client = runner.ProvisioningYouTrackClient(config(), http)
            output = io.StringIO()
            with redirect_stdout(output):
                result = self.call_sync(client)

        self.assertIs(planned, result)
        self.assertEqual(4, len(http.calls))
        event = json.loads(output.getvalue().strip())
        self.assertEqual("reporter-provisioned", event["event"])
        self.assertEqual("created", event["outcome"])
        self.assertEqual("synthetic-member", event["username"])
        self.assertNotIn("example.invalid", output.getvalue())

    def test_dry_run_never_provisions_a_reporter(self):
        http = RecordingHttp([MISSING_REPORTER])
        with mock.patch.dict(
            os.environ,
            {runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token"},
            clear=False,
        ), provisioning_enabled():
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
        ), provisioning_enabled():
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
        ), provisioning_enabled():
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
            "name": "synthetic-member",
            "userType": {"id": "REPORTER"},
            "profile": {
                "email": {
                    "email": "synthetic-member@example.invalid",
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
        ), mock.patch.object(runner.time, "sleep"), provisioning_enabled():
            client = runner.ProvisioningYouTrackClient(config(), http)
            with self.assertRaisesRegex(audit.RemoteApiError, "did not become a unique"):
                self.call_sync(client)

        self.assertEqual(7, len(http.calls))


class ParkedProvisioningTests(unittest.TestCase):
    """OPS-271: provisioning is parked behind an in-source constant.

    The parked state must hold at process startup, before audit.run's scheduled
    loop exists, and must not be reachable by configuration alone.
    """

    class Sentinel:
        """Stand-in for the ordinary audit.YouTrackClient."""

    def env_without_provisioning(self, **overrides):
        env = dict(os.environ)
        env.pop(runner.REPORTER_PROVISION_TOKEN_ENV, None)
        env.pop(runner.REPORTER_HUB_URL_ENV, None)
        env.update(overrides)
        return mock.patch.dict(os.environ, env, clear=True)

    def env_with_provisioning_token(self, **overrides):
        env = dict(os.environ)
        env[runner.REPORTER_PROVISION_TOKEN_ENV] = "injected-token"
        env.update(overrides)
        return mock.patch.dict(os.environ, env, clear=True)

    def test_shipped_default_is_parked(self):
        self.assertFalse(runner.REPORTER_PROVISIONING_ENABLED)

    def test_injected_token_is_rejected_at_interval_zero(self):
        stderr = io.StringIO()
        with self.env_with_provisioning_token(AUDIT_INTERVAL_SECONDS="0"), mock.patch.object(
            audit, "main"
        ) as audit_main, redirect_stderr(stderr):
            result = runner.main()

        self.assertEqual(runner.PARKED_EXIT_CODE, result)
        audit_main.assert_not_called()

    def test_injected_token_is_rejected_at_production_interval_without_sleeping(self):
        """The check must precede the run loop, not live inside it.

        audit.run catches (ConfigurationError, RemoteApiError) inside `while True`
        and then sleeps AUDIT_INTERVAL_SECONDS. A check raised during per-cycle
        client construction would therefore log and sleep for 24 hours instead of
        exiting. Asserting that sleep is never reached is the point of this test.
        """
        stderr = io.StringIO()
        with self.env_with_provisioning_token(
            AUDIT_INTERVAL_SECONDS="86400"
        ), mock.patch.object(audit, "main") as audit_main, mock.patch.object(
            audit.time, "sleep"
        ) as audit_sleep, mock.patch.object(
            runner.time, "sleep"
        ) as runner_sleep, redirect_stderr(
            stderr
        ):
            result = runner.main()

        self.assertEqual(runner.PARKED_EXIT_CODE, result)
        audit_main.assert_not_called()
        audit_sleep.assert_not_called()
        runner_sleep.assert_not_called()

    def test_rejection_emits_a_structured_startup_aborted_event_on_stderr(self):
        stderr = io.StringIO()
        with self.env_with_provisioning_token(), mock.patch.object(
            audit, "main"
        ), redirect_stderr(stderr):
            runner.main()

        event = json.loads(stderr.getvalue().strip())
        self.assertEqual("startup-aborted", event["event"])
        self.assertEqual("reporter-provisioning-parked", event["reason"])
        self.assertIn(runner.REPORTER_PROVISION_TOKEN_ENV, event["detail"])
        self.assertNotIn("injected-token", stderr.getvalue())

    def test_parked_build_does_not_install_the_provisioning_client(self):
        for interval in ("0", "86400"):
            with self.subTest(interval=interval):
                with self.env_without_provisioning(
                    AUDIT_INTERVAL_SECONDS=interval
                ), mock.patch.object(
                    audit, "YouTrackClient", self.Sentinel
                ), mock.patch.object(
                    audit, "main", return_value=0
                ) as audit_main:
                    result = runner.main()
                    self.assertIs(audit.YouTrackClient, self.Sentinel)

                self.assertEqual(0, result)
                audit_main.assert_called_once_with()

    def test_parked_build_ignores_a_foreign_hub_url(self):
        """YOUTRACK_HUB_URL is only validated when ReporterProvisioner is built.

        While parked it is never built, so a hub URL pointing at another host is
        inert. The companion assertion below proves that is a real hazard when the
        provisioning client IS installed - it raises rather than being ignored.
        """
        foreign = "https://not-youtrack.example.invalid/hub/api/rest"

        with self.env_without_provisioning(
            YOUTRACK_HUB_URL=foreign, AUDIT_INTERVAL_SECONDS="86400"
        ), mock.patch.object(audit, "YouTrackClient", self.Sentinel), mock.patch.object(
            audit, "main", return_value=0
        ) as audit_main:
            result = runner.main()
            self.assertIs(audit.YouTrackClient, self.Sentinel)

        self.assertEqual(0, result)
        audit_main.assert_called_once_with()

        with mock.patch.dict(
            os.environ, {runner.REPORTER_HUB_URL_ENV: foreign}, clear=False
        ), provisioning_enabled():
            with self.assertRaisesRegex(
                audit.ConfigurationError, "same YouTrack scheme and host"
            ):
                runner.ProvisioningYouTrackClient(config(), RecordingHttp([]))

    def test_install_only_happens_when_the_source_constant_is_enabled(self):
        with self.env_without_provisioning(), mock.patch.object(
            audit, "YouTrackClient", self.Sentinel
        ), mock.patch.object(audit, "main", return_value=0), provisioning_enabled():
            runner.main()
            # install() ran, replacing the sentinel with the provisioning client.
            self.assertIs(audit.YouTrackClient, runner.ProvisioningYouTrackClient)

        # mock.patch.object restores the pre-test binding on exit, so the rebind
        # performed by install() does not leak into other tests.
        self.assertIsNot(audit.YouTrackClient, self.Sentinel)

    def test_enabled_property_is_false_while_parked(self):
        with mock.patch.dict(
            os.environ,
            {runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token"},
            clear=False,
        ):
            provisioner = runner.ReporterProvisioner(
                config(), RecordingHttp([]), token="provision-token"
            )
            self.assertFalse(provisioner.enabled)
            with provisioning_enabled():
                self.assertTrue(provisioner.enabled)

    def test_ensure_refuses_while_parked(self):
        provisioner = runner.ReporterProvisioner(
            config(), RecordingHttp([]), token="provision-token"
        )
        with self.assertRaisesRegex(audit.ConfigurationError, "not enabled"):
            provisioner.ensure(member())


if __name__ == "__main__":
    unittest.main()
