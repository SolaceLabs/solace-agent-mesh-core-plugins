# GitHub Scripts

Utility scripts used by CI workflows.

## `ensure_test_dependencies.sh`

Used by `build-plugin.yaml` to ensure the Hatch test environment has required test tooling before running tests.

### Inputs (environment variables)

- `HATCH_TEST_ENV` (default: `hatch-test`)

### Behavior

- Runs `pip list --format json` inside the Hatch test environment.
- Checks for required packages:
  - `pytest`
  - `pytest-cov>=4.0.0`
  - `pytest-json-ctrf>=0.1.0`
- Installs only the missing packages via `pip install`.

## `resolve_changed_plugins.py`

Used by `ci.yaml` (`label-pr` job) to resolve changed plugins and generate matrix JSON in one step.

### Inputs (environment variables)

- `EVENT_NAME` (`pull_request` or `push`)
- `PR_BASE_SHA` (for PR diff mode)
- `PR_HEAD_SHA` (for PR diff mode)
- `PR_NUMBER` (for PR workflows)
- `GITHUB_OUTPUT` (provided by GitHub Actions)

### Outputs (written to `GITHUB_OUTPUT`)

- `plugins`: comma-separated changed plugin names after deprecated filtering
- `all_plugins`: JSON array for matrix include (for example `[{"plugin_directory":"sam-rag"}]`)
- `pr_number`: PR number for pull_request events, empty for push events

### Behavior

- Resolves changed files from PR base/head SHAs or from `HEAD~1..HEAD` on push.
- Detects top-level `sam-*` plugin directories from changed files.
- Filters deprecated plugins using `.github/scripts/plugin_exceptions.py`.
- Emits both CSV and matrix JSON outputs for downstream jobs.

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
