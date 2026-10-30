"""Validate Snyk scan artifacts before upload.

The report is optional only when no scan was attempted or the scanner itself
failed (those cases are already reflected in the job result). Metadata is
required for every run that reached image inspection.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPORT_OPTIONAL_STATUSES = {
    "skipped_no_token",
    "scanner_error",
    "report_error",
    "not_run",
}


def load_json_object(path: str | Path, label: str) -> dict:
    file_path = Path(path)
    if not file_path.is_file() or file_path.stat().st_size == 0:
        raise ValueError(f"{label} is missing or empty: {file_path}")
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON: {file_path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {file_path}")
    return value


def validate_artifacts(report_path: str | Path, metadata_path: str | Path, scan_status: str) -> None:
    load_json_object(metadata_path, "Image metadata")
    if scan_status not in REPORT_OPTIONAL_STATUSES:
        load_json_object(report_path, "Snyk report")


def main() -> int:
    try:
        validate_artifacts(
            os.environ["REPORT_PATH"],
            os.environ["METADATA_PATH"],
            os.environ.get("SCAN_RESULT", "not_run"),
        )
    except (KeyError, ValueError) as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    print("Snyk artifact JSON validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
