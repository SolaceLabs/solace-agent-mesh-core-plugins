#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
WORKSPACE_ROOT="$(cd "$REPO_ROOT/../.." && pwd -P)"
LIST_FILE="${1:-"$WORKSPACE_ROOT/test.txt"}"
INNER_SCRIPT="$SCRIPT_DIR/test_trusted_publishing_releases.sh"
MANIFEST_PATH="$REPO_ROOT/.release-please-manifest.json"
CONFIG_PATH="$REPO_ROOT/release-please-config.json"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 1
  fi
}

require_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    echo "Required file not found: $file_path" >&2
    exit 1
  fi
}

load_plugins() {
  local list_file="$1"
  sed -e 's/[[:space:]]*$//' "$list_file" \
    | awk 'NF && $0 !~ /^[[:space:]]*#/'
}

resolve_release_tag() {
  local plugin="$1"
  local package_name
  local version

  package_name="$(jq -r --arg plugin "$plugin" '.packages[$plugin]["package-name"] // empty' "$CONFIG_PATH")"
  version="$(jq -r --arg plugin "$plugin" '.[$plugin] // empty' "$MANIFEST_PATH")"

  if [[ -z "$package_name" || -z "$version" ]]; then
    echo "Could not resolve package-name/version for plugin '$plugin'." >&2
    exit 1
  fi

  printf '%s-%s\n' "$package_name" "$version"
}

main() {
  require_command gh
  require_command jq
  require_command awk
  require_command sed
  require_file "$LIST_FILE"
  require_file "$INNER_SCRIPT"
  require_file "$MANIFEST_PATH"
  require_file "$CONFIG_PATH"

  mapfile -t plugins < <(load_plugins "$LIST_FILE")

  if [[ ${#plugins[@]} -eq 0 ]]; then
    echo "No plugins found in list: $LIST_FILE"
    exit 0
  fi

  echo "Using plugin list: $LIST_FILE"
  echo "Repository root: $REPO_ROOT"
  echo "Plugins to process: ${plugins[*]}"
  echo

  for plugin in "${plugins[@]}"; do
    local answer
    local tag

    if [[ ! -d "$REPO_ROOT/$plugin" ]]; then
      echo "Plugin directory not found: $REPO_ROOT/$plugin" >&2
      exit 1
    fi

    echo "============================================================"
    echo "Next plugin: $plugin"
    read -r -p "Have you added the trusted publisher for '$plugin'? Continue Y/N " answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
      echo "Stopping before running '$plugin'."
      exit 0
    fi

    (
      cd "$REPO_ROOT"
      "$INNER_SCRIPT" "$plugin"
    )

    tag="$(resolve_release_tag "$plugin")"
    if gh release view "$tag" --repo "$(gh repo view --json nameWithOwner -q .nameWithOwner)" >/dev/null 2>&1; then
      echo "Release '$tag' still exists. Stopping so it can be inspected."
      exit 0
    fi
  done

  echo "Finished processing all listed plugins."
}

main "$@"
