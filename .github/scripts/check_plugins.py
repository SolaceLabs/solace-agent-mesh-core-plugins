#!/usr/bin/env python3
"""
Check that all plugin directories are listed in the configuration files.

This script scans the repository for plugin directories (sam-*) and verifies
they are properly configured in:
- .github/workflows/build-plugin.yaml
- .github/workflows/sync-plugin-configs.yaml (paths exclusions)
- .release-please-manifest.json
- release-please-config.json
- .github/pr_labeler.yaml

Why this script exists:
- Plugin onboarding/removal touches multiple files.
- Missing one file causes CI gaps, release issues, or unlabeled PRs.
- This script provides a single consistency check and fails fast.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Set

from plugin_exceptions import DEPRECATED_PLUGINS


def get_plugin_directories(repo_root: Path) -> Set[str]:
    """Get all plugin directories (directories starting with 'sam-')."""
    plugins = set()
    for item in repo_root.iterdir():
        if item.is_dir() and item.name.startswith("sam-"):
            # Treat only Python package directories as plugins to avoid
            # counting utility/demo folders that start with `sam-`.
            if (item / "pyproject.toml").exists():
                plugins.add(item.name)
    return plugins


def get_plugins_from_build_workflow(repo_root: Path) -> Set[str]:
    """Extract plugin names from build-plugin.yaml workflow."""
    workflow_path = repo_root / ".github" / "workflows" / "build-plugin.yaml"
    if not workflow_path.exists():
        return set()

    content = workflow_path.read_text()

    # Parse the workflow-dispatch plugin options list without adding a YAML
    # dependency to this script. We rely on indentation + "- sam-..." pattern.
    plugins = set()
    in_options = False
    for line in content.split("\n"):
        if "options:" in line:
            in_options = True
            continue
        if in_options:
            if line.strip() and not line.strip().startswith("-"):
                if not line.startswith(" " * 10):
                    break
            match = re.match(r"\s*-\s*(sam-[\w-]+)", line)
            if match:
                plugins.add(match.group(1))

    return plugins


def get_plugins_from_sync_workflow(repo_root: Path) -> Set[str]:
    """Extract plugin names from sync-plugin-configs.yaml paths exclusions (!)."""
    workflow_path = repo_root / ".github" / "workflows" / "sync-plugin-configs.yaml"
    if not workflow_path.exists():
        return set()

    content = workflow_path.read_text()

    # This workflow keeps plugin paths in exclusion format: "!sam-foo/**".
    plugins = set()
    for match in re.finditer(r'^\s*-\s*"!(sam-[\w-]+)/\*\*"', content, re.MULTILINE):
        plugins.add(match.group(1))

    return plugins


def get_plugins_from_manifest(repo_root: Path) -> Set[str]:
    """Extract plugin names from .release-please-manifest.json."""
    manifest_path = repo_root / ".release-please-manifest.json"
    if not manifest_path.exists():
        # Missing file should surface as mismatch in the final comparison.
        return set()

    with open(manifest_path) as f:
        manifest = json.load(f)

    return set(manifest.keys())


def get_plugins_from_release_config(repo_root: Path) -> Set[str]:
    """Extract plugin names from release-please-config.json."""
    config_path = repo_root / "release-please-config.json"
    if not config_path.exists():
        return set()

    with open(config_path) as f:
        config = json.load(f)

    return set(config.get("packages", {}).keys())


def get_plugins_from_pr_labeler(repo_root: Path) -> Set[str]:
    """Extract plugin names from .github/pr_labeler.yaml."""
    labeler_path = repo_root / ".github" / "pr_labeler.yaml"
    if not labeler_path.exists():
        return set()

    content = labeler_path.read_text()

    # Labeler config uses plugin names as top-level YAML keys.
    plugins = set()
    for line in content.split("\n"):
        match = re.match(r"^(sam-[\w-]+):", line)
        if match:
            plugins.add(match.group(1))

    return plugins


def main():
    # Resolve repo root relative to this script location so the command works
    # regardless of current working directory.
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent

    print(f"Repository root: {repo_root}")
    print()

    # The source of truth is active plugin directories in the repository.
    # Deprecated plugins are ignored to avoid forcing legacy config churn.
    all_plugins = get_plugin_directories(repo_root)
    deprecated_plugins = all_plugins & DEPRECATED_PLUGINS
    actual_plugins = all_plugins - DEPRECATED_PLUGINS

    print(f"Found {len(all_plugins)} plugin directories:")
    for plugin in sorted(all_plugins):
        print(f"  - {plugin}")
    print()

    if deprecated_plugins:
        print(f"Ignoring {len(deprecated_plugins)} deprecated plugins:")
        for plugin in sorted(deprecated_plugins):
            print(f"  - {plugin}")
        print()

    print(f"Using {len(actual_plugins)} active plugins for validation:")
    for plugin in sorted(actual_plugins):
        print(f"  - {plugin}")
    print()

    # Compare each config file against the active plugin set.
    all_match = True

    configs = [
        ("build-plugin.yaml", get_plugins_from_build_workflow(repo_root)),
        ("sync-plugin-configs.yaml", get_plugins_from_sync_workflow(repo_root)),
        (".release-please-manifest.json", get_plugins_from_manifest(repo_root)),
        ("release-please-config.json", get_plugins_from_release_config(repo_root)),
        ("pr_labeler.yaml", get_plugins_from_pr_labeler(repo_root)),
    ]

    for config_name, config_plugins in configs:
        print(f"Checking {config_name}...")

        # Deprecated plugins are excluded from both sides of comparison.
        filtered_config_plugins = config_plugins - DEPRECATED_PLUGINS
        missing = actual_plugins - filtered_config_plugins
        extra = filtered_config_plugins - actual_plugins

        if missing:
            all_match = False
            print("  ❌ Missing plugins:")
            for plugin in sorted(missing):
                print(f"      - {plugin}")

        if extra:
            all_match = False
            print("  ⚠️  Extra plugins (in config but not in repo):")
            for plugin in sorted(extra):
                print(f"      - {plugin}")

        if not missing and not extra:
            print(f"  ✅ All {len(filtered_config_plugins)} active plugins are configured")

        print()

    # Non-zero exit code lets CI fail when configuration drift is detected.
    if all_match:
        print("✅ All configuration files are in sync with plugin directories!")
        return 0
    else:
        print("❌ Some configuration files need to be updated.")
        print("   Run 'python .github/scripts/add_missing_plugins.py' to fix.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
