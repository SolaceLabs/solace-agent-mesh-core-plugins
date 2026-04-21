"""Configurable field mapping engine for transforming source data to canonical format."""

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class FieldMapper:
    """
    Transforms source records to canonical output format using a three-phase pipeline:

    1. field_mapping: rename source fields to canonical field names
    2. exclusion_list: remove unwanted fields from the output
    3. rename_mapping: rename fields to custom output names

    Additionally supports computed_fields for derived values (e.g., displayName
    composed from firstName + lastName).
    """

    CANONICAL_FIELDS = {
        "id",
        "displayName",
        "workEmail",
        "jobTitle",
        "department",
        "location",
        "supervisorId",
        "hireDate",
        "mobilePhone",
    }

    def __init__(self, config: Dict[str, Any]):
        self.field_mapping: Dict[str, str] = config.get("field_mapping", {})
        self.exclusion_list: List[str] = config.get("exclusion_list", [])
        self.rename_mapping: Dict[str, str] = config.get("rename_mapping", {})
        self.computed_fields: List[Dict[str, Any]] = config.get("computed_fields", [])
        self.pass_through_unmapped: bool = config.get("pass_through_unmapped", True)

    def map_record(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Transforms a single source record through the three-phase pipeline.

        Args:
            source: Raw record from the backend system.

        Returns:
            Transformed record, or None if source is None/empty.
        """
        if not source:
            return None

        # Phase 1: Apply field_mapping (source -> canonical)
        canonical: Dict[str, Any] = {}
        mapped_source_keys: set = set()

        for source_key, canonical_key in self.field_mapping.items():
            if source_key in source:
                canonical[canonical_key] = source[source_key]
                mapped_source_keys.add(source_key)

        # Pass through unmapped fields
        if self.pass_through_unmapped:
            for key, value in source.items():
                if key not in mapped_source_keys and key not in canonical:
                    canonical[key] = value

        # Apply computed fields
        for computed in self.computed_fields:
            target = computed.get("target")
            source_fields = computed.get("source_fields", [])
            separator = computed.get("separator", " ")
            template = computed.get("template")

            if not target:
                continue

            if template:
                try:
                    canonical[target] = template.format(**source)
                except KeyError:
                    parts = [
                        str(source.get(f, "")).strip()
                        for f in source_fields
                        if source.get(f)
                    ]
                    if parts:
                        canonical[target] = separator.join(parts)
            else:
                parts = [
                    str(source.get(f, "")).strip()
                    for f in source_fields
                    if source.get(f)
                ]
                if parts:
                    canonical[target] = separator.join(parts)

        # Phase 2: Apply exclusion_list
        for excluded_field in self.exclusion_list:
            canonical.pop(excluded_field, None)

        # Phase 3: Apply rename_mapping (canonical -> output)
        output: Dict[str, Any] = {}
        for key, value in canonical.items():
            output_key = self.rename_mapping.get(key, key)
            output[output_key] = value

        return output

    def map_records(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transforms a list of source records. Filters out None results."""
        return [r for r in (self.map_record(s) for s in sources) if r is not None]
