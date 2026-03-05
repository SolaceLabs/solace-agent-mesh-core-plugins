# Release Tag Format Inconsistency - Findings

**Date**: 2026-03-04
**Status**: Investigation Complete
**Severity**: High - Will cause publish workflow failure

## Executive Summary

There is a critical mismatch between the release-please tag format configuration and the publish workflow expectations. This will cause the publish workflow to fail when release-please creates plugin releases.

## Current Configuration

### release-please-config.json

```json
{
  "release-type": "python",
  "include-component-in-tag": true,
  "include-v-in-tag": false,  // ⚠️ NO "v" prefix
  "separate-pull-requests": false
}
```

**Generated Tag Format**: `<component>-<version>`
**Example**: `sam-slack-0.2.1`, `sam-bedrock-agent-0.1.1`

### .github/workflows/publish.yaml (Lines 30-47)

```yaml
- name: Extract package path from release tag
  id: extract
  run: |
    # Release tag format: <package-name>-v<version>
    # Example: sam-slack-v0.3.0  // ⚠️ Expects "v" prefix
    TAG="${{ github.event.release.tag_name }}"

    # Extract package name (everything before -v followed by version number)
    PACKAGE_PATH=$(echo "$TAG" | sed 's/-v[0-9].*//')  // ⚠️ Looks for "-v"
    VERSION=$(echo "$TAG" | sed 's/.*-v//')            // ⚠️ Looks for "-v"
```

**Expected Tag Format**: `<package-name>-v<version>`
**Example**: `sam-slack-v0.3.0`

## The Problem

| Component | Tag Format | Configuration |
|-----------|-----------|---------------|
| **release-please** | `sam-slack-0.2.1` | `include-v-in-tag: false` |
| **publish.yaml** | `sam-slack-v0.2.1` | Hardcoded sed pattern `-v[0-9]` |

**Impact**: When release-please creates a release with tag `sam-slack-0.2.1`:
- The sed extraction `sed 's/-v[0-9].*//'` will NOT match
- `PACKAGE_PATH` will be the full tag: `sam-slack-0.2.1` (incorrect)
- `VERSION` will be the full tag: `sam-slack-0.2.1` (incorrect)
- Build and FOSSA steps will fail due to incorrect paths/versions

## Current Release State

### Existing Releases
- **Only one release exists**: `SAMv0.2.4` (manual, created 2025-06-10)
- **No per-plugin releases** have been created by release-please yet

### Pending Release-Please PR
- **Branch**: `release-please--branches--main`
- **Status**: Ready but not merged
- **Plugins with pending versions**:
  - `sam-slack`: 0.2.0 → 0.2.1
  - `sam-bedrock-agent`: 0.1.0 → 0.1.1
  - All 17 plugins have updates ready

### Git Tags
```bash
$ git tag --list
SAMv0.2.4  # Old manual tag
```

**No release-please tags exist yet** because the release PR hasn't been merged.

## Why This Hasn't Been Caught

1. **Release-please PR hasn't been merged yet**
   - No plugin releases have been created
   - The publish workflow has never been triggered by release-please

2. **Only manual release exists**
   - `SAMv0.2.4` was created manually
   - May have worked with manual tag creation

3. **Testing gap**
   - No test releases to validate the workflow end-to-end

## FOSSA Integration Impact

### Current FOSSA Configuration in publish.yaml

```yaml
fossa-scan:
  uses: SolaceDev/solace-public-workflows/.github/workflows/sca-scan-and-guard.yaml@main
  with:
    git_ref: ${{ needs.extract-metadata.outputs.full_tag }}  # Uses tag for checkout
    use_vault: false
    config_file: '${{ needs.extract-metadata.outputs.package_path }}/workflow-config.json'
    additional_scan_params: |
      fossa.config=${{ needs.extract-metadata.outputs.package_path }}/.fossa.yml
      fossa.revision=${{ needs.extract-metadata.outputs.version }}  # Version for FOSSA
```

### FOSSA Issues from Tag Mismatch

If tag extraction fails:
- ❌ `package_path` will be wrong → wrong `config_file` path
- ❌ `package_path` will be wrong → wrong `fossa.config` path
- ❌ `version` extraction fails → wrong `fossa.revision`
- ❌ `git_ref` might work but points to malformed tag

## Solution Options

### Option 1: Fix release-please Config (Add "v" Prefix)

**Change**: `release-please-config.json`
```json
{
  "include-v-in-tag": true  // Change from false to true
}
```

**Result**: Tags will be `sam-slack-v0.2.1`

**Pros**:
- ✅ Minimal code changes
- ✅ Matches publish.yaml expectations
- ✅ Common convention (many projects use "v" prefix)

**Cons**:
- ❌ Changes future tag format (breaks consistency if you prefer no "v")
- ❌ Need to decide if this is your preferred convention

---

### Option 2: Fix publish.yaml (Remove "v" Expectation)

**Change**: `.github/workflows/publish.yaml`
```yaml
# Update sed patterns to handle tags WITHOUT "v"
PACKAGE_PATH=$(echo "$TAG" | sed 's/-[0-9][0-9]*\.[0-9].*//')
VERSION=$(echo "$TAG" | sed 's/.*-\([0-9][0-9]*\.[0-9].*\)/\1/')
```

