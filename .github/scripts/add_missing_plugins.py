#!/usr/bin/env python3
"""
Add missing plugin directories to the configuration files.

This script scans the repository for plugin directories (sam-*) and adds
any missing ones to:
- .github/workflows/build-plugin.yaml
- .release-please-manifest.json
- release-please-config.json
- .github/pr_labeler.yaml
"""

from __future__ import annotations

import json
import os
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


def get_package_name(plugin_name: str) -> str:
    """Convert plugin directory name to Python package name."""
    return plugin_name.replace("-", "_")


def update_build_workflow(repo_root: Path, plugins: Set[str]) -> bool:
    """Update build-plugin.yaml with missing plugins."""
    workflow_path = repo_root / ".github" / "workflows" / "build-plugin.yaml"
    if not workflow_path.exists():
        print(f"  ⚠️  {workflow_path} does not exist, skipping")
        return False

    content = workflow_path.read_text()

    # Find existing plugins in options
    existing_plugins = set()
    for match in re.finditer(r"^\s*-\s*(sam-[\w-]+)\s*$", content, re.MULTILINE):
        existing_plugins.add(match.group(1))

    missing = plugins - existing_plugins
    if not missing:
        print("  ✅ build-plugin.yaml already has all plugins")
        return False

    # Find the options block and add missing plugins
    lines = content.split("\n")
    new_lines = []
    in_options = False
    options_indent = None
    last_option_idx = -1

    for i, line in enumerate(lines):
        new_lines.append(line)
        if "options:" in line and "plugin_directory" in "\n".join(
            lines[max(0, i - 5) : i]
        ):
            in_options = True
            # Get indentation of next line (the first option)
            continue
        if in_options:
            match = re.match(r"^(\s*)-\s*sam-[\w-]+", line)
            if match:
                options_indent = match.group(1)
                last_option_idx = len(new_lines) - 1
            elif (
                line.strip()
                and not line.strip().startswith("-")
                and not line.strip().startswith("#")
            ):
                # End of options block
                in_options = False

    if last_option_idx > 0 and options_indent:
        # Insert missing plugins after the last option
        for plugin in sorted(missing):
            new_lines.insert(last_option_idx + 1, f"{options_indent}- {plugin}")
            last_option_idx += 1

        workflow_path.write_text("\n".join(new_lines))
        print(f"  ✅ Added {len(missing)} plugins to build-plugin.yaml:")
        for plugin in sorted(missing):
            print(f"      - {plugin}")
        return True
    else:
        print("  ⚠️  Could not find options block in build-plugin.yaml")
        return False


def update_manifest(repo_root: Path, plugins: Set[str]) -> bool:
    """Update .release-please-manifest.json with missing plugins."""
    manifest_path = repo_root / ".release-please-manifest.json"

    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = {}

    missing = plugins - set(manifest.keys())
    if not missing:
        print("  ✅ .release-please-manifest.json already has all plugins")
        return False

    # Add missing plugins with initial version
    for plugin in sorted(missing):
        manifest[plugin] = "0.1.0"

    # Sort the manifest by key
    sorted_manifest = dict(sorted(manifest.items()))

    with open(manifest_path, "w") as f:
        json.dump(sorted_manifest, f, indent=2)
        f.write("\n")

    print(f"  ✅ Added {len(missing)} plugins to .release-please-manifest.json:")
    for plugin in sorted(missing):
        print(f"      - {plugin}: 0.1.0")
    return True


def update_release_config(repo_root: Path, plugins: Set[str]) -> bool:
    """Update release-please-config.json with missing plugins."""
    config_path = repo_root / "release-please-config.json"

    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        config = {
            "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
            "release-type": "python",
            "include-component-in-tag": True,
            "include-v-in-tag": False,
            "separate-pull-requests": False,
            "packages": {},
        }

    packages = config.get("packages", {})
    missing = plugins - set(packages.keys())

    if not missing:
        print("  ✅ release-please-config.json already has all plugins")
        return False

    # Add missing plugins
    for plugin in sorted(missing):
        packages[plugin] = {
            "package-name": get_package_name(plugin),
            "changelog-path": "CHANGELOG.md",
        }

    # Sort packages by key
    config["packages"] = dict(sorted(packages.items()))

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"  ✅ Added {len(missing)} plugins to release-please-config.json:")
    for plugin in sorted(missing):
        print(f"      - {plugin}")
    return True


def update_pr_labeler(repo_root: Path, plugins: Set[str]) -> bool:
    """Update .github/pr_labeler.yaml with missing plugins."""
    labeler_path = repo_root / ".github" / "pr_labeler.yaml"

    if labeler_path.exists():
        content = labeler_path.read_text()
    else:
        content = """# PR Labeler configuration
# Labels PRs based on which plugin directories have changes
# Used by CI to determine which plugins to build and test

"""

    # Find existing plugins
    existing_plugins = set()
    for match in re.finditer(r"^(sam-[\w-]+):", content, re.MULTILINE):
        existing_plugins.add(match.group(1))

    missing = plugins - existing_plugins
    if not missing:
        print("  ✅ pr_labeler.yaml already has all plugins")
        return False

    # Add missing plugins at the end
    new_entries = []
    for plugin in sorted(missing):
        new_entries.append(f"""
{plugin}:
  - changed-files:
      - any-glob-to-any-file: {plugin}/**
""")

    content = content.rstrip() + "\n" + "".join(new_entries)

    labeler_path.write_text(content)

    print(f"  ✅ Added {len(missing)} plugins to pr_labeler.yaml:")
    for plugin in sorted(missing):
        print(f"      - {plugin}")
    return True


def main():
    # Find repository root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    print(f"Repository root: {repo_root}")
    print()

    # Get all plugin directories
    actual_plugins = get_plugin_directories(repo_root)
    print(f"Found {len(actual_plugins)} plugin directories:")
    for plugin in sorted(actual_plugins):
        print(f"  - {plugin}")
    print()

    # Update each config file
    updated_any = False

    print("Updating build-plugin.yaml...")
    if update_build_workflow(repo_root, actual_plugins):
        updated_any = True
    print()

    print("Updating .release-please-manifest.json...")
    if update_manifest(repo_root, actual_plugins):
        updated_any = True
    print()

    print("Updating release-please-config.json...")
    if update_release_config(repo_root, actual_plugins):
        updated_any = True
    print()

    print("Updating pr_labeler.yaml...")
    if update_pr_labeler(repo_root, actual_plugins):
        updated_any = True
    print()

    # Summary
    if updated_any:
        print("✅ Configuration files have been updated!")
        print("   Please review the changes and commit them.")
    else:
        print("✅ All configuration files are already up to date!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
