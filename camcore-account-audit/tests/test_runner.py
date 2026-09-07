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
MISSING_REPORTER_DETAIL = json.dumps(
    {"error": "No unique YouTrack Helpdesk reporter matches the Plex email address"}
)


def missing_reporter():
    return audit.RemoteHttpError(
        "missing reporter", status_code=422, detail=MISSING_REPORTER_DETAIL
    )


API = "https://youtrack.example.invalid/api"
EMAIL = "synthetic-member@example.invalid"


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


def member(email=EMAIL):
    return audit.Account(
        user_id="999000001",
        username="synthetic-member",
        email=email,
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


def login():
    return runner.ReporterProvisioner.login_for(member())


def user(uid="2-99", *, login_value=None, email=EMAIL, user_type="REPORTER", banned=False):
    return {
        "id": uid,
        "login": login_value or login(),
        "fullName": "synthetic-member",
        "email": email,
        "banned": banned,
        "userType": {"id": user_type},
    }


def directory(*users):
    """A directory page that always exposes at least one email (the admin)."""
    return [
        {
            "id": "2-1",
            "login": "admin",
            "fullName": "Admin",
            "email": "admin@example.invalid",
            "banned": False,
            "userType": {"id": "STANDARD_USER"},
        },
        *users,
    ]


class RecordingHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"unexpected HTTP call: {url}")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def provisioning_env(**overrides):
    env = {
        runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token",
        runner.REPORTER_PROVISIONING_ENABLED_ENV: "true",
    }
    env.update(overrides)
    return mock.patch.dict(os.environ, env, clear=False)


class ResetTrip(unittest.TestCase):
    def setUp(self):
        runner.reset_trip_for_tests()

    def tearDown(self):
        runner.reset_trip_for_tests()


class ReporterProvisionerConfigTests(ResetTrip):
    def test_rejects_reusing_the_sync_token(self):
        with self.assertRaisesRegex(audit.ConfigurationError, "separate least-privilege"):
            runner.ReporterProvisioner(config(), RecordingHttp([]), token="sync-token")

    def test_api_url_defaults_to_the_sync_host_api_root(self):
        provisioner = runner.ReporterProvisioner(
            config(), RecordingHttp([]), token="provision-token", enabled=True
        )
        self.assertEqual(API, provisioner.api_url)

    def test_foreign_api_url_is_rejected(self):
        with self.assertRaisesRegex(audit.ConfigurationError, "same YouTrack scheme and host"):
            runner.ReporterProvisioner(
                config(),
                RecordingHttp([]),
                token="provision-token",
                api_url="https://not-youtrack.example.invalid/api",
            )

    def test_non_api_root_path_is_rejected(self):
        with self.assertRaisesRegex(audit.ConfigurationError, "/api root"):
            runner.ReporterProvisioner(
                config(),
                RecordingHttp([]),
                token="provision-token",
                api_url="https://youtrack.example.invalid/hub/api/rest",
            )

    def test_enabled_requires_flag_token_live_mode_and_no_trip(self):
        self.assertFalse(
            runner.ReporterProvisioner(
                config(), RecordingHttp([]), token="provision-token", enabled=False
            ).enabled
        )
        self.assertFalse(
            runner.ReporterProvisioner(
                config(), RecordingHttp([]), token="", enabled=True
            ).enabled
        )
        self.assertFalse(
            runner.ReporterProvisioner(
                config(dry_run=True), RecordingHttp([]), token="provision-token", enabled=True
            ).enabled
        )
        live = runner.ReporterProvisioner(
            config(), RecordingHttp([]), token="provision-token", enabled=True
        )
        self.assertTrue(live.enabled)
        with redirect_stderr(io.StringIO()):
            live._trip("test", None)
        self.assertFalse(live.enabled)

    def test_ensure_refuses_when_disabled(self):
        provisioner = runner.ReporterProvisioner(
            config(), RecordingHttp([]), token="provision-token", enabled=False
        )
        with self.assertRaisesRegex(audit.ConfigurationError, "not enabled"):
            provisioner.ensure(member())


