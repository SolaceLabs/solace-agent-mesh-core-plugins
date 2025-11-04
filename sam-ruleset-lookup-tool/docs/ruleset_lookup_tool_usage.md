# RulesetLookupTool Usage Guide

## Overview

The `RulesetLookupTool` is a configuration-driven tool that provides text-based rulesets to LLM agents for reasoning. It acts as a **rule retrieval system** rather than a decision-making engine - it fetches pre-written business logic that the LLM then evaluates.

## Key Concepts

### What It Does
- **Retrieves** text-based rulesets organized by groups
- **Provides** structured IF/ELSE logic for LLM evaluation
- **Supports** multiple ruleset topics within each group

### What It Doesn't Do
- **Execute** decision logic (the LLM does this)
- **Make** business decisions
- **Modify** or interpret rules

## Configuration Structure

### Basic Configuration

```yaml
- tool_type: python
  component_module: sam_ruleset_lookup_tool.ruleset_lookup_tool
  component_base_path: .
  tool_config:
    decision_data: 
      !include ../hr_decision_tree.json
    include_topics_in_description: true
    include_groups_in_description: true
    default_group_key: "_default"
```

### Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `decision_data` | Object | Yes | - | The main ruleset configuration (see structure below) |
| `include_topics_in_description` | Boolean | No | `false` | Include available topics in tool description |
| `include_groups_in_description` | Boolean | No | `false` | Include valid groups in tool description |
| `default_group_key` | String | No | `"_default"` | Fallback group when specified group not found |

## Decision Data Structure

The `decision_data` must contain the following structure:

```json
{
  "name": "hr_decision_trees",
  "description": "Provides HR policy rulesets for employee questions",
  "grouping_parameter": "country",
  "input_parameters": [
    {
      "name": "country",
      "type": "string",
      "required": true,
      "description": "Employee's country to determine applicable rulesets"
    }
  ],
  "decision_tree_groups": {
    "example_group": {
      "decision_trees": [
        {
          "name": "Generic Policy",
          "description": "Demonstrates a simple ruleset for example purposes",
          "decision_logic": "IF parameter1 == 'value1' AND parameter2 > 10:\n  RETURN 'Result A'\nELSE IF parameter1 == 'value2':\n  RETURN 'Result B'\nELSE:\n  RETURN 'Default result'"
        }
      ]
    },
    "_default": {
      "decision_trees": [
        {
          "name": "General Policy",
          "description": "Default policy for unsupported regions",
          "decision_logic": "Contact HR directly for region-specific policies"
        }
      ]
    }
  }
}
```

### Required Fields

#### Root Level
- `name`: Tool identifier (used for function naming)
- `description`: Tool description for LLM
- `grouping_parameter`: Parameter name for group selection
- `input_parameters`: Array of tool parameters
- `decision_tree_groups`: Object containing ruleset groups

#### Input Parameters
- `name`: Parameter name
- `type`: Data type (`string`, `boolean`, `integer`, `number`)
- `required`: Whether parameter is mandatory
- `description`: Parameter description

#### Decision Tree Groups
- Key: Group identifier (e.g., "netherlands", "germany")
- Value: Object with `decision_trees` array

#### Decision Trees
- `name`: Ruleset name/topic
- `description`: Ruleset description
- `decision_logic`: Text-based IF/ELSE logic for LLM evaluation

## Usage Examples

### Example 1: HR Policy Agent

```yaml
# Agent configuration
tools:
  - tool_type: python
    component_module: sam_ruleset_lookup_tool.ruleset_lookup_tool
    component_base_path: .
    tool_config:
      decision_data: 
        name: "hr_policies"
        description: "HR policy rulesets for employee questions"
        grouping_parameter: "country"
        input_parameters:
          - name: "country"
            type: "string"
            required: true
            description: "Employee's country"
        decision_tree_groups:
          netherlands:
            decision_trees:
              - name: "Leave Policy"
                description: "Annual leave calculation rules"
                decision_logic: |
                  IF employment_years >= 5:
                    RETURN 25 + (employment_years - 5) * 0.5 days (max 30)
                  ELSE:
                    RETURN 20 + employment_years days
      include_topics_in_description: true
      include_groups_in_description: true
```

### Example 2: Multi-Region Compliance

```yaml
tools:
  - tool_type: python
    component_module: your_module.ruleset_lookup_tool
    tool_config:
      decision_data:
        name: "compliance_rules"
        description: "Regional compliance rulesets"
        grouping_parameter: "region"
        input_parameters:
          - name: "region"
            type: "string" 
            required: true
            description: "Business region"
          - name: "entity_type"
            type: "string"
            required: false
            description: "Legal entity type"
        decision_tree_groups:
          europe:
            decision_trees:
              - name: "GDPR Compliance"
                description: "GDPR data handling rules"
                decision_logic: |
                  IF data_type == 'personal':
                    REQUIRE explicit_consent AND data_protection_officer_approval
                  IF data_retention > 24_months:
                    REQUIRE legal_basis_documentation
          americas:
            decision_trees:
              - name: "SOX Compliance"
                description: "Sarbanes-Oxley compliance rules"
                decision_logic: |
                  IF financial_data == true:
                    REQUIRE dual_approval AND audit_trail
```

## Tool Behavior

### Dynamic Tool Naming
The tool generates its function name as: `get_rulesets_{sanitized_name}`

For example:
- `name: "hr_policies"` → `get_rulesets_hr_policies`
- `name: "Compliance Rules"` → `get_rulesets_compliance_rules`

### Group Selection Logic
1. **Exact Match**: Looks for exact group key (case-insensitive)
2. **Fallback**: Uses `default_group_key` if specified group not found
3. **Error**: Returns error if no group found and no default configured

### Response Format
```json
{
  "decision_logic": "Ruleset Name: Leave Policy\nDescription: Annual leave calculation rules\nLogic:\nIF employment_years >= 5:\n  RETURN 25 + (employment_years - 5) * 0.5 days (max 30)\nELSE:\n  RETURN 20 + employment_years days\n\n---\n\n..."
}
```