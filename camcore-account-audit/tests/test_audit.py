import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "audit.py"
SPEC = importlib.util.spec_from_file_location("cma_audit", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


UTC = timezone.utc
NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def account(
    *,
    plays=1,
    last_streamed=None,
    username="member",
    user_id="42",
    email="member@example.invalid",
):
    return audit.Account(
        user_id=user_id,
        username=username,
        email=email,
        last_streamed=last_streamed,
        total_plays=plays,
        watch_seconds=3600,
    )


def config(registry_path, *, dry_run=False):
    return audit.Config(
        tautulli_url="https://tautulli.example.invalid",
        tautulli_api_key="test",
        youtrack_sync_url=(
            "https://youtrack.example.invalid/api/admin/projects/CMA/"
            "extensionEndpoints/cma-account-audit/account-sync/sync-account"
        ),
        youtrack_token="test",
        registry_path=Path(registry_path),
        dry_run=dry_run,
    )


def sync_receipt(
    *,
    notification_mode,
    cycle_id,
    plex_user_id,
    planned_action="facts-only",
    permit_required=False,
    permit_reserved=False,
    budget_remaining=1,
    result=None,
    action=None,
    onboarding_requested=False,
    onboarding_completed=False,
):
    if result is None:
        result = "updated"
    if action is None:
        action = planned_action
    return {
        "notificationPolicyVersion": audit.NOTIFICATION_POLICY_VERSION,
        "notificationMode": notification_mode,
        "cycleId": cycle_id,
        "plexUserId": plex_user_id,
        "memberNotificationPermitRequired": permit_required,
        "memberNotificationPermitReserved": permit_reserved,
        "memberNotificationBudgetRemaining": budget_remaining,
        "onboardingRequested": onboarding_requested,
        "onboardingCompleted": onboarding_completed,
        "plannedAction": planned_action,
        "result": result,
        "action": action,
    }


def deferred_receipt(
    *,
    cycle_id,
    plex_user_id,
    planned_action,
    onboarding_requested=False,
):
    return sync_receipt(
        notification_mode=audit.NOTIFICATION_MODE_SUPPRESS,
        cycle_id=cycle_id,
        plex_user_id=plex_user_id,
        planned_action=planned_action,
        permit_required=True,
        result="deferred",
        action=audit.NOTIFICATION_DEFERRED_ACTION,
        onboarding_requested=onboarding_requested,
    )


def protocol_receipt(**overrides):
    receipt = {
        "appName": audit.NOTIFICATION_PROTOCOL_ID,
        "notificationPolicyVersion": audit.NOTIFICATION_POLICY_VERSION,
        "notificationModes": list(audit.NOTIFICATION_PROTOCOL_MODES),
        "memberNotificationLimit": 1,
        "memberNotificationWindowSeconds": int(
            audit.MEMBER_NOTIFICATION_WINDOW.total_seconds()
        ),
        "onboardingProtocolVersion": audit.ONBOARDING_PROTOCOL_VERSION,
    }
    receipt.update(overrides)
    return receipt


class JsonHttpClientTests(unittest.TestCase):
    @staticmethod
    def response(payload):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload).encode("utf-8")
        return response

    def test_retries_one_transient_get_transport_failure(self):
        client = audit.JsonHttpClient(timeout_seconds=5)
        response = self.response({"response": {"result": "success"}})
        with mock.patch.object(
            audit.urllib.request,
            "urlopen",
            side_effect=[ConnectionResetError("connection reset"), response],
        ) as urlopen, mock.patch.object(audit.time, "sleep") as sleep:
            result = client.request("http://127.0.0.1:8181/api/v2")

        self.assertEqual({"response": {"result": "success"}}, result)
        self.assertEqual(2, urlopen.call_count)
        sleep.assert_called_once_with(audit.TRANSIENT_GET_RETRY_DELAY_SECONDS)

    def test_does_not_retry_post_transport_failures(self):
        client = audit.JsonHttpClient(timeout_seconds=5)
        with mock.patch.object(
            audit.urllib.request,
            "urlopen",
            side_effect=ConnectionResetError("connection reset"),
        ) as urlopen, mock.patch.object(audit.time, "sleep") as sleep:
            with self.assertRaises(audit.RemoteApiError):
                client.request(
                    "https://youtrack.example.invalid/sync",
                    method="POST",
                    body={"mode": "permit"},
                )

        self.assertEqual(1, urlopen.call_count)
        sleep.assert_not_called()

    def test_retries_get_transport_failures_only_once(self):
        client = audit.JsonHttpClient(timeout_seconds=5)
        with mock.patch.object(
            audit.urllib.request,
            "urlopen",
            side_effect=[
                ConnectionResetError("first reset"),
                ConnectionResetError("second reset"),
            ],
        ) as urlopen, mock.patch.object(audit.time, "sleep") as sleep:
            with self.assertRaisesRegex(audit.RemoteApiError, "second reset"):
                client.request("http://127.0.0.1:8181/api/v2")

        self.assertEqual(2, urlopen.call_count)
        sleep.assert_called_once_with(audit.TRANSIENT_GET_RETRY_DELAY_SECONDS)

    def test_normalizes_low_level_timeout_without_exposing_query_parameters(self):
        client = audit.JsonHttpClient(timeout_seconds=5)
        with mock.patch.object(
            audit.urllib.request,
            "urlopen",
            side_effect=TimeoutError("socket timed out"),
        ):
            with self.assertRaisesRegex(
                audit.RemoteApiError,
                r"GET https://youtrack\.example\.invalid/protocol failed: socket timed out",
            ) as raised:
                client.request(
                    "https://youtrack.example.invalid/protocol?token=secret"
                )

        self.assertNotIn("token", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))

    def test_normalizes_low_level_http_transport_failures(self):
        client = audit.JsonHttpClient(timeout_seconds=5)
        with mock.patch.object(
            audit.urllib.request,
            "urlopen",
            side_effect=audit.http.client.IncompleteRead(b"partial"),
        ):
            with self.assertRaisesRegex(
                audit.RemoteApiError,
                r"GET https://youtrack\.example\.invalid/protocol failed:",
            ):
                client.request("https://youtrack.example.invalid/protocol")