class ReporterProvisionerLookupTests(ResetTrip):
    def provisioner(self, http):
        return runner.ReporterProvisioner(
            config(), http, token="provision-token", enabled=True
        )

    def test_enumeration_pages_until_a_short_page(self):
        full_page = [user(f"2-{n}", login_value=f"u{n}", email=f"u{n}@example.invalid")
                     for n in range(runner.USER_PAGE_SIZE)]
        http = RecordingHttp([full_page, directory(user())])
        matches = self.provisioner(http).lookup(EMAIL)
        self.assertEqual(2, len(http.calls))
        self.assertIn("$top=100&$skip=0", http.calls[0][0])
        self.assertIn(f"$top=100&$skip={runner.USER_PAGE_SIZE}", http.calls[1][0])
        self.assertIn("fields=id%2Clogin%2CfullName%2Cemail%2Cbanned%2CuserType%28id%29", http.calls[0][0])
        self.assertEqual(["2-99"], [u["id"] for u in matches])

    def test_lookup_matches_email_case_insensitively(self):
        http = RecordingHttp([directory(user(email="Synthetic-Member@Example.INVALID"))])
        self.assertEqual(1, len(self.provisioner(http).lookup(EMAIL)))

    def test_lookup_returns_every_match_of_any_type(self):
        http = RecordingHttp(
            [directory(user("2-5", login_value="a", user_type="STANDARD_USER"), user("2-6", login_value="b"))]
        )
        self.assertEqual(["2-5", "2-6"], [u["id"] for u in self.provisioner(http).lookup(EMAIL)])

    def test_lookup_fails_closed_when_no_email_is_visible(self):
        http = RecordingHttp([[user("2-5", email=None), user("2-6", email=None)]])
        with self.assertRaisesRegex(audit.RemoteApiError, "exposed no email"):
            self.provisioner(http).lookup(EMAIL)

    def test_lookup_fails_closed_on_an_empty_directory(self):
        http = RecordingHttp([[]])
        with self.assertRaisesRegex(audit.RemoteApiError, "no users"):
            self.provisioner(http).lookup(EMAIL)

    def test_lookup_fails_closed_on_invalid_json(self):
        http = RecordingHttp([{"users": []}])
        with self.assertRaisesRegex(audit.RemoteApiError, "invalid JSON"):
            self.provisioner(http).lookup(EMAIL)

    def test_lookup_fails_closed_on_an_oversized_directory(self):
        pages = [
            [user(f"2-{p}-{n}", login_value=f"u{p}{n}", email=f"u{p}{n}@example.invalid")
             for n in range(runner.USER_PAGE_SIZE)]
            for p in range(runner.USER_MAX_PAGES)
        ]
        http = RecordingHttp(pages)
        with self.assertRaisesRegex(audit.RemoteApiError, "directory size"):
            self.provisioner(http).lookup(EMAIL)

    def test_uses_the_provisioning_bearer_token_only(self):
        http = RecordingHttp([directory()])
        self.provisioner(http).lookup(EMAIL)
        self.assertEqual({"Authorization": "Bearer provision-token"}, http.calls[0][1]["headers"])


