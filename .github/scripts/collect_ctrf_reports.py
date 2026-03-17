#!/usr/bin/env python3
"""Collect per-plugin CTRF reports from CI payload artifacts.

Why this script exists:
- Each plugin build uploads a CI payload JSON that contains multiple fields.
- The CTRF merge/report steps need plain CTRF report files, one per plugin.
- This script extracts only `unit_test_report` and writes normalized files that
  downstream steps can merge and publish.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _write_output(name: str, value: str) -> None:
    # GitHub Actions uses the file path in GITHUB_OUTPUT for step outputs.
    # If not running inside Actions, writing outputs is a no-op.
    output_path = os.getenv("GITHUB_OUTPUT", "").strip()
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _read_payload(path: Path) -> dict[str, Any] | None:
    # Some JSON artifacts may be malformed or not match our expected schema.
    # We skip those safely so one bad file does not fail the whole step.
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_project_name(payload: dict[str, Any]) -> str:
    # Prefer `project` (current field), but keep `plugin` as a fallback
    # for backward compatibility with older payload versions.
    for key in ("project", "plugin"):
        name = str(payload.get(key, "")).strip()
        if name:
            return name
    return ""


def _extract_ctrf_report(payload: dict[str, Any]) -> dict[str, Any] | None:
    # Keep only valid CTRF-like objects with `results`; empty/missing reports
    # should not be emitted because downstream merge/report would be noisy.
    report = payload.get("unit_test_report", {})
    if not isinstance(report, dict):
        return None
    if not report.get("results"):
        return None
    return report


def main() -> int:
    # Allow directory overrides for local testing while keeping CI defaults.
    results_dir = Path(os.getenv("RESULTS_DIR", "ci-plugin-results")).resolve()
    output_dir = Path(os.getenv("OUTPUT_DIR", "ctrf-plugin-reports"))
    # Ensure output directory exists even when we collect zero reports.
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    # `actions/download-artifact` may be skipped; treat missing input as empty.
    if results_dir.exists():
        # Sort for deterministic behavior and stable debugging output.
        for payload_path in sorted(results_dir.rglob("*.json")):
            payload = _read_payload(payload_path)
            if payload is None:
                continue

            project_name = _resolve_project_name(payload)
            ctrf_report = _extract_ctrf_report(payload)
            if not project_name or ctrf_report is None:
                continue

            # Emit one CTRF file per plugin/project, named predictably for merge.
            (output_dir / f"{project_name}.json").write_text(
                json.dumps(ctrf_report, indent=2),
                encoding="utf-8",
            )
            count += 1

    # Expose outputs used by workflow conditions (`if:` guards).
    _write_output("count", str(count))
    _write_output("has_reports", "true" if count > 0 else "false")
    print(f"Collected {count} CTRF report(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
