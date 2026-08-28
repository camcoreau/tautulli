import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "audit.py"
SPEC = importlib.util.spec_from_file_location("cma_audit", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


UTC = timezone.utc
NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def account(*, plays=1, last_streamed=None, username="member"):
    return audit.Account(
        user_id="42",
        username=username,
        email="member@example.invalid",
        last_streamed=last_streamed,
        total_plays=plays,
        watch_seconds=3600,
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


if __name__ == "__main__":
    unittest.main()