**Result**: Publish workflow accepts tags like `sam-slack-0.2.1`

**Pros**:
- ✅ Keeps existing release-please config
- ✅ No "v" prefix (cleaner for some use cases)

**Cons**:
- ❌ Requires testing the new sed patterns
- ❌ More complex regex (handles version detection differently)

---

### Option 3: Decouple Checkout from FOSSA Revision (Recommended)

**Change**: `.github/workflows/publish.yaml`
```yaml
fossa-scan:
  uses: .../sca-scan-and-guard.yaml@main
  with:
    # Remove git_ref - use default checkout (GitHub provides release SHA)
    use_vault: false
    config_file: '...'
    additional_scan_params: |
      fossa.config=...
      fossa.revision=${{ needs.extract-metadata.outputs.version }}  # Override to version
```

**How it works**:
1. GitHub triggers publish workflow on `release` event
2. Workflow checks out the **release commit SHA** (automatic)
3. FOSSA scans that checkout
4. FOSSA revision is **overridden** to the version number (e.g., `0.2.1`)

**Pros**:
- ✅ **Tag-format agnostic** - works regardless of "v" prefix
- ✅ Simpler - no complex tag parsing
- ✅ Guaranteed correct checkout (GitHub provides the SHA)
- ✅ FOSSA still tagged with clean version number
- ✅ Most robust solution

**Cons**:
- ❌ Still need to fix tag extraction for `package_path` and `version`
- ❌ Doesn't solve the sed pattern issue entirely

---

### Option 4: Hybrid Approach (Most Pragmatic)

Combine Option 2 and Option 3:

1. **Fix sed patterns** to handle tags without "v"
2. **Remove git_ref** from FOSSA scan (use default checkout)
3. **Override fossa.revision** to extracted version

**Changes**:
```yaml
# Extract metadata
PACKAGE_PATH=$(echo "$TAG" | sed 's/-[0-9][0-9]*\.[0-9].*//')
VERSION=$(echo "$TAG" | sed 's/.*-\([0-9][0-9]*\.[0-9].*\)/\1/')

# FOSSA scan
fossa-scan:
  with:
    # No git_ref specified
    additional_scan_params: |
      fossa.revision=${{ needs.extract-metadata.outputs.version }}
```

**Pros**:
- ✅ Handles current config (no "v")
- ✅ Robust FOSSA scanning
- ✅ Clean version tagging in FOSSA
- ✅ Minimal changes needed

**Cons**:
- ❌ Requires testing both changes

## Recommendation

**Recommended Solution**: **Option 4 (Hybrid Approach)**

**Rationale**:
1. **Respects existing config** - No need to change release-please behavior
2. **Most robust** - Doesn't rely on tag format for checkout
3. **Clean FOSSA tracking** - Version numbers, not SHAs
4. **Future-proof** - Works if tag format changes again

## Testing Plan

Before merging release-please PR:

1. **Test tag extraction locally**:
   ```bash
   TAG="sam-slack-0.2.1"
   PACKAGE_PATH=$(echo "$TAG" | sed 's/-[0-9][0-9]*\.[0-9].*//')
   VERSION=$(echo "$TAG" | sed 's/.*-\([0-9][0-9]*\.[0-9].*\)/\1/')
   echo "Package: $PACKAGE_PATH"  # Should be: sam-slack
   echo "Version: $VERSION"        # Should be: 0.2.1
   ```

2. **Dry-run release** (if possible):
   - Create a test tag: `git tag sam-test-plugin-0.1.0`
   - Trigger publish workflow manually
   - Verify extraction and FOSSA scan work

3. **Merge release-please PR**:
   - Monitor first release closely
   - Check FOSSA dashboard for correct versioning

## Files Requiring Changes

### For Option 4 (Recommended):

1. **`.github/workflows/publish.yaml`** (lines 30-47)
   - Update sed patterns to remove "-v" dependency
   - Remove `full_tag` output (no longer needed)

2. **`.github/workflows/publish.yaml`** (lines 57-70)
   - Remove `git_ref` parameter from fossa-scan job
   - Keep `fossa.revision` override

## Questions for Release Engineer

1. **Tag format preference**: Do you prefer tags with or without "v" prefix?
   - With "v": `sam-slack-v0.2.1`
   - Without "v": `sam-slack-0.2.1` (current config)

2. **Historical consistency**: The old manual release used `SAMv0.2.4` (with "v"). Should future releases match this?

3. **Testing strategy**: Can we create a test release to validate the workflow before merging the release-please PR?

4. **Timeline**: When do you plan to merge the release-please PR? We should fix this before then.

## Related Files

- `.github/workflows/publish.yaml` - Publish workflow (needs fix)
- `release-please-config.json` - Release-please configuration
- `.release-please-manifest.json` - Current plugin versions
- `.github/workflows/release-please.yaml` - Release-please trigger workflow

## Contact

For questions or to discuss solutions, please review this document with the release engineering team.