class YouTrackClientTests(unittest.TestCase):
    class RecordingHttp:
        def __init__(self, failures):
            self.failures = list(failures)
            self.calls = []

        def request(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if self.failures:
                raise self.failures.pop(0)
            return {"result": "deferred"}

    @staticmethod
    def conflict():
        return audit.RemoteHttpError(
            'POST sync-account returned HTTP 400: {"error":"Invalid properties"}',
            status_code=400,
            detail='{"error":"Invalid properties"}',
        )

    def sync(self, http, notification_mode):
        return audit.YouTrackClient(config(Path("registry.json")), http).sync(
            account(last_streamed=NOW - timedelta(days=60)),
            audit.Decision("Inactive", True, "inactive"),
            onboarding_requested=False,
            notification_mode=notification_mode,
            cycle_id="audit-00000000000000000000000000000001",
        )

    def test_permit_retries_one_structured_youtrack_transaction_conflict(self):
        http = self.RecordingHttp([self.conflict()])

        with mock.patch.object(audit.time, "sleep") as sleep:
            self.assertEqual(
                {"result": "deferred"},
                self.sync(http, audit.NOTIFICATION_MODE_PERMIT),
            )
        self.assertEqual(2, len(http.calls))
        self.assertEqual(http.calls[0], http.calls[1])
        sleep.assert_called_once_with(
            audit.PERMIT_CONFLICT_RETRY_DELAYS_SECONDS[0]
        )

    def test_suppress_never_retries_a_transaction_conflict(self):
        http = self.RecordingHttp([self.conflict()])

        with mock.patch.object(audit.time, "sleep") as sleep:
            with self.assertRaises(audit.RemoteHttpError):
                self.sync(http, audit.NOTIFICATION_MODE_SUPPRESS)
        self.assertEqual(1, len(http.calls))
        sleep.assert_not_called()

    def test_permit_does_not_retry_other_http_400_responses(self):
        error = audit.RemoteHttpError(
            'POST sync-account returned HTTP 400: {"error":"Bad Request"}',
            status_code=400,
            detail='{"error":"Bad Request"}',
        )
        http = self.RecordingHttp([error])

        with mock.patch.object(audit.time, "sleep") as sleep:
            with self.assertRaises(audit.RemoteHttpError):
                self.sync(http, audit.NOTIFICATION_MODE_PERMIT)
        self.assertEqual(1, len(http.calls))
        sleep.assert_not_called()

    def test_permit_retries_transaction_conflicts_with_bounded_backoff(self):
        http = self.RecordingHttp(
            [self.conflict(), self.conflict(), self.conflict()]
        )

        with mock.patch.object(audit.time, "sleep") as sleep:
            self.assertEqual(
                {"result": "deferred"},
                self.sync(http, audit.NOTIFICATION_MODE_PERMIT),
            )
        self.assertEqual(4, len(http.calls))
        self.assertTrue(all(call == http.calls[0] for call in http.calls))
        self.assertEqual(
            [mock.call(delay) for delay in audit.PERMIT_CONFLICT_RETRY_DELAYS_SECONDS],
            sleep.call_args_list,
        )

    def test_permit_conflict_retry_budget_remains_fail_closed(self):
        http = self.RecordingHttp(
            [
                self.conflict()
                for _ in range(len(audit.PERMIT_CONFLICT_RETRY_DELAYS_SECONDS) + 1)
            ]
        )

        with mock.patch.object(audit.time, "sleep") as sleep:
            with self.assertRaises(audit.RemoteHttpError):
                self.sync(http, audit.NOTIFICATION_MODE_PERMIT)
        self.assertEqual(
            len(audit.PERMIT_CONFLICT_RETRY_DELAYS_SECONDS) + 1,
            len(http.calls),
        )
        self.assertEqual(
            [mock.call(delay) for delay in audit.PERMIT_CONFLICT_RETRY_DELAYS_SECONDS],
            sleep.call_args_list,
        )


class ClassificationTests(unittest.TestCase):
    def test_active_inside_sixty_day_window(self):
        result = audit.classify_account(
            account(last_streamed=NOW - timedelta(days=59)),
            first_seen=NOW - timedelta(days=200),
            observed_at=NOW,
            inactive_days=60,
            never_used_days=14,
        )

        self.assertEqual("Active", result.account_status)
        self.assertFalse(result.review_needed)

    def test_inactive_on_sixtieth_day(self):
        result = audit.classify_account(
            account(last_streamed=NOW - timedelta(days=60)),
            first_seen=NOW - timedelta(days=200),
            observed_at=NOW,
            inactive_days=60,
            never_used_days=14,
        )

        self.assertEqual("Inactive", result.account_status)
        self.assertTrue(result.review_needed)

    def test_never_used_waits_for_observation_period(self):
        result = audit.classify_account(
            account(plays=0),
            first_seen=NOW - timedelta(days=13),
            observed_at=NOW,
            inactive_days=60,
            never_used_days=14,
        )

        self.assertEqual("Never Used", result.account_status)
        self.assertFalse(result.review_needed)

    def test_never_used_becomes_reviewable_on_fourteenth_day(self):
        result = audit.classify_account(
            account(plays=0),
            first_seen=NOW - timedelta(days=14),
            observed_at=NOW,
            inactive_days=60,
            never_used_days=14,
        )

        self.assertEqual("Never Used", result.account_status)
        self.assertTrue(result.review_needed)

    def test_missing_last_stream_with_plays_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "require a last-streamed"):
            audit.classify_account(
                account(plays=3, last_streamed=None),
                first_seen=NOW - timedelta(days=200),
                observed_at=NOW,
                inactive_days=60,
                never_used_days=14,
            )

    def test_future_last_stream_is_rejected_beyond_clock_skew(self):
        with self.assertRaisesRegex(ValueError, "future"):
            audit.classify_account(
                account(last_streamed=NOW + timedelta(minutes=5, milliseconds=1)),
                first_seen=NOW - timedelta(days=200),
                observed_at=NOW,
                inactive_days=60,
                never_used_days=14,
            )


