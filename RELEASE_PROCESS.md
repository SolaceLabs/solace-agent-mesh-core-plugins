# Release Process

This document describes the complete release process for the solace-agent-mesh-core-plugins repository, from PR creation through package publication to PyPI.

## Overview

This is a multi-package Python monorepo using Release-Please for automated versioning and release management. Each plugin can be released independently with its own version number.

## Process Flow

```
Pull Request → Merge to main → Release-Please PR → Merge Release PR → Publish to PyPI
    ↓              ↓                    ↓                   ↓               ↓
  CI Checks    CI Checks        Release Readiness     Creates Release   FOSSA + Publish
```

---

## Phase 1: Pull Request (Feature/Fix Development)

### What Happens

When you open a PR against the `main` branch, the **CI workflow** (`.github/workflows/ci.yaml`) runs automatically.

### Checks and Gates

#### 1. Conventional Commit Validation
- **Check**: PR title must follow conventional commit format
- **Allowed types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `deps`, `revert`
- **Example**: `feat(sam-slack): add message threading support`
- **Gate**: ❌ BLOCKS merge if invalid

#### 2. Changed Plugin Detection
- Automatically detects which plugins have changed files
- Uses git diff to compare PR against base branch
- Scans for directories matching `sam-*` pattern

#### 3. Plugin Build & Test (per changed plugin)
Workflow: `.github/workflows/build-plugin.yaml`

For each changed plugin:
- **Install dependencies** using uv/hatch
- **Run unit tests** with pytest (Python 3.13)
- **Generate coverage report** (if pytest-cov available)
- **Run SonarQube scan** with quality gate check
  - Scans code quality, security hotspots, coverage
  - **Gate**: ⚠️ ADVISORY - Reports status but doesn't block
- **Build package** (wheel + sdist)
- **Verify package** with twine
- **Upload artifacts** for 7-day retention

**Note**: FOSSA scans are SKIPPED at plugin level on PRs.

#### 4. SonarQube Quality Gate Aggregation
- Collects quality gate results from all changed plugins
- Creates single aggregate check run: "SonarQube Quality Gate"
- Posts PR comment with status table for each plugin
- **Gate**: ❌ BLOCKS merge if any plugin fails quality gate

#### 5. FOSSA Scan (Repository-Level)
Workflow: `SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml`

- Scans the **entire repository** (not individual plugins)
- Uses root `.fossa.yml` configuration
- Checks for:
  - License policy violations
  - Security vulnerabilities in dependencies
- **Gate**: ❌ BLOCKS merge if violations found

#### 6. CI Status Check
- Aggregates all job results
- **Gate**: ❌ BLOCKS merge if any check fails
- Must pass:
  - Plugin builds
  - SonarQube quality gates
  - FOSSA repository scan

### Required Status Checks

Before merge, the following must pass:
- ✅ Conventional Commit Validation
- ✅ Plugin Builds (all changed plugins)
- ✅ SonarQube Quality Gate (aggregate)
- ✅ FOSSA Scan (repository-level)
- ✅ CI Status (aggregate)

---

## Phase 2: Merge to Main

### What Happens

When a PR is merged to `main`:
1. Same CI checks run again on the merged commit
2. **Release-Please workflow** is triggered (`.github/workflows/release-please.yaml`)

### Release-Please Behavior

Release-Please:
- Analyzes commit history since last release
- Determines which plugins need version bumps based on conventional commits:
  - `feat:` → minor version bump (0.1.0 → 0.2.0)
  - `fix:` → patch version bump (0.1.0 → 0.1.1)
  - `feat!:` or `BREAKING CHANGE:` → major version bump
- Creates/updates a **single consolidated Release PR** for all changed plugins
- Updates version numbers in `pyproject.toml` for affected plugins
- Generates/updates `CHANGELOG.md` for each affected plugin
- Updates `.release-please-manifest.json` with new versions

### Release PR Branch
- Branch name: `release-please--branches--main`
- PR title: `chore: release ${branch}`
- Contains version bumps for **all plugins** with changes since last release

---

## Phase 3: Release-Please PR (Release Readiness)

### What Happens

When Release-Please creates or updates the release PR, the **Release Readiness Check workflow** (`.github/workflows/release-readiness-check.yaml`) runs automatically.

### Checks and Gates

#### 1. Extract Plugins Being Released
- Compares release branch against `main`
- Identifies which plugins have changes
- Creates matrix for parallel checks

#### 2. SonarQube Hotspot Check (per plugin)
For each plugin being released:
- Queries SonarQube API for HIGH vulnerability hotspots
- Creates individual check run: `SonarQube: {plugin}`
- **Gate**: ❌ BLOCKS merge if HIGH vulnerabilities found
- **Purpose**: Ensures no critical security issues before release

