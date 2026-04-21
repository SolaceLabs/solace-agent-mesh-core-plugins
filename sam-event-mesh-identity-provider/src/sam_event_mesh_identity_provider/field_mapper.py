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
        canonical = self._apply_field_mapping(source)

        # Apply computed fields
        self._apply_computed_fields(source, canonical)

        # Phase 2: Apply exclusion_list
        self._apply_exclusions(canonical)

        # Phase 3: Apply rename_mapping (canonical -> output)
        return self._apply_rename_mapping(canonical)

    def _apply_field_mapping(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply field mapping and pass through unmapped fields.

        Args:
            source: Raw record from the backend system.

        Returns:
            Dictionary with mapped fields.
        """
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

        return canonical

    def _apply_computed_fields(self, source: Dict[str, Any], canonical: Dict[str, Any]) -> None:
        """
        Apply computed fields to the canonical dictionary.

        Args:
            source: Raw record from the backend system.
            canonical: Dictionary to add computed fields to (modified in place).
        """
        for computed in self.computed_fields:
            target = computed.get("target")
            if not target:
                continue

            computed_value = self._compute_field_value(source, computed)
            if computed_value is not None:
                canonical[target] = computed_value

    def _compute_field_value(self, source: Dict[str, Any], computed: Dict[str, Any]) -> Optional[str]:
        """
        Compute a single field value using template or source fields.

        Args:
            source: Raw record from the backend system.
            computed: Computed field configuration.

        Returns:
            Computed field value, or None if it cannot be computed.
        """
        template = computed.get("template")
        
        if template:
            return self._compute_from_template(source, computed, template)
        
        return self._compute_from_source_fields(source, computed)

    def _compute_from_template(
        self, source: Dict[str, Any], computed: Dict[str, Any], template: str
    ) -> Optional[str]:
        """
        Compute field value using a template string.

        Args:
            source: Raw record from the backend system.
            computed: Computed field configuration.
            template: Template string with placeholders.

        Returns:
            Formatted string, or fallback to source fields if template fails.
        """
        try:
            return template.format(**source)
        except KeyError:
            # Fallback to source_fields if template fails
            return self._compute_from_source_fields(source, computed)

    def _compute_from_source_fields(self, source: Dict[str, Any], computed: Dict[str, Any]) -> Optional[str]:
        """
        Compute field value by joining source fields.

        Args:
            source: Raw record from the backend system.
            computed: Computed field configuration.

        Returns:
            Joined string from source fields, or None if no valid parts.
        """
        source_fields = computed.get("source_fields", [])
        separator = computed.get("separator", " ")
        
        parts = [
            str(source.get(f, "")).strip()
            for f in source_fields
            if source.get(f)
        ]
        
        if parts:
            return separator.join(parts)
        
        return None

    def _apply_exclusions(self, canonical: Dict[str, Any]) -> None:
        """
        Remove excluded fields from the canonical dictionary.

        Args:
            canonical: Dictionary to remove fields from (modified in place).
        """
        for excluded_field in self.exclusion_list:
            canonical.pop(excluded_field, None)

    def _apply_rename_mapping(self, canonical: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply rename mapping to create the final output dictionary.

        Args:
            canonical: Dictionary with canonical field names.

        Returns:
            Dictionary with renamed fields.
        """
        output: Dict[str, Any] = {}
        for key, value in canonical.items():
            output_key = self.rename_mapping.get(key, key)
            output[output_key] = value
        return output

    def map_records(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transforms a list of source records. Filters out None results."""
        return [r for r in (self.map_record(s) for s in sources) if r is not None]
