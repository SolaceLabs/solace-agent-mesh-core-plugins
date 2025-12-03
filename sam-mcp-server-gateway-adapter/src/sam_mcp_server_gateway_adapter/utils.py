"""
Utility functions for the MCP Gateway Adapter.
"""

import re
from typing import Optional
from a2a.types import AgentSkill


def sanitize_tool_name(name: str) -> str:
    """
    Sanitize an agent/skill name to be a valid MCP tool name.

    MCP tool names should be alphanumeric with underscores.
    This function:
    - Converts to lowercase
    - Replaces spaces and hyphens with underscores
    - Removes any non-alphanumeric characters except underscores
    - Removes duplicate underscores
    - Ensures it doesn't start with a number

    Args:
        name: The original agent or skill name

    Returns:
        A sanitized tool name suitable for MCP
    """
    # Convert to lowercase
    name = name.lower()

    # Replace spaces and hyphens with underscores
    name = name.replace(" ", "_").replace("-", "_")

    # Remove any character that isn't alphanumeric or underscore
    name = re.sub(r"[^a-z0-9_]", "", name)

    # Remove duplicate underscores
    name = re.sub(r"_+", "_", name)

    # Remove leading/trailing underscores
    name = name.strip("_")

    # Ensure doesn't start with a number
    if name and name[0].isdigit():
        name = f"tool_{name}"

    # Fallback if name is empty
    if not name:
        name = "unnamed_tool"

    return name


def format_agent_skill_description(skill: AgentSkill) -> str:
    """
    Format an AgentSkill into a description for an MCP tool.

    This creates a human-readable description that combines:
    - The skill's description
    - Example usage (if available)
    - Input/output modes (if specified)

    Args:
        skill: The AgentSkill to format

    Returns:
        A formatted description string
    """
    parts = []

    # Main description
    if skill.description:
        parts.append(skill.description)

    # Add examples if available
    if skill.examples and len(skill.examples) > 0:
        parts.append("\nExamples:")
        for idx, example in enumerate(skill.examples[:3], 1):  # Limit to 3 examples
            # Examples might be strings or dicts
            example_text = example if isinstance(example, str) else str(example)
            parts.append(f"  {idx}. {example_text}")

    # Add input/output mode info if present
    modes_info = []
    if skill.input_modes:
        modes_info.append(f"Input modes: {', '.join(skill.input_modes)}")
    if skill.output_modes:
        modes_info.append(f"Output modes: {', '.join(skill.output_modes)}")

    if modes_info:
        parts.append("\n" + " | ".join(modes_info))

    # Add tags if present
    if skill.tags:
        parts.append(f"\nTags: {', '.join(skill.tags)}")

    return "\n".join(parts) if parts else "No description available"


