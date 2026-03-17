#!/usr/bin/env bash
# Ensure required test dependencies exist in the Hatch test environment.

set -euo pipefail

HATCH_TEST_ENV="${HATCH_TEST_ENV:-hatch-test}"
REQUIRED_TEST_PACKAGES=(
  "pytest"
  "pytest-cov>=4.0.0"
  "pytest-json-ctrf>=0.1.0"
)

installed_packages_json="$(hatch -v run "${HATCH_TEST_ENV}:pip" list --format json)"
installed_packages_json_lower="$(echo "$installed_packages_json" | tr '[:upper:]' '[:lower:]')"

missing_packages=()
for package_spec in "${REQUIRED_TEST_PACKAGES[@]}"; do
  package_name="$(echo "$package_spec" | sed -E 's/[<>=!~].*$//')"
  package_name_lower="$(echo "$package_name" | tr '[:upper:]' '[:lower:]')"

  if [[ "$installed_packages_json_lower" != *"\"name\": \"${package_name_lower}\""* ]] && \
     [[ "$installed_packages_json_lower" != *"\"name\":\"${package_name_lower}\""* ]]; then
    missing_packages+=("$package_spec")
  fi
done

if [[ ${#missing_packages[@]} -gt 0 ]]; then
  echo "Installing missing test dependencies: ${missing_packages[*]}"
  hatch -v run "${HATCH_TEST_ENV}:pip" install "${missing_packages[@]}"
else
  echo "All required test dependencies are already installed."
fi