class MappingTests(unittest.TestCase):
    def test_maps_tautulli_row(self):
        result = audit.account_from_row(
            {
                "user_id": 99,
                "username": "Example",
                "email": "example@example.invalid",
                "last_seen": 1_787_569_200,
                "plays": "12",
                "duration": "7260",
            }
        )

        self.assertEqual("99", result.user_id)
        self.assertEqual(12, result.total_plays)
        self.assertEqual(7260, result.watch_seconds)
        self.assertEqual("2 hrs 1 mins", audit.format_watch_time(result.watch_seconds))

    def test_missing_or_malformed_play_count_fails_closed(self):
        base = {
            "user_id": 99,
            "username": "Example",
            "last_seen": 0,
            "duration": 0,
        }
        for unsafe in (None, "", "not-a-number", -1, True, 0.5):
            with self.subTest(plays=unsafe):
                row = dict(base, plays=unsafe)
                with self.assertRaisesRegex(ValueError, "plays"):
                    audit.account_from_row(row)

    def test_explicit_zero_play_count_remains_valid(self):
        result = audit.account_from_row(
            {
                "user_id": 99,
                "username": "Example",
                "last_seen": 0,
                "plays": 0,
                "duration": 0,
            }
        )

        self.assertEqual(0, result.total_plays)
        self.assertIsNone(result.last_streamed)

    def test_plays_require_a_valid_last_seen_timestamp(self):
        base = {
            "user_id": 99,
            "username": "Example",
            "plays": 1,
            "duration": 0,
        }
        for unsafe in (None, "", 0, "0", "not-a-number", -1, True, 0.5):
            with self.subTest(last_seen=unsafe):
                row = dict(base, last_seen=unsafe)
                with self.assertRaisesRegex(ValueError, "last_seen"):
                    audit.account_from_row(row, observed_at=NOW)

    def test_zero_plays_rejects_a_positive_last_seen_timestamp(self):
        with self.assertRaisesRegex(ValueError, "conflicts with zero plays"):
            audit.account_from_row(
                {
                    "user_id": 99,
                    "username": "Example",
                    "last_seen": int(NOW.timestamp()),
                    "plays": 0,
                    "duration": 0,
                },
                observed_at=NOW,
            )

    def test_future_timestamp_uses_five_minute_clock_skew(self):
        accepted = audit.account_from_row(
            {
                "user_id": 99,
                "username": "Example",
                "last_seen": int((NOW + timedelta(minutes=5)).timestamp()),
                "plays": 1,
                "duration": 0,
            },
            observed_at=NOW,
        )
        self.assertEqual(NOW + timedelta(minutes=5), accepted.last_streamed)

        with self.assertRaisesRegex(ValueError, "future"):
            audit.account_from_row(
                {
                    "user_id": 99,
                    "username": "Example",
                    "last_seen": int((NOW + timedelta(minutes=5, seconds=1)).timestamp()),
                    "plays": 1,
                    "duration": 0,
                },
                observed_at=NOW,
            )

    def test_js_unsafe_integer_telemetry_is_rejected(self):
        for field in ("plays", "last_seen", "duration"):
            with self.subTest(field=field):
                row = {
                    "user_id": 99,
                    "username": "Example",
                    "last_seen": int(NOW.timestamp()),
                    "plays": 1,
                    "duration": 0,
                }
                row[field] = audit.JS_MAX_SAFE_INTEGER + 1
                with self.assertRaisesRegex(ValueError, field):
                    audit.account_from_row(row, observed_at=NOW)

    def test_client_rejects_the_whole_batch_when_any_account_is_unsafe(self):
        class StubHttp:
            def request(self, _url):
                return {
                    "response": {
                        "result": "success",
                        "data": {
                            "data": [
                                {
                                    "user_id": 98,
                                    "username": "Safe Before Unsafe",
                                    "last_seen": 1_700_000_000,
                                    "plays": 4,
                                    "duration": 0,
                                },
                                {
                                    "user_id": 99,
                                    "username": "Example",
                                    "last_seen": 0,
                                    "plays": 2,
                                    "duration": 0,
                                }
                            ]
                        },
                    }
                }

        config = audit.Config(
            tautulli_url="https://tautulli.example.invalid",
            tautulli_api_key="test",
            youtrack_sync_url="",
            youtrack_token="",
            registry_path=Path("registry.json"),
        )
        client = audit.TautulliClient(config, StubHttp())

        with self.assertRaisesRegex(audit.RemoteApiError, "unsafe account telemetry"):
            client.accounts()

    def test_guest_and_local_defaults_are_case_insensitive(self):
        config = audit.Config(
            tautulli_url="https://tautulli.example.invalid",
            tautulli_api_key="test",
            youtrack_sync_url="",
            youtrack_token="",
            registry_path=Path("registry.json"),
        )

        self.assertIn("guest", config.excluded_users)
        self.assertIn("local", config.excluded_users)

    def test_public_log_shape_does_not_include_email_address(self):
        result = audit.public_account(account())

        self.assertEqual("present", result["email"])
        self.assertNotIn("example.invalid", str(result))


