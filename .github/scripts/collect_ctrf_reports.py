#!/usr/bin/env python3
"""Collect per-project CTRF reports from CI result payloads."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT", "")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    results_dir = Path(os.getenv("RESULTS_DIR", "ci-plugin-results"))
    output_dir = Path(os.getenv("OUTPUT_DIR", "ctrf-plugin-reports"))
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for path in results_dir.rglob("*.json"):
        payload = _read_json(path)
        project = str(payload.get("project") or payload.get("plugin") or "").strip()
        ctrf = payload.get("unit_test_report", {})
        if not project or not isinstance(ctrf, dict):
            continue
        if not ctrf.get("results"):
            continue
        (output_dir / f"{project}.json").write_text(
            json.dumps(ctrf, indent=2),
            encoding="utf-8",
        )
        count += 1

    _write_output("count", str(count))
    _write_output("has_reports", "true" if count > 0 else "false")
    print(f"Collected {count} CTRF report(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
