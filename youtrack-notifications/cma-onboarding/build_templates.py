"""Build review-only templates locally. No credentials, HTTP or deployment code."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BODY = "helpdesk_online_form_confirmation_email.ftl"
SUBJECT = "helpdesk_online_form_confirmation_subject.ftl"


def source(name: str) -> str:
    # Canonical DOM capture: LF with exactly one final newline, UTF-8 no BOM.
    return (ROOT / name).read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("Baseline anchor changed; review required")
    return text.replace(old, new, 1)


def templates() -> dict[str, str]:
    body = source("baseline/" + BODY)
    selector = source("selector.ftl")
    begin = "                            <div style=\"\n                                display:inline-block;"
    end = "                            <div style=\"\n                                padding-top:24px;"
    if body.count(begin) != 1 or body.count(end) != 1:
        raise ValueError("Main-content boundary changed; review required")
    first, last = body.index(begin), body.index(end)
    original = body[first:last]
    body = body[:first] + "<#if camcoreOnboarding>\n" + source("welcome-content.ftl") + "<#else>\n" + original + "</#if>\n" + body[last:]
    # Inline only a welcome-specific copy. The shared live footer is not edited.
    footer = source("baseline/helpdesk_footer.ftl")
    footer = replace_once(footer, "CamCore Account Administration", "Cameron-Media | CamCore")
    footer = replace_once(footer, "Account Administration for CamCore services, accounts and managed devices.", "Media streaming, services and support from CamCore.")
    footer = replace_once(footer, "This message relates to a CamCore account administration request and may", "This welcome message relates to your Cameron-Media access and may")
    body = replace_once(body, '<#include "helpdesk_footer.ftl">', '<#if camcoreOnboarding>\n' + footer + '<#else>\n<#include "helpdesk_footer.ftl">\n</#if>')
    # No newline around the subject branch: the ordinary subject remains exact.
    subject = selector + '<#if camcoreOnboarding>Welcome to Cameron-Media — Your access is ready<#else>' + source("baseline/" + SUBJECT).rstrip("\n") + '</#if>\n'
    return {BODY: selector + body, SUBJECT: subject}


def build(destination: Path) -> dict[str, str]:
    destination.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, content in templates().items():
        data = content.encode("utf-8")
        (destination / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    (destination / "SHA256.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    return hashes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
