"""Unit tests for the FieldMapper class."""

import pytest

from sam_event_mesh_identity_provider.field_mapper import FieldMapper


class TestFieldMapperPassthrough:
    """Tests for zero-config passthrough behavior."""

    def test_passthrough_no_config(self):
        """With empty config, source fields pass through unchanged."""
        mapper = FieldMapper({})
        source = {"id": "123", "workEmail": "a@b.com", "jobTitle": "Dev"}
        result = mapper.map_record(source)
        assert result == source

    def test_passthrough_preserves_all_fields(self):
        """All source fields appear in output when pass_through_unmapped is true."""
        mapper = FieldMapper({"pass_through_unmapped": True})
        source = {"custom1": "val1", "custom2": "val2", "nested": {"a": 1}}
        result = mapper.map_record(source)
        assert result == source


class TestFieldMapperMapping:
    """Tests for field_mapping (Phase 1)."""

    def test_basic_field_mapping(self):
        """Source fields are renamed according to field_mapping."""
        mapper = FieldMapper({
            "field_mapping": {"emp_email": "workEmail", "emp_id": "id"},
            "pass_through_unmapped": False,
        })
        source = {"emp_email": "a@b.com", "emp_id": "123", "extra": "data"}
        result = mapper.map_record(source)
        assert result == {"workEmail": "a@b.com", "id": "123"}

    def test_mapped_field_not_in_source(self):
        """Mapping entries for missing source fields are silently skipped."""
        mapper = FieldMapper({
            "field_mapping": {"missing_key": "workEmail"},
            "pass_through_unmapped": False,
        })
        source = {"other_field": "value"}
        result = mapper.map_record(source)
        assert result == {}

    def test_mapping_with_passthrough(self):
        """Mapped and unmapped fields both appear when pass_through_unmapped is true."""
        mapper = FieldMapper({
            "field_mapping": {"emp_email": "workEmail"},
            "pass_through_unmapped": True,
        })
        source = {"emp_email": "a@b.com", "department": "Eng"}
        result = mapper.map_record(source)
        assert result == {"workEmail": "a@b.com", "department": "Eng"}


class TestFieldMapperExclusion:
    """Tests for exclusion_list (Phase 2)."""

    def test_exclusion_list_removes_fields(self):
        """Fields in exclusion_list are removed from output."""
        mapper = FieldMapper({"exclusion_list": ["mobilePhone", "hireDate"]})
        source = {"id": "1", "mobilePhone": "555", "hireDate": "2020-01-01", "name": "A"}
        result = mapper.map_record(source)
        assert "mobilePhone" not in result
        assert "hireDate" not in result
        assert result["id"] == "1"
        assert result["name"] == "A"

    def test_exclusion_of_nonexistent_field(self):
        """Excluding a field that doesn't exist in source doesn't error."""
        mapper = FieldMapper({"exclusion_list": ["nonexistent"]})
        source = {"id": "1"}
        result = mapper.map_record(source)
        assert result == {"id": "1"}


class TestFieldMapperRenaming:
    """Tests for rename_mapping (Phase 3)."""

    def test_rename_mapping(self):
        """Canonical fields are renamed in the output."""
        mapper = FieldMapper({
            "rename_mapping": {"supervisorId": "managerId", "workEmail": "email"},
        })
        source = {"supervisorId": "mgr1", "workEmail": "a@b.com", "id": "1"}
        result = mapper.map_record(source)
        assert result == {"managerId": "mgr1", "email": "a@b.com", "id": "1"}

    def test_rename_only_affects_matching_keys(self):
        """Fields not in rename_mapping keep their original names."""
        mapper = FieldMapper({"rename_mapping": {"workEmail": "email"}})
        source = {"workEmail": "a@b.com", "id": "1"}
        result = mapper.map_record(source)
        assert result == {"email": "a@b.com", "id": "1"}