#### 3. FOSSA Security Scan (Repository-Level)
Workflow: `SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml`

- Scans the release branch
- Uses root `.fossa.yml` configuration
- Checks for:
  - License policy violations (BLOCK mode)
  - Security vulnerabilities (REPORT mode)
- **Gate**: ❌ BLOCKS merge if license policy violations found
- **Gate**: ❌ BLOCKS merge if security vulnerabilities found

#### 4. Release Readiness Report
- Aggregates all security check results
- Creates check run: "Release Readiness"
- Posts PR comment with summary table
- **Gate**: ❌ Overall check BLOCKS merge if any critical check fails

### Required Status Checks for Release PR

Before merging the Release PR:
- ✅ SonarQube Hotspot Checks (all plugins)
- ✅ FOSSA Security Scan (repository-level)
- ✅ Release Readiness (aggregate)

---

## Phase 4: Merge Release PR (Create Releases)

### What Happens

When you merge the Release-Please PR:

1. **Release-Please creates GitHub Releases** for each plugin
   - Release tag format: `{plugin-name}-v{version}` (without 'v' prefix)
   - Example: `sam-slack-v0.3.0`, `sam-mongodb-v0.1.5`
   - Each release is tagged at the merge commit
   - Release notes are generated from changelog

2. **Publish workflow triggers** for each release (`.github/workflows/publish.yaml`)

---

## Phase 5: Publish to PyPI

Workflow: `.github/workflows/publish.yaml`

Triggered by: `release: [published]` event for each plugin release

### Process Steps

#### 1. Extract Package Metadata
- Parses release tag to extract plugin name and version
- Example: `sam-slack-v0.3.0` → plugin: `sam-slack`, version: `0.3.0`
- Verifies plugin directory exists
- Checks out the release tag

#### 2. Build Package
- Sets up Python 3.12
- Installs hatch and twine
- Builds wheel and source distribution
- Verifies package version matches release tag
- Runs twine check for package validity

#### 3. Publish to PyPI
- Uses PyPI Trusted Publishing (OIDC)
- Requires `pypi` environment configured in GitHub
- **Gate**: ❌ Cannot proceed if environment protection rules not met
- Uploads wheel and sdist to PyPI

#### 4. Update GitHub Release
- Attaches build artifacts (wheel + sdist) to the GitHub Release
- Creates workflow summary with:
  - Package name and version
  - Build artifacts list

#### 5. FOSSA Scan (Plugin-Specific - Version Recording)
Workflow: `SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml`

**VERSION RECORDING - Runs AFTER publishing**
- Scans the **specific plugin that was just released**
- Uses plugin-specific `.fossa.yml` configuration from `{plugin}/.fossa.yml`
- Uses plugin-specific workflow config from `{plugin}/workflow-config.json`
- Sets FOSSA revision to the **version number** (not git SHA)
  - This ensures FOSSA tracks releases by version
  - Example: revision = `0.3.0` (not a commit SHA)
- Mode configuration:
  - License policy: REPORT mode (non-blocking, already validated in Release PR)
  - Security vulnerabilities: REPORT mode (non-blocking, package already published)
- **Gate**: ⚠️ NON-BLOCKING - Runs after publish for tracking only
- **Purpose**: Record the release version in FOSSA for tracking and audit trail (fire and forget)

**Why FOSSA Runs After Publishing (Fire and Forget):**
- **License policy and vulnerability validation** already happened in Release-Please PR (BLOCKING gate)
- Running AFTER publish expedites time to get package on PyPI
- Package is already published to PyPI - can't be taken back, so no point blocking
- Records the specific plugin version in FOSSA for tracking and compliance audit trail
- REPORT mode for both policy and vulnerabilities - purely for visibility/tracking
- Uses plugin-specific configuration for accurate per-plugin tracking

### Required Gates for Publishing

- ✅ Package builds successfully
- ✅ Package passes twine checks
- ✅ PyPI environment protection rules (if configured)

### Post-Publish Tracking

- ⚠️ FOSSA scan (runs AFTER publish completes - non-blocking)
  - License policy: REPORT mode (non-blocking, already validated in Release PR)
  - Vulnerabilities: REPORT mode (non-blocking, package already published)
  - Primary purpose: Record version in FOSSA for tracking and audit trail

**Note**: FOSSA scan runs AFTER publishing in "fire and forget" mode to expedite getting packages on PyPI. All security validation happened in Release-Please PR. This scan is purely for tracking - package is already public.

---

## Configuration Files

### Release-Please Configuration

