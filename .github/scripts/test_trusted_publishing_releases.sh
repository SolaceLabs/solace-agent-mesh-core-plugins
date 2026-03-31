#!/usr/bin/env bash
set -euo pipefail

RUN_DIR="$(pwd -P)"
MANIFEST_PATH="$RUN_DIR/.release-please-manifest.json"
CONFIG_PATH="$RUN_DIR/release-please-config.json"
WORKFLOW_FILE="publish.yaml"
RELEASE_WORKFLOW_FILE="release.yaml"
TARGET_COMMIT="${TARGET_COMMIT:-main}"

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

resolve_plugins() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
    return
  fi

  jq -r 'keys_unsorted[]' "$MANIFEST_PATH"
}

release_exists() {
  local repo="$1"
  local tag="$2"
  gh release view "$tag" --repo "$repo" >/dev/null 2>&1
}

wait_for_run_id() {
  local repo="$1"
  local workflow_file="$2"
  local event_name="$3"
  local start_iso="$4"
  local run_id=""
  local attempts=0

  echo "Waiting for workflow '$workflow_file' ($event_name) to start..." >&2
  while [[ -z "$run_id" ]]; do
    attempts=$((attempts + 1))
    run_id="$(
      gh run list \
        --repo "$repo" \
        --workflow "$workflow_file" \
        --event "$event_name" \
        --limit 20 \
        --json databaseId,createdAt \
      | jq -r --arg start "$start_iso" '
          map(select(.createdAt >= $start))
          | .[0].databaseId // empty
        '
    )"

    if [[ -z "$run_id" ]]; then
      printf '.' >&2
      if (( attempts >= 60 )); then
        echo >&2
        echo "Timed out waiting for workflow '$workflow_file' ($event_name) to start." >&2
        exit 1
      fi
      sleep 5
    fi
  done

  echo >&2
  printf '%s\n' "$run_id"
}

watch_run() {
  local repo="$1"
  local run_id="$2"
  local run_url
  local conclusion

  run_url="$(gh run view "$run_id" --repo "$repo" --json url -q .url)"
  echo "Watching workflow run: $run_url"

  if gh run watch "$run_id" --repo "$repo" --interval 10 --exit-status; then
    conclusion="success"
  else
    conclusion="$(gh run view "$run_id" --repo "$repo" --json conclusion -q .conclusion)"
  fi

  echo "Workflow conclusion: $conclusion"
}

get_run_conclusion() {
  local repo="$1"
  local run_id="$2"
  gh run view "$run_id" --repo "$repo" --json conclusion -q .conclusion
}

delete_temp_release() {
  local repo="$1"
  local tag="$2"
  echo "Deleting temporary release: $tag"
  gh release delete "$tag" --repo "$repo" --cleanup-tag --yes
}

main() {
  require_command gh
  require_command jq
  require_file "$MANIFEST_PATH"
  require_file "$CONFIG_PATH"

  local repo
  repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

  mapfile -t plugins < <(resolve_plugins "$@")

  if [[ ${#plugins[@]} -eq 0 ]]; then
    echo "No plugins selected."
    exit 0
  fi

  echo "Repository: $repo"
  echo "Workflow: $WORKFLOW_FILE"
  echo "Dispatch workflow: $RELEASE_WORKFLOW_FILE"
  echo "Target commit: $TARGET_COMMIT"
  echo "Plugins to test: ${plugins[*]}"
  echo

  for plugin in "${plugins[@]}"; do
    local package_name
    local version
    local tag
    local start_iso
    local publish_run_id
    local release_run_id
    local publish_conclusion
    local release_conclusion=""
    local should_delete="false"
    local answer

    package_name="$(jq -r --arg plugin "$plugin" '.packages[$plugin]["package-name"] // empty' "$CONFIG_PATH")"
    version="$(jq -r --arg plugin "$plugin" '.[$plugin] // empty' "$MANIFEST_PATH")"

    if [[ -z "$package_name" || -z "$version" ]]; then
      echo "Skipping '$plugin': missing package-name or version in config/manifest." >&2
      continue
    fi

    tag="${package_name}-${version}"

    echo "============================================================"
    echo "Plugin: $plugin"
    echo "Package name: $package_name"
    echo "Version: $version"
    echo "Release tag: $tag"

    if release_exists "$repo" "$tag"; then
      echo "Release already exists for tag '$tag'. Delete it manually or choose another plugin/version." >&2
      exit 1
    fi

    start_iso="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    gh release create "$tag" \
      --repo "$repo" \
      --target "$TARGET_COMMIT" \
      --title "$tag" \
      --notes "Temporary trusted publishing smoke test for $plugin"

    echo "Created temporary release: $tag"

    publish_run_id="$(wait_for_run_id "$repo" "$WORKFLOW_FILE" "release" "$start_iso")"
    watch_run "$repo" "$publish_run_id"
    publish_conclusion="$(get_run_conclusion "$repo" "$publish_run_id")"

    if [[ "$publish_conclusion" != "success" ]]; then
      echo "Publish workflow did not succeed; skipping release workflow wait."
    else
      release_run_id="$(wait_for_run_id "$repo" "$RELEASE_WORKFLOW_FILE" "workflow_dispatch" "$start_iso")"
      watch_run "$repo" "$release_run_id"
      release_conclusion="$(get_run_conclusion "$repo" "$release_run_id")"
    fi

    if [[ "$publish_conclusion" == "success" && "$release_conclusion" == "success" ]]; then
      echo "Both workflows succeeded for $plugin."
    else
      echo "One or more workflows failed for $plugin."
      echo "  publish.yaml: ${publish_conclusion:-unknown}"
      if [[ -n "$release_conclusion" ]]; then
        echo "  release.yaml: $release_conclusion"
      else
        echo "  release.yaml: not started"
      fi
    fi

    read -r -p "Continue Y/N " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
      should_delete="true"
    fi

    if [[ "$should_delete" == "true" ]]; then
      delete_temp_release "$repo" "$tag"
      echo
      continue
    fi

    echo "Stopping. Keeping release '$tag' for inspection."
    exit 0
  done

  echo "Finished processing all selected plugins."
}

main "$@"
