#!/usr/bin/env bash
# Ensure required test dependencies exist in the Hatch test environment.

set -euo pipefail

# CI can override the Hatch env name, but default to current plugin test env.
HATCH_TEST_ENV="${HATCH_TEST_ENV:-hatch-test}"
# Packages required by build-plugin.yaml test command:
# - pytest: test runner
# - pytest-cov: coverage.xml generation for quality gates
# - pytest-json-ctrf: report.json generation for CTRF aggregation
REQUIRED_TEST_PACKAGES=(
  "pytest"
  "pytest-cov>=4.0.0"
  "pytest-json-ctrf>=0.1.0"
)

# Query installed packages once to avoid multiple `pip show` calls.
installed_packages_json="$(hatch -v run "${HATCH_TEST_ENV}:pip" list --format json)"
# Normalize case for robust name matching across different metadata variants.
installed_packages_json_lower="$(echo "$installed_packages_json" | tr '[:upper:]' '[:lower:]')"

missing_packages=()
for package_spec in "${REQUIRED_TEST_PACKAGES[@]}"; do
  # Strip version operators to compare only package names.
  package_name="$(echo "$package_spec" | sed -E 's/[<>=!~].*$//')"
  package_name_lower="$(echo "$package_name" | tr '[:upper:]' '[:lower:]')"

  # Match both `"name": "pkg"` and `"name":"pkg"` JSON formatting.
  if [[ "$installed_packages_json_lower" != *"\"name\": \"${package_name_lower}\""* ]] && \
     [[ "$installed_packages_json_lower" != *"\"name\":\"${package_name_lower}\""* ]]; then
    missing_packages+=("$package_spec")
  fi
done

if [[ ${#missing_packages[@]} -gt 0 ]]; then
  # Install only what is missing to keep CI fast and deterministic.
  echo "Installing missing test dependencies: ${missing_packages[*]}"
  hatch -v run "${HATCH_TEST_ENV}:pip" install "${missing_packages[@]}"
else
  echo "All required test dependencies are already installed."
fi
