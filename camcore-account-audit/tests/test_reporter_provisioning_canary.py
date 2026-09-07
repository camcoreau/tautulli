"""End-to-end tests for tools/reporter_provisioning_canary.py against a fake YouTrack."""

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
CANARY = ROOT / "tools" / "reporter_provisioning_canary.py"
PROVISION_TOKEN = "perm-PROVISION-not-real"
SYNC_TOKEN = "perm-SYNC-not-real"


class FakeYouTrack(BaseHTTPRequestHandler):
    state: dict = {}

    def log_message(self, *args):  # silence
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self):
        return self.headers.get("Authorization") == f"Bearer {PROVISION_TOKEN}"

    def do_GET(self):
        st = FakeYouTrack.state
        st["requests"].append(("GET", self.path, self.headers.get("Authorization")))
        if not self._authorised():
            return self._json(401, {"error": "Unauthorized"})
        parts = urlsplit(self.path)
        if parts.path == "/api/users":
            query = parse_qs(parts.query)
            top = int(query.get("$top", ["100"])[0])
            skip = int(query.get("$skip", ["0"])[0])
            return self._json(200, st["users"][skip : skip + top])
        if parts.path.startswith("/api/users/"):
            uid = parts.path.rsplit("/", 1)[1]
            for user in st["users"]:
                if user["id"] == uid:
                    return self._json(200, user)
            return self._json(404, {"error": "not found"})
        self._json(404, {"error": "nf"})

    def do_POST(self):
        st = FakeYouTrack.state
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        st["requests"].append(("POST", self.path, self.headers.get("Authorization")))
        st["posts"].append(body)
        if not self._authorised():
            return self._json(401, {"error": "Unauthorized"})
        if urlsplit(self.path).path != "/api/users":
            return self._json(404, {"error": "nf"})
        if not body.get("password"):
            return self._json(400, {"error": "password is required"})
        user = {
            "id": f"2-{100 + len(st['posts'])}",
            "login": body["login"],
            "fullName": body.get("fullName"),
            "email": body.get("email"),
            "banned": False,
            "userType": {"id": st.get("created_type", body["userType"]["id"])},
        }
        st["users"].append(user)
        self._json(200, user)


class CanaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeYouTrack)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeYouTrack.state = {
            "users": [
                {"id": "2-1", "login": "admin", "fullName": "Admin", "email": "admin@example.invalid",
                 "banned": False, "userType": {"id": "STANDARD_USER"}},
                {"id": "2-2", "login": "agent", "fullName": "Agent", "email": "agent@example.invalid",
                 "banned": False, "userType": {"id": "AGENT"}},
                {"id": "2-3", "login": "rep", "fullName": "Reporter", "email": "rep@example.invalid",
                 "banned": False, "userType": {"id": "REPORTER"}},
            ],
            "posts": [],
            "requests": [],
        }

    def run_canary(self, mode, **env_overrides):
        env = dict(
            os.environ,
            TAUTULLI_URL="http://127.0.0.1:1",
            TAUTULLI_API_KEY="tautulli-not-real",
            YOUTRACK_SYNC_URL=(
                f"http://127.0.0.1:{self.port}/api/admin/projects/CMA/"
                "extensionEndpoints/cma-account-audit/account-sync/sync-account"
            ),
            YOUTRACK_TOKEN=SYNC_TOKEN,
            YOUTRACK_REPORTER_PROVISION_TOKEN=PROVISION_TOKEN,
            DRY_RUN="false",
            CANARY_PLEX_USER_ID="ops343-canary-000001",
            CANARY_USERNAME="ops343-canary",
            CANARY_EMAIL="canary@example.invalid",
        )
        env.pop("REPORTER_PROVISIONING_ENABLED", None)
        env.pop("CANARY_CONFIRM", None)
        env.update(env_overrides)
        proc = subprocess.run(
            [sys.executable, str(CANARY), mode], env=env, capture_output=True, text=True
        )
        receipt = json.loads(proc.stdout.strip().splitlines()[-1])
        return proc.returncode, receipt, proc.stdout + proc.stderr

    def assert_no_secrets(self, output):
        self.assertNotIn(PROVISION_TOKEN, output)
        self.assertNotIn(SYNC_TOKEN, output)
        self.assertNotIn("canary@example.invalid", output)
        for post in FakeYouTrack.state["posts"]:
            self.assertNotIn(post["password"], output)

    def test_preview_is_read_only(self):
        rc, receipt, output = self.run_canary("preview")
        self.assertEqual(0, rc, output)
        self.assertEqual("preview-only", receipt["phase"])
        self.assertEqual(0, receipt["createRequests"])
        self.assertEqual({"STANDARD_USER": 1, "AGENT": 1, "REPORTER": 1}, receipt["before"]["userTypeCounts"])
        self.assertEqual([], receipt["before"]["emailMatches"])
        self.assertEqual([], FakeYouTrack.state["posts"])
        self.assertTrue(all(auth == f"Bearer {PROVISION_TOKEN}" for _, _, auth in FakeYouTrack.state["requests"]))
        self.assert_no_secrets(output)

    def test_run_requires_confirmation(self):
        rc, receipt, output = self.run_canary("run")
        self.assertEqual(5, rc)
        self.assertEqual("held", receipt["phase"])
        self.assertEqual([], FakeYouTrack.state["posts"])

    def test_run_creates_exactly_one_reporter_and_verifies_counts(self):
        rc, receipt, output = self.run_canary("run", CANARY_CONFIRM="yes")
        self.assertEqual(0, rc, output)
        self.assertEqual("complete", receipt["phase"])
        self.assertTrue(receipt["accepted"])
        self.assertEqual(1, receipt["createRequests"])
        self.assertEqual(1, len(FakeYouTrack.state["posts"]))
        post = FakeYouTrack.state["posts"][0]
        self.assertEqual({"id": "REPORTER"}, post["userType"])
        self.assertEqual(receipt["identity"]["expectedLogin"], post["login"])
        self.assertEqual("REPORTER", receipt["created"]["userType"])
        self.assertEqual({"STANDARD_USER": 1, "AGENT": 1, "REPORTER": 2}, receipt["after"]["userTypeCounts"])
        self.assertEqual([receipt["created"]["id"]], [u["id"] for u in receipt["after"]["emailMatches"]])
        self.assert_no_secrets(output)

    def test_run_holds_when_email_already_matches(self):
        FakeYouTrack.state["users"].append(
            {"id": "2-9", "login": "existing", "fullName": "E", "email": "Canary@Example.INVALID",
             "banned": False, "userType": {"id": "REPORTER"}}
        )
        rc, receipt, output = self.run_canary("run", CANARY_CONFIRM="yes")
        self.assertEqual(5, rc)
        self.assertEqual("held", receipt["phase"])
        self.assertEqual(["2-9"], [u["id"] for u in receipt["before"]["emailMatches"]])
        self.assertEqual([], FakeYouTrack.state["posts"])

    def test_run_holds_in_dry_run(self):
        rc, receipt, output = self.run_canary("run", CANARY_CONFIRM="yes", DRY_RUN="true")
        self.assertEqual(5, rc)
        self.assertEqual("held", receipt["phase"])
        self.assertEqual([], FakeYouTrack.state["posts"])

    def test_wrong_persisted_type_is_reported_and_trips(self):
        FakeYouTrack.state["created_type"] = "STANDARD_USER"
        rc, receipt, output = self.run_canary("run", CANARY_CONFIRM="yes")
        self.assertEqual(6, rc)
        self.assertEqual("create-failed", receipt["phase"])
        self.assertIn("not REPORTER", receipt["tripped"])
        self.assertIn("reporter-provisioning-tripped", output)
        self.assert_no_secrets(output)

    def test_rejects_non_synthetic_identifier(self):
        rc, receipt, output = self.run_canary("preview", CANARY_PLEX_USER_ID="12345678")
        self.assertEqual(2, rc)
        self.assertEqual([], FakeYouTrack.state["requests"])


if __name__ == "__main__":
    unittest.main()