class RegistryTests(unittest.TestCase):
    def test_preserves_first_observation_when_account_is_seen_again(self):
        registry = audit.Registry(Path("registry.json"))
        first = registry.first_seen(account(), NOW - timedelta(days=20))
        second = registry.first_seen(account(), NOW)

        self.assertEqual(first, second)

    def test_v1_registry_adds_and_preserves_backward_compatible_safety_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            original = {
                "schemaVersion": 1,
                "users": {
                    "42": {
                        "firstSeenAt": (NOW - timedelta(days=20)).isoformat(),
                        "lastSeenAt": NOW.isoformat(),
                        "username": "member",
                    }
                },
                "lastCompletedAt": (NOW - timedelta(days=1)).isoformat(),
                "rollbackSentinel": {"preserve": True},
            }
            path.write_text(json.dumps(original), encoding="utf-8")

            registry = audit.Registry(path)
            registry.load()

            self.assertEqual(1, registry.data["schemaVersion"])
            self.assertEqual(original["users"], registry.data["users"])
            self.assertEqual(
                original["lastCompletedAt"], registry.data["lastCompletedAt"]
            )
            self.assertEqual(
                original["rollbackSentinel"], registry.data["rollbackSentinel"]
            )
            self.assertEqual({}, registry.data["memberNotificationPermitHistory"])

            registry.reserve_notification_permit(
                cycle_id="audit-" + "a" * 32,
                account=account(),
                observed_at=NOW,
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(1, saved["schemaVersion"])
            self.assertEqual(
                original["rollbackSentinel"], saved["rollbackSentinel"]
            )
            self.assertIn("memberNotificationGate", saved)
            self.assertIn("42", saved["memberNotificationPermitHistory"])

    def test_onboarding_baseline_never_backfills_existing_members(self):
        registry = audit.Registry(Path("registry.json"))
        existing = account(user_id="42", username="existing")

        _, requested = registry.observe_account(existing, NOW)
        self.assertFalse(requested)
        registry.complete_onboarding_baseline(NOW, inventory_count=1)

        _, requested = registry.observe_account(existing, NOW + timedelta(minutes=5))
        self.assertFalse(requested)
        newcomer = account(user_id="43", username="newcomer")
        _, requested = registry.observe_account(newcomer, NOW + timedelta(minutes=5))
        self.assertTrue(requested)
        self.assertEqual(
            "pending", registry.data["users"]["43"]["onboardingState"]
        )

        registry.confirm_onboarding(newcomer)
        self.assertEqual(
            "completed", registry.data["users"]["43"]["onboardingState"]
        )

    def test_onboarding_baseline_refuses_an_empty_inventory(self):
        registry = audit.Registry(Path("registry.json"))
        with self.assertRaisesRegex(audit.ConfigurationError, "empty.*baseline"):
            registry.complete_onboarding_baseline(NOW, inventory_count=0)

    def test_notification_permit_is_reserved_for_a_full_twenty_four_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            registry = audit.Registry(path)
            target = account()
            registry.reserve_notification_permit(
                cycle_id="audit-" + "a" * 32,
                account=target,
                observed_at=NOW,
            )

            self.assertFalse(
                registry.notification_permit_available(
                    NOW + timedelta(hours=23, minutes=59, seconds=59)
                )
            )
            self.assertTrue(
                registry.notification_permit_available(NOW + timedelta(hours=24))
            )
            self.assertEqual(
                NOW,
                registry.last_notification_permit_at(target, NOW),
            )

            reloaded = audit.Registry(path)
            reloaded.load()
            self.assertFalse(
                reloaded.notification_permit_available(NOW + timedelta(hours=1))
            )

    def test_invalid_notification_state_fails_closed_on_load(self):
        invalid_gates = [
            "not-an-object",
            {
                "policyVersion": True,
                "cycleId": "audit-" + "a" * 32,
                "plexUserId": "42",
                "reservedAt": NOW.isoformat(),
                "status": "reserved",
            },
            {
                "policyVersion": 1.0,
                "cycleId": "audit-" + "a" * 32,
                "plexUserId": "42",
                "reservedAt": NOW.isoformat(),
                "status": "reserved",
            },
            {
                "policyVersion": 1,
                "cycleId": "",
                "plexUserId": "42",
                "reservedAt": NOW.isoformat(),
                "status": "reserved",
            },
            {
                "policyVersion": 1,
                "cycleId": "audit-" + "a" * 32,
                "plexUserId": "42",
                "reservedAt": NOW.replace(tzinfo=None).isoformat(),
                "status": "reserved",
            },
            {
                "policyVersion": 1,
                "cycleId": "audit-" + "a" * 32,
                "plexUserId": "42",
                "reservedAt": NOW.isoformat(),
                "status": "unknown",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, gate in enumerate(invalid_gates):
                with self.subTest(index=index):
                    path = Path(directory) / f"registry-{index}.json"
                    path.write_text(
                        json.dumps(
                            {
                                "schemaVersion": 1,
                                "users": {},
                                "memberNotificationPermitHistory": {},
                                "memberNotificationGate": gate,
                            }
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaises(audit.ConfigurationError):
                        audit.Registry(path).load()

    def test_non_v1_schema_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            for schema_version in [2, True, "1", None]:
                with self.subTest(schema_version=schema_version):
                    path.write_text(
                        json.dumps({"schemaVersion": schema_version, "users": {}}),
                        encoding="utf-8",
                    )
                    with self.assertRaises(audit.ConfigurationError):
                        audit.Registry(path).load()


class RegistryLockTests(unittest.TestCase):
    def test_registry_lock_is_exclusive_across_processes_and_releases(self):
        child_source = "\n".join(
            [
                "import importlib.util",
                "import sys",
                "import time",
                "from pathlib import Path",
                "module_path, registry_raw, ready_raw, release_raw = sys.argv[1:]",
                "spec = importlib.util.spec_from_file_location('child_cma_audit', module_path)",
                "module = importlib.util.module_from_spec(spec)",
                "sys.modules[spec.name] = module",
                "spec.loader.exec_module(module)",
                "registry_path = Path(registry_raw)",
                "ready_path = Path(ready_raw)",
                "release_path = Path(release_raw)",
                "with module.RegistryLock(registry_path):",
                "    ready_path.write_text('locked', encoding='utf-8')",
                "    deadline = time.monotonic() + 10",
                "    while not release_path.exists():",
                "        if time.monotonic() >= deadline:",
                "            raise RuntimeError('parent did not release child lock')",
                "        time.sleep(0.01)",
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "registry.json"
            ready_path = root / "ready"
            release_path = root / "release"
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    child_source,
                    str(MODULE_PATH),
                    str(registry_path),
                    str(ready_path),
                    str(release_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 5
                while not ready_path.exists() and process.poll() is None:
                    if time.monotonic() >= deadline:
                        self.fail("child did not acquire the registry lock")
                    time.sleep(0.01)
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    self.fail(
                        f"child failed before holding the lock: {stdout} {stderr}"
                    )

                with self.assertRaisesRegex(
                    audit.ConfigurationError, "exclusive registry lock"
                ):
                    with audit.RegistryLock(registry_path):
                        self.fail("a second process acquired the registry lock")

                release_path.write_text("release", encoding="utf-8")
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(0, process.returncode, stdout + stderr)
                with audit.RegistryLock(registry_path):
                    pass
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)


class SyncReceiptTests(unittest.TestCase):
    CYCLE_ID = "audit-" + "a" * 32

    def validate(self, response, mode, *, onboarding_requested=False):
        return audit.validate_sync_response(
            response,
            notification_mode=mode,
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            onboarding_requested=onboarding_requested,
        )

    def test_accepts_exact_suppress_and_permit_receipts(self):
        safe = sync_receipt(
            notification_mode=audit.NOTIFICATION_MODE_SUPPRESS,
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            result="planned",
        )
        self.assertIs(safe, self.validate(safe, audit.NOTIFICATION_MODE_SUPPRESS))

        deferred = deferred_receipt(
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            planned_action="notice-started",
        )
        self.assertIs(
            deferred,
            self.validate(deferred, audit.NOTIFICATION_MODE_SUPPRESS),
        )

        permitted = sync_receipt(
            notification_mode=audit.NOTIFICATION_MODE_PERMIT,
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            planned_action="notice-started",
            permit_required=True,
            permit_reserved=True,
            budget_remaining=0,
        )
        self.assertIs(
            permitted,
            self.validate(permitted, audit.NOTIFICATION_MODE_PERMIT),
        )

    def test_accepts_staged_ticket_creation_and_ranks_existing_notice_first(self):
        planned_action = audit.TICKET_CREATED_AWAITING_NOTICE_ACTION
        deferred = deferred_receipt(
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            planned_action=planned_action,
        )
        self.assertIs(
            deferred,
            self.validate(deferred, audit.NOTIFICATION_MODE_SUPPRESS),
        )

        created = sync_receipt(
            notification_mode=audit.NOTIFICATION_MODE_PERMIT,
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            planned_action=planned_action,
            permit_required=True,
            permit_reserved=True,
            budget_remaining=0,
            result="created",
        )
        self.assertIs(
            created,
            self.validate(created, audit.NOTIFICATION_MODE_PERMIT),
        )
        self.assertLess(
            audit.candidate_priority({"plannedAction": "notice-started"}),
            audit.candidate_priority({"plannedAction": planned_action}),
        )

    def test_rejects_missing_mismatched_and_contradictory_receipts(self):
        valid = sync_receipt(
            notification_mode=audit.NOTIFICATION_MODE_SUPPRESS,
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            result="planned",
        )
        corruptions = [
            lambda value: value.pop("notificationPolicyVersion"),
            lambda value: value.__setitem__("notificationPolicyVersion", True),
            lambda value: value.__setitem__("notificationPolicyVersion", 1.0),
            lambda value: value.__setitem__("notificationMode", "permit"),
            lambda value: value.__setitem__("cycleId", "audit-" + "b" * 32),
            lambda value: value.__setitem__("plexUserId", "other"),
            lambda value: value.pop("onboardingRequested"),
            lambda value: value.__setitem__("onboardingRequested", True),
            lambda value: value.pop("onboardingCompleted"),
            lambda value: value.__setitem__("onboardingCompleted", "false"),
            lambda value: value.__setitem__(
                "memberNotificationPermitRequired", "true"
            ),
            lambda value: value.__setitem__(
                "memberNotificationPermitReserved", 0
            ),
            lambda value: value.__setitem__(
                "memberNotificationBudgetRemaining", True
            ),
            lambda value: value.__setitem__(
                "memberNotificationBudgetRemaining", 2
            ),
            lambda value: value.__setitem__("plannedAction", "unknown"),
        ]
        for index, corrupt in enumerate(corruptions):
            with self.subTest(index=index):
                response = dict(valid)
                corrupt(response)
                with self.assertRaises(audit.RemoteApiError):
                    self.validate(response, audit.NOTIFICATION_MODE_SUPPRESS)

        contradictory_suppress = deferred_receipt(
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            planned_action="notice-started",
        )
        contradictory_suppress["memberNotificationPermitReserved"] = True
        with self.assertRaises(audit.RemoteApiError):
            self.validate(
                contradictory_suppress,
                audit.NOTIFICATION_MODE_SUPPRESS,
            )

        contradictory_permit = sync_receipt(
            notification_mode=audit.NOTIFICATION_MODE_PERMIT,
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            planned_action="notice-started",
            permit_required=True,
            permit_reserved=True,
            budget_remaining=1,
        )
        with self.assertRaises(audit.RemoteApiError):
            self.validate(contradictory_permit, audit.NOTIFICATION_MODE_PERMIT)

        mutating_suppress_receipt = sync_receipt(
            notification_mode=audit.NOTIFICATION_MODE_SUPPRESS,
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            result="updated",
        )
        with self.assertRaises(audit.RemoteApiError):
            self.validate(
                mutating_suppress_receipt,
                audit.NOTIFICATION_MODE_SUPPRESS,
            )

        unsafe_completion = sync_receipt(
            notification_mode=audit.NOTIFICATION_MODE_SUPPRESS,
            cycle_id=self.CYCLE_ID,
            plex_user_id="42",
            result="planned",
            onboarding_requested=True,
            onboarding_completed=True,
        )
        with self.assertRaises(audit.RemoteApiError):
            self.validate(
                unsafe_completion,
                audit.NOTIFICATION_MODE_SUPPRESS,
                onboarding_requested=True,
            )


class ProtocolReceiptTests(unittest.TestCase):
    def test_accepts_only_the_exact_closed_protocol_receipt(self):
        valid = protocol_receipt()
        self.assertIs(valid, audit.validate_protocol_response(valid))

        corruptions = [
            lambda value: value.pop("notificationPolicyVersion"),
            lambda value: value.__setitem__("unexpected", True),
            lambda value: value.__setitem__("appName", "legacy-account-audit"),
            lambda value: value.__setitem__("notificationPolicyVersion", True),
            lambda value: value.__setitem__("notificationPolicyVersion", 1.0),
            lambda value: value.__setitem__("notificationModes", ["permit", "suppress"]),
            lambda value: value.pop("onboardingProtocolVersion"),
            lambda value: value.__setitem__("onboardingProtocolVersion", True),
            lambda value: value.__setitem__("onboardingProtocolVersion", 2),
            lambda value: value.__setitem__("memberNotificationLimit", True),
            lambda value: value.__setitem__("memberNotificationLimit", 2),
            lambda value: value.__setitem__("memberNotificationWindowSeconds", 1.0),
            lambda value: value.__setitem__("memberNotificationWindowSeconds", 3600),
        ]
        for index, corrupt in enumerate(corruptions):
            with self.subTest(index=index):
                response = protocol_receipt()
                corrupt(response)
                with self.assertRaises(audit.RemoteApiError):
                    audit.validate_protocol_response(response)

    def test_client_uses_the_read_only_sibling_endpoint(self):
        class RecordingHttp:
            def __init__(self):
                self.calls = []

            def request(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return protocol_receipt()

        http = RecordingHttp()
        client = audit.YouTrackClient(config(Path("registry.json")), http)
        response = client.protocol()

        self.assertEqual(protocol_receipt(), response)
        self.assertEqual(1, len(http.calls))
        self.assertEqual(
            "https://youtrack.example.invalid/api/admin/projects/CMA/"
            "extensionEndpoints/cma-account-audit/account-sync/protocol",
            http.calls[0][0],
        )
        self.assertEqual(
            {"Authorization": "Bearer test"},
            http.calls[0][1]["headers"],
        )
        self.assertNotIn("body", http.calls[0][1])
        self.assertNotIn("method", http.calls[0][1])


class RunOnceTests(unittest.TestCase):
    def run_worker(
        self,
        *,
        accounts,
        registry_path,
        responder=None,
        observed_at=NOW,
        clock_at=None,
        dry_run=False,
        protocol_response=None,
    ):
        calls = []
        clock_at = clock_at or observed_at

        class StubTautulliClient:
            def __init__(self, _config, _http):
                pass

            def accounts(self):
                return list(accounts)

        class StubYouTrackClient:
            def __init__(self, _config, _http):
                pass

            def protocol(self):
                if dry_run:
                    raise AssertionError("Dry-run must not call the protocol endpoint")
                if isinstance(protocol_response, BaseException):
                    raise protocol_response
                return protocol_receipt() if protocol_response is None else protocol_response

            def sync(
                self,
                target,
                decision,
                *,
                onboarding_requested,
                notification_mode,
                cycle_id,
            ):
                calls.append(
                    {
                        "account": target,
                        "decision": decision,
                        "onboarding_requested": onboarding_requested,
                        "notification_mode": notification_mode,
                        "cycle_id": cycle_id,
                    }
                )
                if responder is None:
                    raise AssertionError("YouTrack must not be called")
                return responder(target, decision, notification_mode, cycle_id)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(audit, "TautulliClient", StubTautulliClient),
            mock.patch.object(audit, "YouTrackClient", StubYouTrackClient),
            mock.patch.object(audit, "utc_now", return_value=clock_at),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = audit.run_once(
                config(registry_path, dry_run=dry_run),
                observed_at=observed_at,
            )
        return exit_code, calls, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def inactive_account(*, username, user_id):
        return account(
            username=username,
            user_id=user_id,
            last_streamed=NOW - timedelta(days=60),
        )

    def test_dry_run_never_calls_youtrack_or_reserves_a_permit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            exit_code, calls, _, _ = self.run_worker(
                accounts=[self.inactive_account(username="member", user_id="42")],
                registry_path=path,
                dry_run=True,
            )

            self.assertEqual(0, exit_code)
            self.assertEqual([], calls)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(NOW.isoformat(), saved["lastCompletedAt"])
            self.assertEqual(NOW.isoformat(), saved["onboardingBaselineCompletedAt"])
            self.assertEqual("baseline", saved["users"]["42"]["onboardingState"])
            self.assertNotIn("memberNotificationGate", saved)

    def test_new_member_is_onboarded_once_after_the_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "users": {
                            "42": {
                                "firstSeenAt": (NOW - timedelta(days=30)).isoformat(),
                                "lastSeenAt": NOW.isoformat(),
                                "username": "existing",
                                "onboardingState": "baseline",
                            }
                        },
                        "memberNotificationPermitHistory": {},
                        "onboardingBaselineCompletedAt": (
                            NOW - timedelta(days=1)
                        ).isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            newcomer = account(
                user_id="43",
                username="newcomer",
                plays=0,
                last_streamed=None,
            )

            def responder(target, _decision, mode, cycle_id):
                if mode == audit.NOTIFICATION_MODE_SUPPRESS:
                    return deferred_receipt(
                        cycle_id=cycle_id,
                        plex_user_id=target.user_id,
                        planned_action=audit.ONBOARDING_TICKET_CREATED_ACTION,
                        onboarding_requested=True,
                    )
                return sync_receipt(
                    notification_mode=mode,
                    cycle_id=cycle_id,
                    plex_user_id=target.user_id,
                    planned_action=audit.ONBOARDING_TICKET_CREATED_ACTION,
                    permit_required=True,
                    permit_reserved=True,
                    budget_remaining=0,
                    result="created",
                    onboarding_requested=True,
                    onboarding_completed=True,
                )

            exit_code, calls, _, stderr = self.run_worker(
                accounts=[newcomer],
                registry_path=path,
                responder=responder,
            )

            self.assertEqual(0, exit_code, stderr)
            self.assertEqual(2, len(calls))
            self.assertTrue(all(call["onboarding_requested"] for call in calls))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                "completed", saved["users"]["43"]["onboardingState"]
            )

    def test_legacy_or_invalid_protocol_stops_before_account_enumeration(self):
        class MustNotEnumerate:
            def __iter__(self):
                raise AssertionError("Tautulli accounts were enumerated before the handshake")

        unsafe_responses = [
            audit.RemoteApiError("GET protocol returned HTTP 404"),
            {"result": "legacy-account-sync"},
            protocol_receipt(memberNotificationLimit=2),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, unsafe in enumerate(unsafe_responses):
                with self.subTest(index=index):
                    path = Path(directory) / f"registry-{index}.json"
                    original = {
                        "schemaVersion": 1,
                        "users": {},
                        "memberNotificationPermitHistory": {},
                        "lastCompletedAt": (NOW - timedelta(days=1)).isoformat(),
                    }
                    path.write_text(json.dumps(original), encoding="utf-8")
                    with self.assertRaises(audit.RemoteApiError):
                        self.run_worker(
                            accounts=MustNotEnumerate(),
                            registry_path=path,
                            responder=lambda *_args: (_ for _ in ()).throw(
                                AssertionError("sync POST was called before the handshake")
                            ),
                            protocol_response=unsafe,
                        )
                    self.assertEqual(
                        original,
                        json.loads(path.read_text(encoding="utf-8")),
                    )
                    self.assertFalse(
                        path.with_name(path.name + ".lock").exists(),
                        "the registry lock was acquired before protocol validation",
                    )

    def test_held_registry_lock_stops_before_inventory_or_sync(self):
        class MustNotEnumerate:
            def __iter__(self):
                raise AssertionError("Tautulli accounts were enumerated while locked")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            original = {
                "schemaVersion": 1,
                "users": {},
                "memberNotificationPermitHistory": {},
                "lastCompletedAt": (NOW - timedelta(days=1)).isoformat(),
            }
            path.write_text(json.dumps(original), encoding="utf-8")

            with audit.RegistryLock(path):
                with self.assertRaisesRegex(
                    audit.ConfigurationError, "exclusive registry lock"
                ):
                    self.run_worker(
                        accounts=MustNotEnumerate(),
                        registry_path=path,
                        responder=lambda *_args: (_ for _ in ()).throw(
                            AssertionError("sync POST was called while locked")
                        ),
                    )

            self.assertEqual(
                original,
                json.loads(path.read_text(encoding="utf-8")),
            )

    def test_three_candidates_issue_only_one_permit_post(self):
        candidates = [
            self.inactive_account(username="zeta", user_id="3"),
            self.inactive_account(username="alpha", user_id="1"),
            self.inactive_account(username="beta", user_id="2"),
        ]
        planned_actions = {
            "1": "review-already-in-progress",
            "2": "retained",
            "3": "notice-started",
        }

        def responder(target, _decision, mode, cycle_id):
            planned_action = planned_actions[target.user_id]
            if mode == audit.NOTIFICATION_MODE_SUPPRESS:
                return deferred_receipt(
                    cycle_id=cycle_id,
                    plex_user_id=target.user_id,
                    planned_action=planned_action,
                )
            return sync_receipt(
                notification_mode=audit.NOTIFICATION_MODE_PERMIT,
                cycle_id=cycle_id,
                plex_user_id=target.user_id,
                planned_action=planned_action,
                permit_required=True,
                permit_reserved=True,
                budget_remaining=0,
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            exit_code, calls, _, _ = self.run_worker(
                accounts=candidates,
                registry_path=path,
                responder=responder,
            )

            self.assertEqual(0, exit_code)
            self.assertEqual(
                ["suppress", "suppress", "suppress", "permit"],
                [item["notification_mode"] for item in calls],
            )
            permit_calls = [
                item
                for item in calls
                if item["notification_mode"] == audit.NOTIFICATION_MODE_PERMIT
            ]
            self.assertEqual(1, len(permit_calls))
            # A direct Access Retained transition wins over an in-progress pulse.
            self.assertEqual("2", permit_calls[0]["account"].user_id)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("confirmed", saved["memberNotificationGate"]["status"])
            self.assertEqual("2", saved["memberNotificationGate"]["plexUserId"])
            self.assertEqual(NOW.isoformat(), saved["lastCompletedAt"])

    def test_read_only_plan_is_not_selected_over_a_notification_candidate(self):
        accounts = [
            self.inactive_account(username="safe", user_id="1"),
            self.inactive_account(username="candidate", user_id="2"),
        ]

        def responder(target, _decision, mode, cycle_id):
            if mode == audit.NOTIFICATION_MODE_SUPPRESS:
                if target.user_id == "1":
                    return sync_receipt(
                        notification_mode=mode,
                        cycle_id=cycle_id,
                        plex_user_id=target.user_id,
                        planned_action="facts-only",
                        permit_required=False,
                        result="planned",
                    )
                return deferred_receipt(
                    cycle_id=cycle_id,
                    plex_user_id=target.user_id,
                    planned_action="notice-started",
                )
            self.assertEqual("2", target.user_id)
            return sync_receipt(
                notification_mode=mode,
                cycle_id=cycle_id,
                plex_user_id=target.user_id,
                planned_action="notice-started",
                permit_required=True,
                permit_reserved=True,
                budget_remaining=0,
            )

        with tempfile.TemporaryDirectory() as directory:
            exit_code, calls, _, _ = self.run_worker(
                accounts=accounts,
                registry_path=Path(directory) / "registry.json",
                responder=responder,
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(
            ["suppress", "suppress", "permit"],
            [item["notification_mode"] for item in calls],
        )
        self.assertEqual("2", calls[-1]["account"].user_id)

    def test_local_window_starts_at_the_outbound_permit_attempt(self):
        target = self.inactive_account(username="alpha", user_id="1")

        def responder(target, _decision, mode, cycle_id):
            if mode == audit.NOTIFICATION_MODE_SUPPRESS:
                return deferred_receipt(
                    cycle_id=cycle_id,
                    plex_user_id=target.user_id,
                    planned_action="notice-started",
                )
            return sync_receipt(
                notification_mode=audit.NOTIFICATION_MODE_PERMIT,
                cycle_id=cycle_id,
                plex_user_id=target.user_id,
                planned_action="notice-started",
                permit_required=True,
                permit_reserved=True,
                budget_remaining=0,
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            permit_at = NOW + timedelta(hours=2)
            exit_code, _, _, _ = self.run_worker(
                accounts=[target],
                registry_path=path,
                responder=responder,
                observed_at=NOW,
                clock_at=permit_at,
            )
            self.assertEqual(0, exit_code)
            registry = audit.Registry(path)
            registry.load()
            self.assertEqual(
                permit_at.isoformat(),
                registry.data["memberNotificationGate"]["reservedAt"],
            )
            self.assertFalse(
                registry.notification_permit_available(NOW + timedelta(hours=25))
            )
            self.assertTrue(
                registry.notification_permit_available(NOW + timedelta(hours=26))
            )

            second_exit_code, second_calls, _, _ = self.run_worker(
                accounts=[target],
                registry_path=path,
                responder=responder,
                observed_at=NOW + timedelta(hours=24),
                clock_at=permit_at + timedelta(hours=24),
            )
            self.assertEqual(0, second_exit_code)
            self.assertEqual(
                ["suppress", "permit"],
                [item["notification_mode"] for item in second_calls],
            )

    def test_any_suppress_error_blocks_permit_and_last_completed_update(self):
        candidates = [
            self.inactive_account(username="alpha", user_id="1"),
            self.inactive_account(username="beta", user_id="2"),
        ]
        old_completed = (NOW - timedelta(days=1)).isoformat()

        def responder(target, _decision, mode, cycle_id):
            self.assertEqual(audit.NOTIFICATION_MODE_SUPPRESS, mode)
            if target.user_id == "2":
                raise audit.RemoteApiError("suppression failed")
            return deferred_receipt(
                cycle_id=cycle_id,
                plex_user_id=target.user_id,
                planned_action="notice-started",
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "users": {},
                        "memberNotificationPermitHistory": {},
                        "lastCompletedAt": old_completed,
                    }
                ),
                encoding="utf-8",
            )
            exit_code, calls, _, stderr = self.run_worker(
                accounts=candidates,
                registry_path=path,
                responder=responder,
            )

            self.assertEqual(1, exit_code)
            self.assertEqual(
                ["suppress", "suppress"],
                [item["notification_mode"] for item in calls],
            )
            self.assertIn('"phase": "suppress"', stderr)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(old_completed, saved["lastCompletedAt"])
            self.assertNotIn("memberNotificationGate", saved)

    def test_ambiguous_permit_failure_stays_reserved_and_is_not_retried(self):
        target = self.inactive_account(username="alpha", user_id="1")

        def failing_responder(target, _decision, mode, cycle_id):
            if mode == audit.NOTIFICATION_MODE_SUPPRESS:
                return deferred_receipt(
                    cycle_id=cycle_id,
                    plex_user_id=target.user_id,
                    planned_action="notice-started",
                )
            raise audit.RemoteApiError("response timed out")

        def safe_responder(target, _decision, mode, cycle_id):
            self.assertEqual(audit.NOTIFICATION_MODE_SUPPRESS, mode)
            return deferred_receipt(
                cycle_id=cycle_id,
                plex_user_id=target.user_id,
                planned_action="notice-started",
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            first_code, first_calls, _, _ = self.run_worker(
                accounts=[target],
                registry_path=path,
                responder=failing_responder,
            )
            self.assertEqual(1, first_code)
            self.assertEqual(
                ["suppress", "permit"],
                [item["notification_mode"] for item in first_calls],
            )
            after_failure = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                "reserved", after_failure["memberNotificationGate"]["status"]
            )
            self.assertNotIn("lastCompletedAt", after_failure)

            second_code, second_calls, _, _ = self.run_worker(
                accounts=[target],
                registry_path=path,
                responder=safe_responder,
                observed_at=NOW + timedelta(hours=1),
            )
            self.assertEqual(0, second_code)
            self.assertEqual(
                ["suppress"],
                [item["notification_mode"] for item in second_calls],
            )

    def test_determinate_deferred_permit_receipts_complete_safely(self):
        target = self.inactive_account(username="alpha", user_id="1")
        scenarios = [
            {
                "name": "server-budget-exhausted",
                "response": lambda cycle_id: sync_receipt(
                    notification_mode=audit.NOTIFICATION_MODE_PERMIT,
                    cycle_id=cycle_id,
                    plex_user_id="1",
                    planned_action="notice-started",
                    permit_required=True,
                    budget_remaining=0,
                    result="deferred",
                    action=audit.NOTIFICATION_BUDGET_EXHAUSTED_ACTION,
                ),
                "status": "server-budget-exhausted",
            },
            {
                "name": "no-longer-required",
                "response": lambda cycle_id: sync_receipt(
                    notification_mode=audit.NOTIFICATION_MODE_PERMIT,
                    cycle_id=cycle_id,
                    plex_user_id="1",
                    planned_action="facts-only",
                    permit_required=False,
                    result="planned",
                ),
                "status": "no-longer-required",
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                def responder(target, _decision, mode, cycle_id):
                    if mode == audit.NOTIFICATION_MODE_SUPPRESS:
                        return deferred_receipt(
                            cycle_id=cycle_id,
                            plex_user_id=target.user_id,
                            planned_action="notice-started",
                        )
                    return scenario["response"](cycle_id)

                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "registry.json"
                    exit_code, calls, _, _ = self.run_worker(
                        accounts=[target],
                        registry_path=path,
                        responder=responder,
                    )
                    self.assertEqual(0, exit_code)
                    self.assertEqual(
                        ["suppress", "permit"],
                        [item["notification_mode"] for item in calls],
                    )
                    saved = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(
                        scenario["status"],
                        saved["memberNotificationGate"]["status"],
                    )
                    self.assertEqual(NOW.isoformat(), saved["lastCompletedAt"])

    def test_invalid_permit_receipt_remains_ambiguously_reserved(self):
        target = self.inactive_account(username="alpha", user_id="1")

        def responder(target, _decision, mode, cycle_id):
            if mode == audit.NOTIFICATION_MODE_SUPPRESS:
                return deferred_receipt(
                    cycle_id=cycle_id,
                    plex_user_id=target.user_id,
                    planned_action="notice-started",
                )
            invalid = sync_receipt(
                notification_mode=audit.NOTIFICATION_MODE_PERMIT,
                cycle_id=cycle_id,
                plex_user_id=target.user_id,
                planned_action="notice-started",
                permit_required=True,
                permit_reserved=True,
                budget_remaining=0,
            )
            invalid["cycleId"] = "audit-" + "f" * 32
            return invalid

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            exit_code, _, _, stderr = self.run_worker(
                accounts=[target],
                registry_path=path,
                responder=responder,
            )
            self.assertEqual(1, exit_code)
            self.assertIn("wrong cycle ID", stderr)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                "reserved", saved["memberNotificationGate"]["status"]
            )
            self.assertNotIn("lastCompletedAt", saved)

    def test_least_recently_permitted_candidate_rotates_after_window(self):
        candidates = [
            self.inactive_account(username="alpha", user_id="1"),
            self.inactive_account(username="beta", user_id="2"),
        ]

        def responder(target, _decision, mode, cycle_id):
            if mode == audit.NOTIFICATION_MODE_SUPPRESS:
                return deferred_receipt(
                    cycle_id=cycle_id,
                    plex_user_id=target.user_id,
                    planned_action="review-already-in-progress",
                )
            return sync_receipt(
                notification_mode=audit.NOTIFICATION_MODE_PERMIT,
                cycle_id=cycle_id,
                plex_user_id=target.user_id,
                planned_action="review-already-in-progress",
                permit_required=True,
                permit_reserved=True,
                budget_remaining=0,
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            first_code, first_calls, _, _ = self.run_worker(
                accounts=candidates,
                registry_path=path,
                responder=responder,
            )
            second_code, second_calls, _, _ = self.run_worker(
                accounts=candidates,
                registry_path=path,
                responder=responder,
                observed_at=NOW + timedelta(hours=24),
            )

            self.assertEqual(0, first_code)
            self.assertEqual(0, second_code)
            first_selected = [
                item["account"].user_id
                for item in first_calls
                if item["notification_mode"] == audit.NOTIFICATION_MODE_PERMIT
            ]
            second_selected = [
                item["account"].user_id
                for item in second_calls
                if item["notification_mode"] == audit.NOTIFICATION_MODE_PERMIT
            ]
            self.assertEqual(["1"], first_selected)
            self.assertEqual(["2"], second_selected)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                {"1", "2"},
                set(saved["memberNotificationPermitHistory"]),
            )

    def test_invalid_per_user_permit_history_fails_closed(self):
        invalid_histories = [
            [],
            {"": NOW.isoformat()},
            {"42": "not-a-timestamp"},
            {"42": NOW.replace(tzinfo=None).isoformat()},
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, history in enumerate(invalid_histories):
                with self.subTest(index=index):
                    path = Path(directory) / f"registry-{index}.json"
                    path.write_text(
                        json.dumps(
                            {
                                "schemaVersion": 1,
                                "users": {},
                                "memberNotificationPermitHistory": history,
                            }
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaises(audit.ConfigurationError):
                        audit.Registry(path).load()


if __name__ == "__main__":
    unittest.main()