class ReporterProvisionerCreateTests(ResetTrip):
    def provisioner(self, http):
        return runner.ReporterProvisioner(
            config(), http, token="provision-token", enabled=True
        )

    def test_creates_a_reporter_through_api_users_and_reads_it_back(self):
        http = RecordingHttp([directory(), user(), user()])
        output = io.StringIO()
        with redirect_stdout(output):
            outcome, created = self.provisioner(http).ensure(member())

        self.assertEqual("created", outcome)
        self.assertEqual("2-99", created["id"])
        self.assertEqual(3, len(http.calls))

        create_url, create_kwargs = http.calls[1]
        self.assertTrue(create_url.startswith(f"{API}/users?"))
        self.assertNotIn("/hub/", create_url)
        self.assertEqual("POST", create_kwargs["method"])
        self.assertEqual({"Authorization": "Bearer provision-token"}, create_kwargs["headers"])
        body = create_kwargs["body"]
        self.assertEqual(
            {"login", "fullName", "email", "password", "userType"}, set(body)
        )
        self.assertEqual(login(), body["login"])
        self.assertNotIn("synthetic", body["login"])
        self.assertEqual("synthetic-member", body["fullName"])
        self.assertEqual(EMAIL, body["email"])
        self.assertEqual({"id": "REPORTER"}, body["userType"])
        self.assertGreaterEqual(len(body["password"]), 32)
        self.assertNotIn(body["password"], output.getvalue())

        readback_url, readback_kwargs = http.calls[2]
        self.assertTrue(readback_url.startswith(f"{API}/users/2-99?"))
        self.assertEqual("GET", readback_kwargs.get("method", "GET"))

    def test_passwords_are_unique_per_create(self):
        http = RecordingHttp([directory(), user(), user(), directory(), user(), user()])
        provisioner = self.provisioner(http)
        provisioner.max_per_cycle = 2
        provisioner.ensure(member())
        provisioner.ensure(member())
        self.assertNotEqual(http.calls[1][1]["body"]["password"], http.calls[4][1]["body"]["password"])

    def test_existing_match_never_creates(self):
        http = RecordingHttp([directory(user(user_type="STANDARD_USER"))])
        outcome, created = self.provisioner(http).ensure(member())
        self.assertEqual(("existing", None), (outcome, created))
        self.assertEqual(1, len(http.calls))

    def test_wrong_type_on_create_trips_the_breaker(self):
        http = RecordingHttp([directory(), user(user_type="STANDARD_USER")])
        provisioner = self.provisioner(http)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaisesRegex(audit.RemoteApiError, "not REPORTER"):
                provisioner.ensure(member())

        self.assertEqual(2, len(http.calls))  # no readback after a failed create check
        self.assertIn("creation: user type is not REPORTER", runner.tripped_reason())
        self.assertFalse(provisioner.enabled)
        event = json.loads(stderr.getvalue().strip())
        self.assertEqual("reporter-provisioning-tripped", event["event"])
        self.assertEqual("2-99", event["user"]["id"])
        self.assertEqual(login(), event["user"]["login"])
        self.assertNotIn("example.invalid", stderr.getvalue())

    def test_wrong_identity_on_readback_trips_the_breaker(self):
        http = RecordingHttp([directory(), user(), user(email="someone-else@example.invalid")])
        provisioner = self.provisioner(http)
        with redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(audit.RemoteApiError, "readback"):
                provisioner.ensure(member())
        self.assertIn("readback: email mismatch", runner.tripped_reason())
        self.assertFalse(provisioner.enabled)

    def test_missing_id_or_login_mismatch_trips(self):
        http = RecordingHttp([directory(), {**user(), "id": "", "login": "other"}])
        with redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(audit.RemoteApiError, "missing id, login mismatch"):
                self.provisioner(http).ensure(member())
        self.assertIsNotNone(runner.tripped_reason())

    def test_tripped_breaker_persists_across_provisioner_instances(self):
        first = self.provisioner(RecordingHttp([directory(), user(user_type="AGENT")]))
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(audit.RemoteApiError):
                first.ensure(member())
        second = self.provisioner(RecordingHttp([]))
        self.assertFalse(second.enabled)
        with self.assertRaisesRegex(audit.ConfigurationError, "not enabled"):
            second.ensure(member())

    def test_http_rejection_on_create_is_an_error_without_tripping(self):
        rejected = audit.RemoteHttpError(
            "rejected", status_code=400, detail=json.dumps({"error": "login already exists"})
        )
        http = RecordingHttp([directory(), rejected])
        with self.assertRaises(audit.RemoteHttpError):
            self.provisioner(http).ensure(member())
        self.assertIsNone(runner.tripped_reason())

    def test_cycle_budget_is_enforced(self):
        http = RecordingHttp([directory(), user(), user()])
        provisioner = self.provisioner(http)
        provisioner.ensure(member())
        self.assertFalse(provisioner.cycle_budget_available)
        with self.assertRaisesRegex(audit.ConfigurationError, "budget"):
            provisioner.ensure(member())
        self.assertEqual(3, len(http.calls))

    def test_user_type_counts(self):
        counts = self.provisioner(RecordingHttp([])).user_type_counts(
            directory(user(), user("2-7", login_value="x", user_type="AGENT"), {"id": "2-8"})
        )
        self.assertEqual({"STANDARD_USER": 1, "REPORTER": 1, "AGENT": 1, "unknown": 1}, counts)


