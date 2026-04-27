#!/usr/bin/env python3
"""Fail when a command log contains warning output."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

WARNING_PATTERN = re.compile(r"(?i)(?:\bWARN\b|\b[\w-]*warnings?\b)")
IGNORED_SUBSTRINGS = (
    "--disable-warnings",
    "fail_on_warnings.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail if the provided log file contains warning output."
    )
    parser.add_argument("log_path", help="Path to the log file to inspect.")
    parser.add_argument(
        "--command",
        default="command",
        help="Human-readable command name for error messages.",
    )
    return parser.parse_args()


def collect_warning_lines(log_text: str) -> list[tuple[int, str]]:
    warning_lines: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(log_text.splitlines(), start=1):
        line = raw_line.rstrip()
        if not WARNING_PATTERN.search(line):
            continue
        if any(ignored in line for ignored in IGNORED_SUBSTRINGS):
            continue
        warning_lines.append((line_number, line))
    return warning_lines


def main() -> int:
    args = parse_args()
    log_text = Path(args.log_path).read_text(encoding="utf-8", errors="replace")
    warning_lines = collect_warning_lines(log_text)

    if not warning_lines:
        print(f"No warnings found in {args.command} output.")
        return 0

    print(f"{args.command} produced warnings; failing build.")
    print("Warning lines:")
    for line_number, line in warning_lines:
        print(f"{line_number}: {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
