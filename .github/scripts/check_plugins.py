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
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Set


def get_plugin_directories(repo_root: Path) -> Set[str]:
    """Get all plugin directories (directories starting with 'sam-')."""
    plugins = set()
    for item in repo_root.iterdir():
        if item.is_dir() and item.name.startswith("sam-"):
            # Check if it's a valid plugin (has pyproject.toml)
            if (item / "pyproject.toml").exists():
                plugins.add(item.name)
    return plugins


def get_plugins_from_build_workflow(repo_root: Path) -> Set[str]:
    """Extract plugin names from build-plugin.yaml workflow."""
    workflow_path = repo_root / ".github" / "workflows" / "build-plugin.yaml"
    if not workflow_path.exists():
        return set()

    content = workflow_path.read_text()

    # Find the options list under workflow_dispatch
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

    # Find plugins in paths section with ! prefix (exclusions)
    plugins = set()
    for match in re.finditer(r'^\s*-\s*"!(sam-[\w-]+)/\*\*"', content, re.MULTILINE):
        plugins.add(match.group(1))

    return plugins


def get_plugins_from_manifest(repo_root: Path) -> Set[str]:
    """Extract plugin names from .release-please-manifest.json."""
    manifest_path = repo_root / ".release-please-manifest.json"
    if not manifest_path.exists():
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

    # Find all top-level keys that start with 'sam-'
    plugins = set()
    for line in content.split("\n"):
        match = re.match(r"^(sam-[\w-]+):", line)
        if match:
            plugins.add(match.group(1))

    return plugins


def main():
    # Find repository root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent

    print(f"Repository root: {repo_root}")
    print()

    # Get all plugin directories
    actual_plugins = get_plugin_directories(repo_root)
    print(f"Found {len(actual_plugins)} plugin directories:")
    for plugin in sorted(actual_plugins):
        print(f"  - {plugin}")
    print()

    # Check each config file
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

        missing = actual_plugins - config_plugins
        extra = config_plugins - actual_plugins

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
            print(f"  ✅ All {len(config_plugins)} plugins are configured")

        print()

    # Summary
    if all_match:
        print("✅ All configuration files are in sync with plugin directories!")
        return 0
    else:
        print("❌ Some configuration files need to be updated.")
        print("   Run 'python .github/scripts/add_missing_plugins.py' to fix.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