class ProvisioningYouTrackClientTests(ResetTrip):
    def client(self, http, *, dry_run=False):
        with provisioning_env():
            return runner.ProvisioningYouTrackClient(config(dry_run=dry_run), http)

    def call_sync(self, client, **overrides):
        kwargs = dict(
            onboarding_requested=True,
            notification_mode=audit.NOTIFICATION_MODE_SUPPRESS,
            cycle_id="audit-" + "a" * 32,
        )
        kwargs.update(overrides)
        return client.sync(member(), decision(), **kwargs)

    def test_live_onboarding_provisions_missing_reporter_then_retries_suppress(self):
        planned = {"result": "deferred"}
        http = RecordingHttp([missing_reporter(), directory(), user(), user(), planned])
        client = self.client(http)
        output = io.StringIO()
        with redirect_stdout(output):
            result = self.call_sync(client)

        self.assertIs(planned, result)
        self.assertEqual(5, len(http.calls))
        event = json.loads(output.getvalue().strip())
        self.assertEqual("reporter-provisioned", event["event"])
        self.assertEqual("created", event["outcome"])
        self.assertEqual("synthetic-member", event["username"])
        self.assertEqual({"id": "2-99", "login": login(), "userType": "REPORTER", "banned": False}, event["user"])
        self.assertNotIn("example.invalid", output.getvalue())
        self.assertNotIn(http.calls[2][1]["body"]["password"], output.getvalue())

    def test_existing_account_keeps_the_deterministic_skip_and_never_creates(self):
        http = RecordingHttp([missing_reporter(), directory(user(user_type="STANDARD_USER"))])
        client = self.client(http)
        output = io.StringIO()
        with redirect_stdout(output):
            with self.assertRaises(audit.RemoteHttpError) as raised:
                self.call_sync(client)

        self.assertEqual("reporter-match-unavailable", audit.deterministic_identity_skip_reason(raised.exception))
        self.assertEqual(2, len(http.calls))
        event = json.loads(output.getvalue().strip())
        self.assertEqual("reporter-provisioning-skipped", event["event"])
        self.assertEqual("existing-account-not-unique-match", event["reason"])

    def test_second_provisioning_in_a_cycle_is_a_deterministic_skip(self):
        planned = {"result": "deferred"}
        http = RecordingHttp([missing_reporter(), directory(), user(), user(), planned, missing_reporter()])
        client = self.client(http)
        with redirect_stdout(io.StringIO()):
            self.call_sync(client)
            output = io.StringIO()
            with redirect_stdout(output):
                with self.assertRaises(audit.RemoteHttpError) as raised:
                    self.call_sync(client)
        self.assertEqual("reporter-match-unavailable", audit.deterministic_identity_skip_reason(raised.exception))
        self.assertEqual(6, len(http.calls))
        self.assertEqual("cycle-budget-exhausted", json.loads(output.getvalue().strip())["reason"])

    def test_dry_run_never_provisions(self):
        http = RecordingHttp([missing_reporter()])
        client = self.client(http, dry_run=True)
        with self.assertRaises(audit.RemoteHttpError):
            self.call_sync(client)
        self.assertEqual(1, len(http.calls))

    def test_non_onboarding_sync_never_provisions(self):
        http = RecordingHttp([missing_reporter()])
        with self.assertRaises(audit.RemoteHttpError):
            self.call_sync(self.client(http), onboarding_requested=False)
        self.assertEqual(1, len(http.calls))

    def test_permit_mode_never_provisions(self):
        http = RecordingHttp([missing_reporter()])
        with self.assertRaises(audit.RemoteHttpError):
            self.call_sync(self.client(http), notification_mode=audit.NOTIFICATION_MODE_PERMIT)
        self.assertEqual(1, len(http.calls))

    def test_other_rejections_are_re_raised_untouched(self):
        other = audit.RemoteHttpError("conflict", status_code=409, detail=json.dumps({"error": "x"}))
        http = RecordingHttp([other])
        with self.assertRaises(audit.RemoteHttpError) as raised:
            self.call_sync(self.client(http))
        self.assertIs(other, raised.exception)

    def test_tripped_breaker_disables_provisioning_for_later_syncs(self):
        http = RecordingHttp([missing_reporter(), directory(), user(user_type="STANDARD_USER"), missing_reporter()])
        client = self.client(http)
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            with self.assertRaises(audit.RemoteApiError):
                self.call_sync(client)
            with self.assertRaises(audit.RemoteHttpError):
                self.call_sync(client)
        self.assertEqual(4, len(http.calls))

    def test_persistent_missing_reporter_after_provisioning_fails_closed(self):
        http = RecordingHttp(
            [missing_reporter(), directory(), user(), user()]
            + [missing_reporter() for _ in range(4)]
        )
        client = self.client(http)
        with mock.patch.object(runner.time, "sleep"), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(audit.RemoteApiError, "did not become a unique"):
                self.call_sync(client)
        self.assertEqual(8, len(http.calls))


