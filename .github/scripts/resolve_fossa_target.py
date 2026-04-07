#!/usr/bin/env python3
"""Resolve FOSSA branch/revision target for plugin builds.

This script centralizes the workflow logic that determines:
- branch
- revision
- enable_diff_mode
- diff_base_revision_sha

Inputs are provided via environment variables by `build-plugin.yaml`.
Outputs are written to `GITHUB_OUTPUT`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RELEASE_MANIFEST = ".release-please-manifest.json"


def _read_manifest_version(manifest_path: Path, plugin: str) -> str:
    if not manifest_path.exists():
        return ""
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    value = payload.get(plugin, "") if isinstance(payload, dict) else ""
    return str(value).strip()


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _manifest_version_at_revision(plugin: str, revision: str) -> str:
    if not revision:
        return ""
    result = _run_git(["show", f"{revision}:{RELEASE_MANIFEST}"])
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    try:
        payload = json.loads(result.stdout)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get(plugin, "")).strip()


def _main_branch_version_bump(before_sha: str, current_sha: str, plugin: str) -> str:
    if not before_sha or not current_sha:
        return ""

    exists = _run_git(["cat-file", "-e", before_sha])
    if exists.returncode != 0:
        return ""

    changed = _run_git(
        ["diff", "--name-only", before_sha, current_sha, "--", RELEASE_MANIFEST]
    )
    if changed.returncode != 0 or RELEASE_MANIFEST not in changed.stdout:
        return ""

    old_version = _manifest_version_at_revision(plugin, before_sha)
    new_version = _manifest_version_at_revision(plugin, current_sha)
    if new_version and new_version != old_version:
        return new_version
    return ""


def _hatch_version(plugin_dir: str) -> str:
    if not plugin_dir:
        return ""
    result = subprocess.run(
        ["hatch", "version"],
        cwd=plugin_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _write_output(name: str, value: str) -> None:
    output_path = os.getenv("GITHUB_OUTPUT", "")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    ref_hint = os.getenv("REF_HINT", "").strip()
    event_name = os.getenv("EVENT_NAME", "").strip()
    head_ref = os.getenv("HEAD_REF", "").strip()
    default_branch = os.getenv("DEFAULT_BRANCH", "").strip()
    current_ref_name = os.getenv("CURRENT_REF_NAME", "").strip()
    before_sha = os.getenv("BEFORE_SHA", "").strip()
    current_sha = os.getenv("CURRENT_SHA", "").strip()
    plugin_dir = os.getenv("PLUGIN_DIRECTORY", "").strip()
    pr_base_sha = os.getenv("PR_BASE_SHA", "").strip()

    manifest_file = Path(os.getenv("GITHUB_WORKSPACE", ".")) / RELEASE_MANIFEST
    manifest_version = _read_manifest_version(manifest_file, plugin_dir)

    if event_name == "pull_request":
        is_release_please_pr = "release-please" in head_ref
    else:
        is_release_please_pr = "release-please" in ref_hint

    main_bump_version = ""
    if event_name == "push" and current_ref_name == default_branch:
        main_bump_version = _main_branch_version_bump(before_sha, current_sha, plugin_dir)

    if is_release_please_pr:
        branch = "ReleasePleasePR"
        # Use commit SHA for release-please PR scans so we always query
        # the freshly analyzed revision, not a reused semantic version key.
        revision = current_sha or manifest_version or _hatch_version(plugin_dir)
        enable_diff_mode = "false"
        diff_base_revision_sha = ""
    elif event_name == "pull_request":
        branch = "PR"
        revision = head_ref
        enable_diff_mode = "true"
        diff_base_revision_sha = pr_base_sha
    elif event_name == "push" and current_ref_name == default_branch:
        branch = "main"
        revision = main_bump_version or current_sha
        enable_diff_mode = "false"
        diff_base_revision_sha = ""
    else:
        branch = default_branch
        revision = current_sha
        enable_diff_mode = "false"
        diff_base_revision_sha = ""

    resolved = {
        "branch": branch,
        "revision": revision,
        "enable_diff_mode": enable_diff_mode,
        "diff_base_revision_sha": diff_base_revision_sha,
    }

    for key, value in resolved.items():
        _write_output(key, value)

    print(
        "Resolved FOSSA scan target:"
        f" branch={branch}"
        f" revision={revision}"
        f" diff_mode={enable_diff_mode}"
        f" diff_base={diff_base_revision_sha or '<none>'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
