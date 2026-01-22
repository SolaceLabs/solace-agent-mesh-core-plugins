#!/usr/bin/env python3
"""
Add missing plugins to all configuration files.

This script scans the repository for plugin directories (sam-*) and adds
any missing plugins to:
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


def get_package_name(plugin_dir: str) -> str:
    """Convert plugin directory name to package name."""
    # sam-foo-bar -> solace_agent_mesh_foo_bar
    suffix = plugin_dir.replace("sam-", "").replace("-", "_")
    return f"solace_agent_mesh_{suffix}"


def update_build_workflow(repo_root: Path, plugins: Set[str]) -> bool:
    """Update .github/workflows/build-plugin.yaml with missing plugins."""
    workflow_path = repo_root / ".github" / "workflows" / "build-plugin.yaml"

    if not workflow_path.exists():
        print(f"  ⚠️  {workflow_path} does not exist, skipping")
        return False

    content = workflow_path.read_text()

    # Find existing plugins in options (lines like "          - sam-foo")
    existing_plugins = set()
    for match in re.finditer(r"^\s*-\s*(sam-[\w-]+)\s*$", content, re.MULTILINE):
        existing_plugins.add(match.group(1))

    missing = plugins - existing_plugins
    if not missing:
        print("  ✅ build-plugin.yaml already has all plugins")
        return False

    # Find the last plugin option and add after it
    lines = content.split("\n")
    last_option_idx = -1
    indent = "          "  # Default indent

    for i, line in enumerate(lines):
        match = re.match(r"^(\s*)-\s*sam-[\w-]+\s*$", line)
        if match:
            indent = match.group(1)
            last_option_idx = i

    if last_option_idx < 0:
        print("  ⚠️  Could not find options block in build-plugin.yaml")
        return False

    # Insert missing plugins after the last option
    for plugin in sorted(missing, reverse=True):
        lines.insert(last_option_idx + 1, f"{indent}- {plugin}")

    workflow_path.write_text("\n".join(lines))
    print(f"  ✅ Added {len(missing)} plugins to build-plugin.yaml:")
    for plugin in sorted(missing):
        print(f"      + {plugin}")
    return True


def update_sync_workflow(repo_root: Path, plugins: Set[str]) -> bool:
    """Update .github/workflows/sync-plugin-configs.yaml paths exclusions with missing plugins."""
    workflow_path = repo_root / ".github" / "workflows" / "sync-plugin-configs.yaml"

    if not workflow_path.exists():
        print(f"  ⚠️  {workflow_path} does not exist, skipping")
        return False

    content = workflow_path.read_text()

    # Find existing plugins in paths exclusions (! prefix)
    existing_plugins = set()
    for match in re.finditer(r'^\s*-\s*"!(sam-[\w-]+)/\*\*"', content, re.MULTILINE):
        existing_plugins.add(match.group(1))

    missing = plugins - existing_plugins
    if not missing:
        print("  ✅ sync-plugin-configs.yaml already has all plugins")
        return False

    # Find the last exclusion pattern (lines with "!sam-*/**") and add after it
    lines = content.split("\n")
    last_exclusion_idx = -1
    indent = "      "  # Default indent

    for i, line in enumerate(lines):
        match = re.match(r'^(\s*)-\s*"!sam-[\w-]+/\*\*"', line)
        if match:
            indent = match.group(1)
            last_exclusion_idx = i

    if last_exclusion_idx < 0:
        print("  ⚠️  Could not find paths exclusions in sync-plugin-configs.yaml")
        return False

    # Insert missing plugins after the last exclusion
    for plugin in sorted(missing, reverse=True):
        lines.insert(last_exclusion_idx + 1, f'{indent}- "!{plugin}/**"')

    workflow_path.write_text("\n".join(lines))
    print(f"  ✅ Added {len(missing)} plugins to sync-plugin-configs.yaml:")
    for plugin in sorted(missing):
        print(f"      + {plugin}")
    return True


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
        print(f"      + {plugin}")
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
        print(f"      + {plugin}")
    return True


def update_pr_labeler(repo_root: Path, plugins: Set[str]) -> bool:
    """Update .github/pr_labeler.yaml with missing plugins."""
    labeler_path = repo_root / ".github" / "pr_labeler.yaml"

    if labeler_path.exists():
        content = labeler_path.read_text()
    else:
        content = """# PR Labeler configuration
# This file automatically labels PRs based on changed files.

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
        new_entries.append(f"""{plugin}:
  - changed-files:
    - any-glob-to-any-file: {plugin}/**

""")

    content = content.rstrip() + "\n" + "".join(new_entries)

    labeler_path.write_text(content)

    print(f"  ✅ Added {len(missing)} plugins to pr_labeler.yaml:")
    for plugin in sorted(missing):
        print(f"      + {plugin}")
    return True


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

    # Update each config file
    updated_any = False

    print("Updating build-plugin.yaml...")
    if update_build_workflow(repo_root, actual_plugins):
        updated_any = True
    print()

    print("Updating sync-plugin-configs.yaml...")
    if update_sync_workflow(repo_root, actual_plugins):
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
        print("=" * 50)
        print("✅ Configuration files updated successfully!")
        print("   Please review the changes and commit them.")
    else:
        print("✅ All configuration files are already up to date!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