class StartupTests(ResetTrip):
    class Sentinel:
        """Stand-in for the ordinary audit.YouTrackClient."""

    def clean_env(self, **overrides):
        env = dict(os.environ)
        for key in (
            runner.REPORTER_PROVISION_TOKEN_ENV,
            runner.REPORTER_PROVISIONING_ENABLED_ENV,
            runner.REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV,
            runner.REPORTER_API_URL_ENV,
            runner.LEGACY_HUB_URL_ENV,
        ):
            env.pop(key, None)
        env.update(overrides)
        return mock.patch.dict(os.environ, env, clear=True)

    def run_main(self, **env):
        stdout, stderr = io.StringIO(), io.StringIO()
        with self.clean_env(**env), mock.patch.object(
            audit, "YouTrackClient", self.Sentinel
        ), mock.patch.object(audit, "main", return_value=0) as audit_main, mock.patch.object(
            audit.time, "sleep"
        ) as audit_sleep, redirect_stdout(stdout), redirect_stderr(stderr):
            result = runner.main()
            installed = audit.YouTrackClient
        audit_sleep.assert_not_called()
        return result, installed, audit_main, stdout.getvalue(), stderr.getvalue()

    def test_default_is_disabled_and_does_not_install(self):
        result, installed, audit_main, stdout, stderr = self.run_main(AUDIT_INTERVAL_SECONDS="86400")
        self.assertEqual(0, result)
        self.assertIs(self.Sentinel, installed)
        audit_main.assert_called_once_with()
        event = json.loads(stdout.strip())
        self.assertEqual({"event": "reporter-provisioning", "state": "disabled", "tokenPresent": False, "maxPerCycle": None}, event)

    def test_token_without_switch_stays_disabled(self):
        result, installed, _, stdout, _ = self.run_main(
            **{runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token"}
        )
        self.assertEqual(0, result)
        self.assertIs(self.Sentinel, installed)
        event = json.loads(stdout.strip())
        self.assertEqual("disabled", event["state"])
        self.assertTrue(event["tokenPresent"])
        self.assertNotIn("provision-token", stdout)

    def test_switch_and_token_install_the_provisioning_client(self):
        result, installed, audit_main, stdout, _ = self.run_main(
            **{
                runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token",
                runner.REPORTER_PROVISIONING_ENABLED_ENV: "true",
            }
        )
        self.assertEqual(0, result)
        self.assertIs(runner.ProvisioningYouTrackClient, installed)
        audit_main.assert_called_once_with()
        event = json.loads(stdout.strip())
        self.assertEqual("enabled", event["state"])
        self.assertEqual(1, event["maxPerCycle"])
        self.assertIsNot(audit.YouTrackClient, self.Sentinel)  # patch restored

    def test_switch_without_token_aborts_before_the_run_loop(self):
        result, installed, audit_main, _, stderr = self.run_main(
            **{runner.REPORTER_PROVISIONING_ENABLED_ENV: "true", "AUDIT_INTERVAL_SECONDS": "86400"}
        )
        self.assertEqual(runner.STARTUP_ABORT_EXIT_CODE, result)
        audit_main.assert_not_called()
        event = json.loads(stderr.strip())
        self.assertEqual("startup-aborted", event["event"])
        self.assertIn(runner.REPORTER_PROVISION_TOKEN_ENV, event["detail"])

    def test_switch_with_reused_sync_token_aborts(self):
        result, _, audit_main, _, stderr = self.run_main(
            **{
                runner.REPORTER_PROVISIONING_ENABLED_ENV: "true",
                runner.REPORTER_PROVISION_TOKEN_ENV: "same-token",
                "YOUTRACK_TOKEN": "same-token",
            }
        )
        self.assertEqual(runner.STARTUP_ABORT_EXIT_CODE, result)
        audit_main.assert_not_called()
        self.assertIn("separate least-privilege", stderr)
        self.assertNotIn("same-token", stderr)

    def test_legacy_hub_url_aborts_even_when_disabled(self):
        result, _, audit_main, _, stderr = self.run_main(
            **{runner.LEGACY_HUB_URL_ENV: "https://youtrack.example.invalid/hub/api/rest"}
        )
        self.assertEqual(runner.STARTUP_ABORT_EXIT_CODE, result)
        audit_main.assert_not_called()
        self.assertIn("Hub provisioning path was removed", stderr)

    def test_invalid_max_per_cycle_aborts_when_enabled(self):
        result, _, audit_main, _, stderr = self.run_main(
            **{
                runner.REPORTER_PROVISIONING_ENABLED_ENV: "true",
                runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token",
                runner.REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV: "0",
            }
        )
        self.assertEqual(runner.STARTUP_ABORT_EXIT_CODE, result)
        audit_main.assert_not_called()
        self.assertIn(runner.REPORTER_PROVISIONING_MAX_PER_CYCLE_ENV, stderr)

    def test_invalid_switch_value_aborts(self):
        result, _, audit_main, _, _ = self.run_main(
            **{runner.REPORTER_PROVISIONING_ENABLED_ENV: "maybe"}
        )
        self.assertEqual(runner.STARTUP_ABORT_EXIT_CODE, result)
        audit_main.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class FullCycleProvisioningTests(ResetTrip):
    """audit.run_once with the real ProvisioningYouTrackClient over a scripted HTTP stub."""

    SYNC_URL = (
        "https://youtrack.example.invalid/api/admin/projects/CMA/"
        "extensionEndpoints/cma-account-audit/account-sync/sync-account"
    )

    def receipt(self, body, **overrides):
        receipt = {
            "notificationPolicyVersion": audit.NOTIFICATION_POLICY_VERSION,
            "notificationMode": body["notificationMode"],
            "cycleId": body["cycleId"],
            "plexUserId": body["plexUserId"],
            "memberNotificationPermitRequired": True,
            "memberNotificationPermitReserved": False,
            "memberNotificationBudgetRemaining": 1,
            "onboardingRequested": True,
            "onboardingCompleted": False,
            "plannedAction": audit.ONBOARDING_TICKET_CREATED_ACTION,
            "result": "deferred",
            "action": audit.NOTIFICATION_DEFERRED_ACTION,
        }
        receipt.update(overrides)
        return receipt

    def run_cycle(self, registry_path, *, provisioning_env_on=True):
        test = self
        directory_users = [
            {"id": "2-1", "login": "admin", "fullName": "Admin", "email": "admin@example.invalid",
             "banned": False, "userType": {"id": "STANDARD_USER"}},
        ]
        log = []

        class ScriptedHttp:
            def __init__(self, _timeout):
                pass

            def request(self, url, *, method="GET", headers=None, body=None):
                path = url.split("?", 1)[0]
                log.append((method, path))
                if url == test.SYNC_URL:
                    test.assertEqual({"Authorization": "Bearer sync-token"}, headers)
                    matched = [u for u in directory_users
                               if (u.get("email") or "").casefold() == (body["email"] or "").casefold()]
                    if len(matched) != 1:
                        raise missing_reporter()
                    if body["notificationMode"] == audit.NOTIFICATION_MODE_SUPPRESS:
                        return test.receipt(body)
                    return test.receipt(
                        body,
                        memberNotificationPermitReserved=True,
                        memberNotificationBudgetRemaining=0,
                        onboardingCompleted=True,
                        result="created",
                        action=audit.ONBOARDING_TICKET_CREATED_ACTION,
                    )
                test.assertEqual({"Authorization": "Bearer provision-token"}, headers)
                if path == f"{API}/users" and method == "GET":
                    return list(directory_users)
                if path == f"{API}/users" and method == "POST":
                    created = {
                        "id": "2-50", "login": body["login"], "fullName": body["fullName"],
                        "email": body["email"], "banned": False, "userType": dict(body["userType"]),
                    }
                    directory_users.append(created)
                    return created
                if path == f"{API}/users/2-50":
                    return directory_users[-1]
                raise AssertionError(f"unexpected request {method} {url}")

        class StubTautulli:
            def __init__(self, _config, _http):
                pass

            def accounts(self):
                return [member()]

            def home_user_map(self):
                return {member().user_id: False}

        def protocol_stub(self):
            return {
                "appName": audit.NOTIFICATION_PROTOCOL_ID,
                "notificationPolicyVersion": audit.NOTIFICATION_POLICY_VERSION,
                "notificationModes": list(audit.NOTIFICATION_PROTOCOL_MODES),
                "memberNotificationLimit": 1,
                "memberNotificationWindowSeconds": int(audit.MEMBER_NOTIFICATION_WINDOW.total_seconds()),
                "onboardingProtocolVersion": audit.ONBOARDING_PROTOCOL_VERSION,
            }

        env = provisioning_env() if provisioning_env_on else mock.patch.dict(
            os.environ, {runner.REPORTER_PROVISION_TOKEN_ENV: "provision-token",
                         runner.REPORTER_PROVISIONING_ENABLED_ENV: "false"}, clear=False)
        stdout, stderr = io.StringIO(), io.StringIO()
        with env, mock.patch.object(audit, "JsonHttpClient", ScriptedHttp), mock.patch.object(
            audit, "TautulliClient", StubTautulli
        ), mock.patch.object(audit.YouTrackClient, "protocol", protocol_stub), mock.patch.object(
            audit, "YouTrackClient", runner.ProvisioningYouTrackClient
        ), mock.patch.object(audit, "utc_now", return_value=NOW), redirect_stdout(stdout), redirect_stderr(stderr):
            cfg = audit.Config(
                tautulli_url="https://tautulli.example.invalid",
                tautulli_api_key="tautulli-token",
                youtrack_sync_url=self.SYNC_URL,
                youtrack_token="sync-token",
                registry_path=Path(registry_path),
                dry_run=False,
            )
            exit_code = audit.run_once(cfg, observed_at=NOW)
        return exit_code, log, directory_users, stdout.getvalue(), stderr.getvalue()

    def pending_registry(self, path):
        from datetime import timedelta

        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "users": {
                        "1": {
                            "firstSeenAt": (NOW - timedelta(days=30)).isoformat(),
                            "lastSeenAt": NOW.isoformat(),
                            "username": "existing",
                            "onboardingState": "baseline",
                        }
                    },
                    "memberNotificationPermitHistory": {},
                    "onboardingBaselineCompletedAt": (NOW - timedelta(days=1)).isoformat(),
                }
            ),
            encoding="utf-8",
        )

    def test_new_member_without_reporter_is_provisioned_then_welcomed_in_one_cycle(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            self.pending_registry(path)
            exit_code, log, users, stdout, stderr = self.run_cycle(path)

            self.assertEqual(0, exit_code, stderr)
            self.assertEqual(
                [
                    ("POST", self.SYNC_URL),          # suppress -> 422 missing reporter
                    ("GET", f"{API}/users"),          # exact-email lookup
                    ("POST", f"{API}/users"),         # create REPORTER
                    ("GET", f"{API}/users/2-50"),     # readback
                    ("POST", self.SYNC_URL),          # suppress retry -> deferred plan
                    ("POST", self.SYNC_URL),          # permit -> welcome ticket created
                ],
                log,
            )
            created = users[-1]
            self.assertEqual({"id": "REPORTER"}, created["userType"])
            self.assertEqual(login(), created["login"])
            self.assertIn('"event": "reporter-provisioned"', stdout)
            self.assertIn('"notificationPermitStatus": "confirmed"', stdout)
            self.assertIn('"errors": 0', stdout)
            self.assertNotIn(EMAIL, stdout)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("completed", saved["users"][member().user_id]["onboardingState"])

    def test_switch_off_leaves_the_member_skipped_and_creates_nothing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            self.pending_registry(path)
            exit_code, log, users, stdout, stderr = self.run_cycle(path, provisioning_env_on=False)

            self.assertEqual(0, exit_code, stderr)
            self.assertEqual([("POST", self.SYNC_URL)], log)
            self.assertEqual(1, len(users))
            self.assertIn('"youtrackSuppressSkipped": "reporter-match-unavailable"', stdout)
            self.assertIn('"notificationPermitStatus": "not-needed"', stdout)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("pending", saved["users"][member().user_id]["onboardingState"])
