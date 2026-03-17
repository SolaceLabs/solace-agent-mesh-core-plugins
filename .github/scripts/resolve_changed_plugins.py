#!/usr/bin/env python3
"""Resolve changed plugins for matrix builds and exclude deprecated plugins."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Iterable

from plugin_exceptions import DEPRECATED_PLUGINS


def _run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def _write_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT", "")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _changed_files_for_pr(base_sha: str, head_sha: str) -> list[str]:
    if not base_sha or not head_sha:
        return []
    result = _run_cmd(["git", "diff", "--name-only", base_sha, head_sha])
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _changed_files_for_push() -> list[str]:
    result = _run_cmd(["git", "diff", "--name-only", "HEAD~1", "HEAD"])
    if result.returncode == 0:
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    root = _run_cmd(["git", "rev-list", "--max-parents=0", "HEAD"])
    if root.returncode != 0:
        return []
    root_sha = root.stdout.strip().splitlines()[0] if root.stdout.strip() else ""
    if not root_sha:
        return []
    fallback = _run_cmd(["git", "diff", "--name-only", root_sha, "HEAD"])
    if fallback.returncode != 0:
        return []
    return [line.strip() for line in fallback.stdout.splitlines() if line.strip()]


def _extract_plugins(changed_files: Iterable[str]) -> list[str]:
    plugins = set()
    for file_path in changed_files:
        if not file_path.startswith("sam-") or "/" not in file_path:
            continue
        plugins.add(file_path.split("/", 1)[0])
    return sorted(plugin for plugin in plugins if plugin not in DEPRECATED_PLUGINS)


def _to_matrix_json(plugins: list[str]) -> str:
    matrix = [{"plugin_directory": plugin} for plugin in plugins]
    return json.dumps(matrix, separators=(",", ":"))


def main() -> int:
    event_name = os.getenv("EVENT_NAME", "").strip()
    base_sha = os.getenv("PR_BASE_SHA", "").strip()
    head_sha = os.getenv("PR_HEAD_SHA", "").strip()
    pr_number = os.getenv("PR_NUMBER", "").strip()

    if event_name == "pull_request":
        changed_files = _changed_files_for_pr(base_sha, head_sha)
        resolved_pr_number = pr_number
    elif event_name == "push":
        changed_files = _changed_files_for_push()
        resolved_pr_number = ""
    else:
        changed_files = []
        resolved_pr_number = ""

    plugins = _extract_plugins(changed_files)
    plugins_csv = ",".join(plugins)
    matrix_json = _to_matrix_json(plugins)

    print(f"Detected changed files: {len(changed_files)}")
    print(f"Changed plugins: {plugins_csv}")
    print(f"Filtered deprecated plugins: {len(plugins)} selected")

    _write_output("plugins", plugins_csv)
    _write_output("all_plugins", matrix_json)
    _write_output("pr_number", resolved_pr_number)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
