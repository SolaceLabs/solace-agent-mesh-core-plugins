from typing import List, Optional
from pydantic import BaseModel, Field

class McpAdapterConfig(BaseModel):
    """Configuration model for the McpAdapter."""

    mcp_server_name: str = Field(
        default="SAM MCP Gateway", description="Name of the MCP server"
    )
    mcp_server_description: str = Field(
        default="Model Context Protocol gateway to Solace Agent Mesh",
        description="Description of the MCP server",
    )
    transport: str = Field(
        default="http", description="Transport type: 'http' or 'stdio'"
    )
    port: int = Field(default=8000, description="Port for HTTP transport")
    host: str = Field(default="0.0.0.0", description="Host for HTTP transport")
    default_user_identity: str = Field(
        default="mcp_user", description="Default user identity for authentication"
    )
    stream_responses: bool = Field(
        default=True, description="Whether to stream responses back to MCP client"
    )
    task_timeout_seconds: int = Field(
        default=300,
        description="Timeout in seconds for waiting for agent task completion (default 5 minutes)",
    )

    # OAuth Authentication Configuration
    enable_auth: bool = Field(
        default=False,
        description="Enable OAuth authentication. Requires HTTP transport and external OAuth2 service.",
    )
    external_auth_service_url: str = Field(
        default="http://localhost:8050",
        description="URL of SAM's OAuth2 service (enterprise feature)",
    )
    external_auth_provider: str = Field(
        default="azure",
        description="OAuth provider configured in OAuth2 service (e.g., 'azure', 'google')",
    )
    dev_mode: bool = Field(
        default=False,
        description="Development mode - bypass auth and use default_user_identity (WARNING: insecure, dev only)",
    )
    user_id_claim: str = Field(
        default="email",
        description="OAuth claim to use as user ID for SAM audit logs (options: 'email', 'sub', 'upn', 'preferred_username')",
    )
    session_secret_key: Optional[str] = Field(
        default=None,
        description="Secret key for session encryption (auto-generated if not provided)",
    )
    require_pkce: bool = Field(
        default=True,
        description="Require PKCE (Proof Key for Code Exchange, RFC 7636) for all OAuth flows. "
        "STRONGLY recommended for security. Disable only for legacy client compatibility.",
    )

    # File handling configuration
    inline_image_max_bytes: int = Field(
        default=5_242_880,  # 5MB
        description="Maximum size in bytes for inline image returns (larger images become resource links)",
    )
    inline_audio_max_bytes: int = Field(
        default=10_485_760,  # 10MB
        description="Maximum size in bytes for inline audio returns (larger audio becomes resource links)",
    )
    inline_text_max_bytes: int = Field(
        default=1_048_576,  # 1MB
        description="Maximum size in bytes for inline text file returns (larger text files become resource links)",
    )
    inline_binary_max_bytes: int = Field(
        default=524_288,  # 512KB
        description="Maximum size in bytes for inline binary returns (larger binaries become resource links)",
    )

    # Resource configuration
    resource_uri_prefix: str = Field(
        default="artifact",
        description="URI prefix for artifact resources (e.g., 'artifact://session_id/filename')",
    )
    enable_artifact_resources: bool = Field(
        default=True,
        description="Whether to expose artifacts as MCP resources",
    )

    # Tool filtering configuration
    include_tools: List[str] = Field(
        default_factory=list,
        description="List of tool patterns to include (regex or exact match). Empty list = include all. "
        "Filters check agent name, skill name, and tool name. "
        "Examples: ['data_.*', 'fetch_user_info']",
    )
    exclude_tools: List[str] = Field(
        default_factory=list,
        description="List of tool patterns to exclude (regex or exact match). Takes priority over includes. "
        "Filters check agent name, skill name, and tool name. "
        "Priority: exclude exact > include exact > exclude regex > include regex. "
        "Examples: ['.*_debug', 'test_tool']",
    )