**`.release-please-config.json`**
- Defines release strategy for all plugins
- Configuration:
  - `release-type: python` - Python package versioning
  - `include-component-in-tag: true` - Tags include plugin name
  - `include-v-in-tag: false` - Tags use `plugin-v1.0.0` format (not `plugin-vv1.0.0`)
  - `separate-pull-requests: false` - Single PR for all releases
  - `bump-minor-pre-major: true` - Allow minor bumps before 1.0.0
- Lists all 17 plugins with their package names

**`.release-please-manifest.json`**
- Tracks current version for each plugin
- Updated automatically by Release-Please

### FOSSA Configuration

**Repository-level**: `.fossa.yml` (root)
- Used for PR scans and Release-Please PR scans
- Scans entire repository

**Plugin-level**: `{plugin}/.fossa.yml`
- Used for plugin-specific scans during publishing
- Each plugin can have custom configuration

**Workflow config**: `{plugin}/workflow-config.json`
- Contains plugin-specific FOSSA project settings
- Used during publish workflow

### GitHub Branch Protection (Recommended)

For `main` branch:
- Require PR before merging
- Require status checks:
  - CI Status
  - SonarQube Quality Gate
  - FOSSA Scan

For Release-Please PR:
- Require status checks:
  - Release Readiness
  - SonarQube hotspot checks
  - FOSSA Security Scan

---

## Release Tag Format

Tags follow the pattern: `{plugin-name}-v{version}`

Examples:
- `sam-slack-v0.3.0`
- `sam-mongodb-v0.1.5`
- `sam-rest-gateway-v0.2.0`

**Note**: The tag includes a 'v' prefix (e.g., `-v0.3.0`), but Release-Please config has `include-v-in-tag: false`, meaning the version component itself doesn't get an extra 'v'.

---

## Summary of Gates

| Stage | Gate Type | What Blocks |
|-------|-----------|-------------|
| **Pull Request** | ❌ BLOCKING | - Invalid conventional commit format<br>- Plugin build failures<br>- SonarQube quality gate failures<br>- FOSSA repository-level violations |
| **Release PR** | ❌ BLOCKING | - SonarQube HIGH vulnerability hotspots<br>- FOSSA license policy violations |
| **Publishing** | ❌ BLOCKING | - Package build failures<br>- PyPI environment protection |

**Note**: FOSSA scan runs AFTER publishing for version tracking only (non-blocking).

---

## What Gets Scanned When

| Stage | FOSSA Scope | Configuration | Policy Mode | Vuln Mode | Purpose |
|-------|-------------|---------------|-------------|-----------|---------|
| **PR (ci.yaml)** | Repository-level | `.fossa.yml` (root) | BLOCK | BLOCK | Catch issues early, prevent bad code in main |
| **Release PR** | Repository-level | `.fossa.yml` (root) | BLOCK | BLOCK | Validate release branch before merge (GATE) |
| **Per-Plugin Build** | Plugin-level (main branch only) | `{plugin}/.fossa.yml` | BLOCK | BLOCK | Track individual plugin health (not on PRs) |
| **Publishing** | Plugin-level | `{plugin}/.fossa.yml` | REPORT | REPORT | Record release version (runs AFTER publish, fire and forget) |

**Key**:
- Policy Mode: License policy enforcement
- Vuln Mode: Vulnerability checking
- BLOCK = Fails workflow if violations found
- REPORT = Logs findings but doesn't block

---

## Manual Release Process (if needed)

### Manually Trigger Release Readiness Check
```bash
# Go to Actions → Release Readiness Check → Run workflow
# Specify:
# - pr_number: (optional) PR number to comment on
# - ref: release-please--branches--main (or specific SHA)
```

### Manually Create Release
```bash
# If Release-Please didn't create a release automatically:
gh release create {plugin-name}-v{version} --title "{plugin-name} v{version}" --notes "Release notes here"
```

---

## Troubleshooting

### Release PR not created
- Check that commits follow conventional commit format
- Verify commits are on main branch
- Check Release-Please workflow run logs

### Publishing failed
- Check FOSSA scan results in workflow logs
- Verify PyPI trusted publisher is configured
- Check that release tag matches expected format

### FOSSA blocking release
- Review violations in FOSSA dashboard
- Update dependencies or request policy exemption
- Re-run FOSSA scan after fixes

---

## Key Workflows Summary

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yaml` | PR + push to main | Build, test, quality checks, repository FOSSA scan |
| `build-plugin.yaml` | Called by ci.yaml | Per-plugin build, test, quality checks |
| `release-please.yaml` | Push to main | Create/update release PR |
| `release-readiness-check.yaml` | Release PR created/updated | Security validation before release |
| `publish.yaml` | GitHub release published | FOSSA scan + publish to PyPI |

---

## Contact

For questions about the release process, contact the repository maintainers.
