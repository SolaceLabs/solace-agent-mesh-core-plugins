#!/usr/bin/env python3
"""
Deprecate active plugins across tracked configuration files.

This script removes selected plugins from release/build/label tracking and
adds them to the shared deprecated plugin exceptions list. It also rewrites
the deprecation workflow's checkbox inputs so already-deprecated plugins are
not offered again.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Sequence, Set

from plugin_exceptions import DEPRECATED_PLUGINS

GITHUB_PATH = Path(".github")
WORKFLOWS_PATH = GITHUB_PATH / "workflows"
SCRIPTS_PATH = GITHUB_PATH / "scripts"

AUTO_INPUTS_START = "      # BEGIN AUTO-GENERATED PLUGIN INPUTS"
AUTO_INPUTS_END = "      # END AUTO-GENERATED PLUGIN INPUTS"


def get_plugin_directories(repo_root: Path) -> Set[str]:
    """Get all plugin directories (directories starting with 'sam-')."""
    plugins = set()
    for item in repo_root.iterdir():
        if item.is_dir() and item.name.startswith("sam-") and (item / "pyproject.toml").exists():
            plugins.add(item.name)
    return plugins


def _is_truthy(value: object) -> bool:
    return value is True or str(value).strip().lower() == "true"


def resolve_selected_plugins(args: Sequence[str]) -> list[str]:
    """Resolve selected plugins from CLI args or workflow inputs JSON."""
    selected = sorted({plugin.strip() for plugin in args if plugin.strip()})
    if selected:
        return selected

    raw_inputs = os.getenv("WORKFLOW_INPUTS_JSON", "").strip()
    if not raw_inputs:
        raise SystemExit(
            "No plugins selected. Pass plugin names as arguments or set WORKFLOW_INPUTS_JSON."
        )

    try:
        payload = json.loads(raw_inputs)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid WORKFLOW_INPUTS_JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise SystemExit("WORKFLOW_INPUTS_JSON must decode to an object.")

    selected = sorted(
        plugin
        for plugin, enabled in payload.items()
        if plugin.startswith("sam-") and _is_truthy(enabled)
    )
    if not selected:
        raise SystemExit("No plugins selected. Choose at least one active plugin to deprecate.")
    return selected


def write_deprecated_plugins(repo_root: Path, deprecated_plugins: Set[str]) -> None:
    """Rewrite the shared deprecated plugin set with sorted entries."""
    exceptions_path = repo_root / SCRIPTS_PATH / "plugin_exceptions.py"
    entries = "\n".join(f'    "{plugin}",' for plugin in sorted(deprecated_plugins))
    content = f"""#!/usr/bin/env python3
\"\"\"
Shared plugin exceptions for synchronization/validation scripts.
\"\"\"

from __future__ import annotations

