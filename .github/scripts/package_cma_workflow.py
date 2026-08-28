"""Build the reviewed CMA YouTrack workflow upload archive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile


WORKFLOW_FILES = (
    "manifest.json",
    "entity-extensions.json",
    "audit-freshness-bridge.js",
    "communication-catchup.js",
    "communications.js",
    "deadline-transitions.js",
    "lifecycle-catchup.js",
    "lifecycle-transitions.js",
    "notice-escalation.js",
    "reporter-replies.js",
    "stage-communications.js",
)

EXPECTED_PROPERTIES = {
    "cmaMessageStateVersion": "integer",
    "cmaMessageSequence": "integer",
    "cmaObservedReviewStage": "string",
    "cmaPendingMessageKey": "string",
    "cmaPendingMessageToken": "string",
    "cmaDeliveredMessageToken": "string",
    "cmaDeliveredMessageAt": "integer",
    "cmaAccountAuditConfirmedAt": "integer",
    "cmaSuppressedReviewStage": "string",
}


def canonical_bytes(path: Path) -> bytes:
    """Return platform-independent UTF-8 bytes for reviewed text sources."""
    text = path.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def validate_declarations(source: Path) -> None:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "cma-account-review":
        raise SystemExit("The workflow app identity must remain cma-account-review")
    if manifest.get("minYouTrackVersion") != "2024.3.0":
        raise SystemExit("The workflow must require extension-property support")

    declaration = json.loads(
        (source / "entity-extensions.json").read_text(encoding="utf-8")
    )
    extensions = declaration.get("entityTypeExtensions")
    if not isinstance(extensions, list) or len(extensions) != 1:
        raise SystemExit("Expected exactly one entity type extension")
    if extensions[0].get("entityType") != "Issue":
        raise SystemExit("Delivery properties must extend Issue")
    properties = extensions[0].get("properties")
    actual = {
        name: value.get("type")
        for name, value in properties.items()
    } if isinstance(properties, dict) else {}
    if actual != EXPECTED_PROPERTIES:
        raise SystemExit(
            f"Delivery property declaration changed: expected {EXPECTED_PROPERTIES}, "
            f"found {actual}"
        )


def build_archive(source: Path, destination: Path) -> None:
    missing = [name for name in WORKFLOW_FILES if not (source / name).is_file()]
    if missing:
        raise SystemExit("Missing workflow files: " + ", ".join(missing))

    expected_scripts = sorted(name for name in WORKFLOW_FILES if name.endswith(".js"))
    actual_scripts = sorted(path.name for path in source.glob("*.js"))
    if actual_scripts != expected_scripts:
        raise SystemExit(
            "Production workflow script inventory changed; review WORKFLOW_FILES. "
            f"Expected {expected_scripts}, found {actual_scripts}"
        )
    validate_declarations(source)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name in WORKFLOW_FILES:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, canonical_bytes(source / name))

    with zipfile.ZipFile(destination, mode="r") as archive:
        if tuple(archive.namelist()) != WORKFLOW_FILES:
            raise SystemExit("Archive root inventory does not match the reviewed files")
        bad_entry = archive.testzip()
        if bad_entry:
            raise SystemExit(f"Archive integrity check failed for {bad_entry}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("youtrack-workflows/cma-account-review"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/cma-account-review.zip"),
    )
    args = parser.parse_args()
    build_archive(args.source.resolve(), args.output.resolve())
    print(args.output)


if __name__ == "__main__":
    main()