def truncate_text(text: str, max_length: int = 1000) -> str:
    """
    Truncate text to a maximum length, adding ellipsis if needed.

    Args:
        text: The text to truncate
        max_length: Maximum length (default 1000)

    Returns:
        Truncated text with "..." appended if it was truncated
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def create_session_id(prefix: str = "mcp") -> str:
    """
    Create a unique session ID for MCP requests.

    Args:
        prefix: Prefix for the session ID (default "mcp")

    Returns:
        A unique session ID string
    """
    import uuid
    from datetime import datetime

    timestamp = int(datetime.now().timestamp() * 1000)
    unique_id = uuid.uuid4().hex[:8]
    return f"{prefix}-{timestamp}-{unique_id}"


def extract_agent_skill_from_tool_name(
    tool_name: str,
    separator: str = "_"
) -> Optional[tuple[str, str]]:
    """
    Parse a tool name to extract agent name and skill name.

    Assumes format: agent_name_skill_name

    Args:
        tool_name: The MCP tool name
        separator: The separator character (default "_")

    Returns:
        Tuple of (agent_name, skill_name) or None if cannot parse
    """
    parts = tool_name.split(separator)
    if len(parts) < 2:
        return None

    # Assume the last part is the skill, everything before is the agent
    skill_name = parts[-1]
    agent_name = separator.join(parts[:-1])

    return (agent_name, skill_name)


def should_include_tool(
    agent_name: str,
    skill_name: str,
    tool_name: str,
    include_patterns: list[str],
    exclude_patterns: list[str]
) -> bool:
    """
    Determine if a tool should be included based on filter patterns.

    Filters check against all three names: agent_name, skill_name, and tool_name.
    Supports both regex patterns and exact string matches (auto-detected).

    Priority order (highest to lowest):
    1. Exclude exact match - if any exclude pattern matches exactly, reject
    2. Include exact match - if any include pattern matches exactly, accept
    3. Exclude regex match - if any exclude pattern matches as regex, reject
    4. Include regex match - if any include pattern matches as regex, accept
    5. Default - if include_patterns is empty, accept; otherwise reject

    Args:
        agent_name: Original agent name (e.g., "DataAgent")
        skill_name: Original skill name (e.g., "Fetch User")
        tool_name: Sanitized tool name (e.g., "data_agent_fetch_user")
        include_patterns: List of patterns to include
        exclude_patterns: List of patterns to exclude

    Returns:
        True if tool should be included, False otherwise

    Examples:
        >>> should_include_tool("DataAgent", "Fetch", "data_agent_fetch",
        ...                     ["data_.*"], [".*_debug"])
        True

        >>> should_include_tool("DebugAgent", "Test", "debug_agent_test",
        ...                     ["data_.*"], ["debug_agent_test"])
        False  # Exact exclude match
    """
    # If no filters specified, include everything
    if not include_patterns and not exclude_patterns:
        return True

    # Collect all names to check
    names_to_check = [agent_name, skill_name, tool_name]

    # Separate patterns into exact and regex
    exact_includes, regex_includes = _split_patterns(include_patterns)
    exact_excludes, regex_excludes = _split_patterns(exclude_patterns)

    # Priority 1: Exclude exact match (highest priority)
    for pattern in exact_excludes:
        if _matches_exact_any(pattern, names_to_check):
            return False

    # Priority 2: Include exact match
    for pattern in exact_includes:
        if _matches_exact_any(pattern, names_to_check):
            return True

    # Priority 3: Exclude regex match
    for pattern in regex_excludes:
        if _matches_regex_any(pattern, names_to_check):
            return False

    # Priority 4: Include regex match
    for pattern in regex_includes:
        if _matches_regex_any(pattern, names_to_check):
            return True

    # Priority 5: Default behavior
    # If include_patterns specified but no match found, reject
    # If only exclude_patterns specified, accept (not excluded)
    return len(include_patterns) == 0


def _split_patterns(patterns: list[str]) -> tuple[list[str], list[str]]:
    """
    Split patterns into exact matches and regex patterns.

    Auto-detects regex by checking for special regex characters.

    Args:
        patterns: List of pattern strings

    Returns:
        Tuple of (exact_patterns, regex_patterns)
    """
    exact = []
    regex = []

    # Regex special characters that indicate a pattern
    regex_chars = r'.*+?[]{}()^$|\\'

    for pattern in patterns:
        # Check if pattern contains regex special chars
        if any(char in pattern for char in regex_chars):
            regex.append(pattern)
        else:
            exact.append(pattern)

    return exact, regex


def _matches_exact_any(pattern: str, names: list[str]) -> bool:
    """
    Check if pattern matches any name exactly (case-sensitive).

    Args:
        pattern: Exact string to match
        names: List of names to check against

    Returns:
        True if pattern matches any name exactly
    """
    return pattern in names


def _matches_regex_any(pattern: str, names: list[str]) -> bool:
    """
    Check if regex pattern matches any name.

    Args:
        pattern: Regex pattern string
        names: List of names to check against

    Returns:
        True if pattern matches any name
    """
    try:
        compiled = re.compile(pattern)
        return any(compiled.search(name) for name in names)
    except re.error:
        # If regex compilation fails, treat as exact match
        return pattern in names
