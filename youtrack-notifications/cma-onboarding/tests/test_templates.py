"""Offline source-to-FreeMarker regression tests. No live services or real members."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("welcome_builder", ROOT / "build_templates.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
TITLE = "Welcome to Cameron-Media — Your access is ready"
MARKER = "<!-- CamCore:CMA:onboarding:v1 -->\n\n## Welcome to Cameron-Media\n"
BODY = builder.BODY
SUBJECT = builder.SUBJECT


class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.java = os.environ.get("CMA_TEST_JAVA", "java")
        cls.javac = os.environ.get("CMA_TEST_JAVAC", "javac")
        cls.jar = Path(os.environ["CMA_TEST_FREEMARKER_JAR"]).resolve()
        expected = "9a9fb91cd64199232eb1ca9766148a5d30ef8944be5fac051018f96c70c8f6a3"
        if hashlib.sha256(cls.jar.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Unexpected FreeMarker artifact")
        cls.temp = tempfile.TemporaryDirectory(prefix="cma-welcome-offline-")
        cls.work = Path(cls.temp.name)
        cls.classes = cls.work / "classes"
        cls.classes.mkdir()
        subprocess.run([cls.javac, "-cp", str(cls.jar), "-d", str(cls.classes), str(ROOT / "tests/RenderTemplate.java")], check=True, capture_output=True, text=True)
        cls.base = cls.work / "baseline"
        cls.draft = cls.work / "draft"
        cls.base.mkdir()
        # Git may check out FTL as CRLF on Windows. Render the documented
        # canonical LF capture, just as the builder does, without normalizing
        # either rendered result or weakening the byte-for-byte assertion.
        for fixture in (ROOT / "baseline").glob("*.ftl"):
            (cls.base / fixture.name).write_bytes(
                builder.source("baseline/" + fixture.name).encode("utf-8")
            )
        builder.build(cls.draft)
        for directory in (cls.base, cls.draft):
            # Only this unexported platform include is a simplified stub.
            (directory / "helpdesk_head_styles.ftl").write_text('<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>\n', encoding="utf-8")
        shutil.copyfile(cls.base / "helpdesk_footer.ftl", cls.draft / "helpdesk_footer.ftl")
        node = os.environ.get("CMA_TEST_NODE", "node")
        result = subprocess.run([node, str(ROOT / "tests/description-fixture.js")], check=True, capture_output=True, text=True, encoding="utf-8")
        cls.descriptions = json.loads(result.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def render(self, directory, name, overrides=None):
        values = {
            "issue.id": "CMA-999001", "issue.summary": TITLE,
            "issue.description": self.descriptions["welcome"],
            "threadSubject": TITLE, "commentFromReply": "false",
        }
        values.update(overrides or {})
        def escape(value):
            return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        props = self.work / "case.properties"
        props.write_text("\n".join(key + "=" + escape(value) for key, value in values.items() if value is not None), encoding="utf-8")
        output = self.work / "rendered.txt"
        command = [self.java, "-cp", str(self.jar) + os.pathsep + str(self.classes), "RenderTemplate", str(directory), name, str(props), str(output)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return output.read_bytes()

    def test_canonical_capture_matches_independent_dom_readback(self):
        expected = {
            BODY: (13459, 293, "f189849d"),
            SUBJECT: (83, 1, "b28e3e41"),
            "helpdesk_footer.ftl": (4478, 116, "53030097"),
        }
        for name, (chars, lines, checksum) in expected.items():
            content = builder.source("baseline/" + name).removesuffix("\n")
            self.assertEqual(len(content), chars)
            self.assertEqual(len(content.split("\n")), lines)
            value = 2166136261
            for char in content:
                value = ((value ^ ord(char)) * 16777619) & 0xffffffff
            self.assertEqual(f"{value:08x}", checksum)

    def test_actual_app_description_contract(self):
        self.assertTrue(self.descriptions["welcome"].startswith(MARKER))
        self.assertNotIn(MARKER, self.descriptions["review"])
        for link in ("https://app.plex.tv/desktop/", "https://www.plex.tv/apps-devices/", "https://camcore.au", "https://requests.camcore.au", "https://status.camcore.au"):
            self.assertIn(link, self.descriptions["welcome"])
            self.assertIn(link, builder.source("welcome-content.ftl"))

    def test_baseline_fixtures_use_canonical_lf_after_checkout(self):
        for name in (BODY, SUBJECT, "helpdesk_footer.ftl"):
            data = (self.base / name).read_bytes()
            self.assertEqual(data, builder.source("baseline/" + name).encode("utf-8"))
            self.assertNotIn(b"\r", data)

    def test_welcome_contents_for_both_reply_modes(self):
        for reply in ("true", "false"):
            with self.subTest(reply=reply):
                html = self.render(self.draft, BODY, {"commentFromReply": reply}).decode("utf-8")
                for value in ("Welcome to Cameron-Media", "Your access is now ready", "Accept your Plex invitation", "Plex Web App", "Plex Apps &amp; Devices", "Find your libraries", "Media Requests", "Service Status", "help@camcore.au", "Open your welcome ticket", "CMA-999001", "No reply is needed"):
                    self.assertIn(value, html)
                for value in ("Request received", "Thank you for contacting", "review the details and respond", "If you did not submit", "safely ignore", "Future updates will be delivered", "CamCore:CMA:onboarding", "synthetic-member"):
                    self.assertNotIn(value, html)
                self.assertEqual("Reply directly to this email" in html, reply == "true")
                self.assertIn("https://example.invalid/ticket?test=1&amp;view=welcome", html)
                self.assertEqual(self.render(self.draft, SUBJECT).decode("utf-8"), TITLE + "\n")
                preview = os.environ.get("CMA_TEST_PREVIEW_DIR")
                if preview:
                    Path(preview).mkdir(parents=True, exist_ok=True)
                    (Path(preview) / ("welcome-reply-" + reply + ".html")).write_text(html, encoding="utf-8")

    def test_non_onboarding_output_byte_for_byte_unchanged(self):
        cases = {
            "ordinary": {"issue.summary": "Synthetic account question", "issue.description": "Please help"},
            "actual_review": {"issue.summary": "Account Review — synthetic-member", "issue.description": self.descriptions["review"]},
            "title_only": {"issue.description": "## Welcome to Cameron-Media\nUnmarked legacy ticket"},
            "marker_wrong_title": {"issue.summary": "Synthetic account question"},
            "other_project": {"issue.id": "SUP-999001"},
            "operations": {"issue.id": "OPS-999001"},
            "invalid_id": {"issue.id": "CMA-099"},
            "id_suffix": {"issue.id": "CMA-999001\n"},
            "missing_description": {"issue.description": None},
            "null_description": {"issue.description.kind": "null"},
            "number_description": {"issue.description.kind": "number"},
            "list_description": {"issue.description.kind": "list"},
            "missing_summary": {"issue.summary": None},
            "boolean_summary": {"issue.summary.kind": "boolean"},
            "middle_marker": {"issue.description": "Text before marker\n" + self.descriptions["welcome"]},
            "wrong_version": {"issue.description": self.descriptions["welcome"].replace("onboarding:v1", "onboarding:v2")},
            "wrong_heading": {"issue.description": self.descriptions["welcome"].replace("## Welcome", "## Not welcome")},
            "empty_description": {"issue.description": ""},
            "title_suffix": {"issue.summary": TITLE + "\nInjected"},
        }
        for label, values in cases.items():
            for reply in ("true", "false"):
                for name in (BODY, SUBJECT):
                    with self.subTest(case=label, reply=reply, component=name):
                        fixture = {**values, "commentFromReply": reply}
                        self.assertEqual(self.render(self.base, name, fixture), self.render(self.draft, name, fixture))

    def test_crlf_marker_is_accepted_without_rendering_description(self):
        html = self.render(self.draft, BODY, {"issue.description": self.descriptions["welcome"].replace("\n", "\r\n")}).decode("utf-8")
        self.assertIn("Welcome to Cameron-Media", html)
        self.assertNotIn("Request received", html)

    def test_untrusted_description_and_subject_are_not_rendered_for_welcome(self):
        values = {"issue.description": self.descriptions["hostile"] + '\n<script>alert(7)</script>', "threadSubject": "Injected\r\nBcc: nobody@example.invalid"}
        html = self.render(self.draft, BODY, values).decode("utf-8")
        for text in ("<script", "onerror=", "Bcc:", "nobody@example.invalid"):
            self.assertNotIn(text, html)
        self.assertEqual(self.render(self.draft, SUBJECT, values).decode("utf-8"), TITLE + "\n")

    def test_platform_url_is_html_escaped(self):
        html = self.render(self.draft, BODY, {"confirmationURL": 'https://example.invalid/?a="x"&b=<tag>'}).decode("utf-8")
        self.assertIn('https://example.invalid/?a=&quot;x&quot;&amp;b=&lt;tag&gt;', html)
        self.assertNotIn('b=<tag>', html)

    def test_only_two_deployment_templates_are_built(self):
        outputs = builder.templates()
        self.assertEqual(set(outputs), {BODY, SUBJECT})
        self.assertNotIn('helpdesk_footer.ftl', outputs)
        self.assertEqual(outputs, builder.templates())
        original = builder.source("baseline/" + BODY)
        draft = outputs[BODY]
        start, end = original.index("<!-- CamCore header -->"), original.index("<!-- Main content -->")
        self.assertIn(original[start:end], draft)
        with self.assertRaises(ValueError):
            builder.replace_once("changed source", "missing anchor", "replacement")


if __name__ == "__main__":
    unittest.main(verbosity=2)
