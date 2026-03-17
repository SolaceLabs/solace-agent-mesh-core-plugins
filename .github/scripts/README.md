# GitHub Scripts

Utility scripts used by CI workflows.

## `collect_ctrf_reports.py`

Used by `ci.yaml` (`ci-status` job) to collect CTRF reports from project CI payloads.

### Inputs (environment variables)

- `RESULTS_DIR` (default: `ci-plugin-results`)
- `OUTPUT_DIR` (default: `ctrf-plugin-reports`)
- `GITHUB_OUTPUT` (provided by GitHub Actions)

### Outputs (written to `GITHUB_OUTPUT`)

- `count`: number of collected CTRF reports
- `has_reports`: `true` when at least one CTRF report was collected

### Behavior

- Reads all JSON payloads under `RESULTS_DIR`.
- Accepts project identity from `project` (preferred) or `plugin` (backward compatibility).
- Extracts `unit_test_report` only when it is a valid CTRF object with `results`.
- Writes one CTRF file per project into `OUTPUT_DIR` (`<project>.json`).

## `resolve_fossa_target.py`

Used by `build-plugin.yaml` to resolve FOSSA scan target values for a plugin build.

### Inputs (environment variables)

- `REF_HINT`
- `EVENT_NAME`
- `HEAD_REF`
- `DEFAULT_BRANCH`
- `CURRENT_REF_NAME`
- `BEFORE_SHA`
- `CURRENT_SHA`
- `PLUGIN_DIRECTORY`
- `PR_BASE_SHA`
- `GITHUB_WORKSPACE` (provided by GitHub Actions)

### Outputs (written to `GITHUB_OUTPUT`)

- `branch`
- `revision`
- `enable_diff_mode`
- `diff_base_revision_sha`

### Resolution behavior

- **Release-please PR**:
  - `branch=ReleasePleasePR`
  - `revision=<version from .release-please-manifest.json>` (fallback to `hatch version`, then SHA)
  - diff mode disabled
- **Regular PR**:
  - `branch=PR`
  - `revision=<head_ref>`
  - diff mode enabled with `diff_base_revision_sha=<pull_request.base.sha>`
- **Push to default branch**:
  - `branch=main`
  - if plugin version changed in `.release-please-manifest.json`, `revision=<new version>`, else `revision=<current sha>`
  - diff mode disabled
- **Other events/refs**:
  - `branch=<default branch>`
  - `revision=<current sha>`
  - diff mode disabled