class TestFieldMapperComputedFields:
    """Tests for computed_fields."""

    def test_computed_field_concatenation(self):
        """Computed field concatenates source fields with separator."""
        mapper = FieldMapper({
            "computed_fields": [
                {
                    "target": "displayName",
                    "source_fields": ["firstName", "lastName"],
                    "separator": " ",
                }
            ],
            "pass_through_unmapped": False,
        })
        source = {"firstName": "Jane", "lastName": "Doe"}
        result = mapper.map_record(source)
        assert result["displayName"] == "Jane Doe"

    def test_computed_field_skips_empty_parts(self):
        """Empty source fields are skipped during concatenation."""
        mapper = FieldMapper({
            "computed_fields": [
                {
                    "target": "displayName",
                    "source_fields": ["firstName", "middleName", "lastName"],
                    "separator": " ",
                }
            ],
            "pass_through_unmapped": False,
        })
        source = {"firstName": "Jane", "middleName": "", "lastName": "Doe"}
        result = mapper.map_record(source)
        assert result["displayName"] == "Jane Doe"

    def test_computed_field_with_template(self):
        """Template-based computed field uses format string."""
        mapper = FieldMapper({
            "computed_fields": [
                {
                    "target": "displayName",
                    "source_fields": ["firstName", "lastName"],
                    "template": "{firstName} {lastName}",
                }
            ],
            "pass_through_unmapped": False,
        })
        source = {"firstName": "Jane", "lastName": "Doe"}
        result = mapper.map_record(source)
        assert result["displayName"] == "Jane Doe"

    def test_computed_field_template_fallback(self):
        """When template format fails, falls back to concatenation."""
        mapper = FieldMapper({
            "computed_fields": [
                {
                    "target": "displayName",
                    "source_fields": ["firstName", "lastName"],
                    "template": "{firstName} {missingKey}",
                    "separator": " ",
                }
            ],
            "pass_through_unmapped": False,
        })
        source = {"firstName": "Jane", "lastName": "Doe"}
        result = mapper.map_record(source)
        assert result["displayName"] == "Jane Doe"

    def test_computed_field_no_target(self):
        """Computed field with no target is skipped."""
        mapper = FieldMapper({
            "computed_fields": [
                {"source_fields": ["firstName", "lastName"], "separator": " "}
            ],
            "pass_through_unmapped": False,
        })
        source = {"firstName": "Jane", "lastName": "Doe"}
        result = mapper.map_record(source)
        assert result == {}


class TestFieldMapperFullPipeline:
    """Tests for the complete three-phase pipeline."""

    def test_full_pipeline(self):
        """All three phases applied in sequence: mapping, exclusion, renaming."""
        mapper = FieldMapper({
            "field_mapping": {"emp_title": "jobTitle", "emp_email": "workEmail"},
            "exclusion_list": ["workEmail"],
            "rename_mapping": {"jobTitle": "title"},
            "pass_through_unmapped": False,
        })
        source = {"emp_title": "Engineer", "emp_email": "a@b.com"}
        result = mapper.map_record(source)
        # workEmail is excluded, jobTitle renamed to title
        assert result == {"title": "Engineer"}

    def test_hr_system_mapping(self, hr_field_mapping_config, sample_hr_employee):
        """Verify HR system mapping produces the expected canonical output."""
        mapper = FieldMapper(hr_field_mapping_config)
        result = mapper.map_record(sample_hr_employee)

        assert result["displayName"] == "Jane Doe"
        assert result["id"] == "jane.doe@company.com"
        assert result["workEmail"] == "jane.doe@company.com"
        assert result["jobTitle"] == "Senior Engineer"
        assert result["department"] == "Engineering"
        assert result["location"] == "Toronto"
        assert result["manager"] == "mgr@company.com"


class TestFieldMapperEdgeCases:
    """Tests for edge cases."""

    def test_none_input(self):
        """Returns None when source is None."""
        mapper = FieldMapper({})
        assert mapper.map_record(None) is None

    def test_empty_dict_input(self):
        """Returns None when source is empty dict."""
        mapper = FieldMapper({})
        assert mapper.map_record({}) is None

    def test_map_records_list(self):
        """map_records processes a list and filters out None results."""
        mapper = FieldMapper({"pass_through_unmapped": True})
        sources = [
            {"id": "1", "name": "Alice"},
            {},
            {"id": "2", "name": "Bob"},
            None,
        ]
        results = mapper.map_records(sources)
        assert len(results) == 2
        assert results[0]["id"] == "1"
        assert results[1]["id"] == "2"

    def test_pass_through_unmapped_false(self):
        """Only mapped fields appear when pass_through_unmapped is false."""
        mapper = FieldMapper({
            "field_mapping": {"name": "displayName"},
            "pass_through_unmapped": False,
        })
        source = {"name": "Jane", "extra_field": "value", "another": "data"}
        result = mapper.map_record(source)
        assert result == {"displayName": "Jane"}