# Plugins that still exist in the repository but should not be auto-managed
# in release/config synchronization files.
DEPRECATED_PLUGINS = {{
{entries}
}}
"""
    exceptions_path.write_text(content, encoding="utf-8")


def _remove_plugins_from_build_options(content: str, removed_plugins: Set[str]) -> str:
    pattern = re.compile(
        r"(^  workflow_dispatch:\n.*?^      plugin_directory:\n.*?^        options:\n)"
        r"(?P<options>(?:^          -\s*sam-[\w-]+\n)+)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        raise SystemExit(
            "Could not locate workflow_dispatch.plugin_directory.options in build-plugin.yaml."
        )

    filtered_lines = []
    for line in match.group("options").splitlines(keepends=True):
        option_match = re.match(r"^\s*-\s*(sam-[\w-]+)\s*$", line)
        if option_match and option_match.group(1) in removed_plugins:
            continue
        filtered_lines.append(line)

    if not filtered_lines:
        raise SystemExit("build-plugin.yaml cannot be left without any plugin choices.")

    return (
        content[: match.start("options")]
        + "".join(filtered_lines)
        + content[match.end("options") :]
    )


def update_build_workflow(repo_root: Path, removed_plugins: Set[str]) -> None:
    """Remove deprecated plugins from build-plugin workflow dispatch options."""
    workflow_path = repo_root / WORKFLOWS_PATH / "build-plugin.yaml"
    content = workflow_path.read_text(encoding="utf-8")
    workflow_path.write_text(
        _remove_plugins_from_build_options(content, removed_plugins),
        encoding="utf-8",
    )


def update_manifest(repo_root: Path, removed_plugins: Set[str]) -> None:
    """Remove deprecated plugins from .release-please-manifest.json."""
    manifest_path = repo_root / ".release-please-manifest.json"
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)

    for plugin in removed_plugins:
        manifest.pop(plugin, None)

    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(dict(sorted(manifest.items())), handle, indent=2)
        handle.write("\n")


def update_release_config(repo_root: Path, removed_plugins: Set[str]) -> None:
    """Remove deprecated plugins from release-please-config.json."""
    config_path = repo_root / "release-please-config.json"
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    packages = config.get("packages", {})
    for plugin in removed_plugins:
        packages.pop(plugin, None)
    config["packages"] = dict(sorted(packages.items()))

    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")


def update_pr_labeler(repo_root: Path, removed_plugins: Set[str]) -> None:
    """Remove deprecated plugins from PR labeler rules."""
    labeler_path = repo_root / GITHUB_PATH / "pr_labeler.yaml"
    lines = labeler_path.read_text(encoding="utf-8").splitlines()

    header: list[str] = []
    index = 0
    while index < len(lines) and not re.match(r"^(sam-[\w-]+):\s*$", lines[index]):
        header.append(lines[index])
        index += 1

    blocks: list[tuple[str, list[str]]] = []
    current_plugin = ""
    current_block: list[str] = []

    for line in lines[index:]:
        match = re.match(r"^(sam-[\w-]+):\s*$", line)
        if match:
            if current_plugin:
                blocks.append((current_plugin, current_block))
            current_plugin = match.group(1)
            current_block = [line]
        else:
            current_block.append(line)

    if current_plugin:
        blocks.append((current_plugin, current_block))

    updated_lines = list(header)
    for plugin, block in blocks:
        if plugin not in removed_plugins:
            updated_lines.extend(block)

    labeler_path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


def render_deprecate_workflow_inputs(plugins: Set[str]) -> str:
    """Render the managed checkbox inputs block for the deprecation workflow."""
    lines = [AUTO_INPUTS_START]
    if plugins:
        for plugin in sorted(plugins):
            lines.extend(
                [
                    f"      {plugin}:",
                    f'        description: "Deprecate {plugin}"',
                    "        required: false",
                    "        type: boolean",
                    "        default: false",
                ]
            )
    else:
        lines.append("      # No active plugins remain.")
    lines.append(AUTO_INPUTS_END)
    return "\n".join(lines)


def update_deprecate_workflow(repo_root: Path, active_plugins: Set[str]) -> None:
    """Refresh the deprecation workflow inputs to match active plugins."""
    workflow_path = repo_root / WORKFLOWS_PATH / "deprecate-plugins.yaml"
    content = workflow_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"{re.escape(AUTO_INPUTS_START)}\n.*?\n{re.escape(AUTO_INPUTS_END)}",
        re.DOTALL,
    )
    replacement = render_deprecate_workflow_inputs(active_plugins)
    updated_content, count = pattern.subn(replacement, content, count=1)
    if count != 1:
        raise SystemExit(
            "Could not locate the managed plugin inputs block in deprecate-plugins.yaml."
        )
    workflow_path.write_text(updated_content, encoding="utf-8")


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent

    selected_plugins = resolve_selected_plugins(sys.argv[1:])
    selected_set = set(selected_plugins)

    all_plugins = get_plugin_directories(repo_root)
    active_plugins = all_plugins - DEPRECATED_PLUGINS

    unknown_plugins = sorted(selected_set - all_plugins)
    if unknown_plugins:
        print("Unknown plugin directories:")
        for plugin in unknown_plugins:
            print(f"  - {plugin}")
        return 1

    already_deprecated = sorted(selected_set & DEPRECATED_PLUGINS)
    if already_deprecated:
        print("Plugins are already deprecated and cannot be selected again:")
        for plugin in already_deprecated:
            print(f"  - {plugin}")
        return 1

    invalid_selection = sorted(selected_set - active_plugins)
    if invalid_selection:
        print("Selected plugins are not active plugins:")
        for plugin in invalid_selection:
            print(f"  - {plugin}")
        return 1

    updated_deprecated_plugins = set(DEPRECATED_PLUGINS) | selected_set
    active_plugins_after_update = all_plugins - updated_deprecated_plugins

    update_build_workflow(repo_root, selected_set)
    update_manifest(repo_root, selected_set)
    update_release_config(repo_root, selected_set)
    update_pr_labeler(repo_root, selected_set)
    write_deprecated_plugins(repo_root, updated_deprecated_plugins)
    update_deprecate_workflow(repo_root, active_plugins_after_update)

    print(f"Deprecated {len(selected_plugins)} plugin(s):")
    for plugin in selected_plugins:
        print(f"  - {plugin}")

    print()
    print("Updated files:")
    print("  - .github/workflows/build-plugin.yaml")
    print("  - .github/workflows/deprecate-plugins.yaml")
    print("  - .github/pr_labeler.yaml")
    print("  - .github/scripts/plugin_exceptions.py")
    print("  - .release-please-manifest.json")
    print("  - release-please-config.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
