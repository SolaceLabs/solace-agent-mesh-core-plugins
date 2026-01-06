"""
Configuration management for OAuth test client.
"""

import os
from typing import Optional

from pydantic import BaseModel, Field


class TestConfig(BaseModel):
    """Test client configuration."""

    # MCP Server
    mcp_server_url: str = Field(
        default="http://localhost:8090",
        description="MCP server base URL"
    )

    # Auth Proxy
    auth_proxy_url: str = Field(
        default="http://localhost:8050",
        description="External auth proxy URL"
    )

    # Callback Server
    callback_host: str = Field(
        default="127.0.0.1",
        description="Host for OAuth callback server"
    )
    callback_port: int = Field(
        default=8888,
        description="Port for OAuth callback server"
    )

    # Timeouts
    authorization_timeout: int = Field(
        default=300,
        description="Seconds to wait for user to authorize (5 minutes)"
    )
    state_ttl: int = Field(
        default=300,
        description="OAuth state TTL in seconds (matches server default)"
    )
    code_ttl: int = Field(
        default=300,
        description="Authorization code TTL in seconds (matches server default)"
    )

    # Test Options
    verbose: bool = Field(
        default=True,
        description="Enable verbose output"
    )
    auto_open_browser: bool = Field(
        default=True,
        description="Automatically open browser for authorization"
    )
    export_results: bool = Field(
        default=True,
        description="Export test results to files"
    )
    results_dir: str = Field(
        default="./test_results",
        description="Directory for test result exports"
    )

    # OAuth Client Details
    default_client_id: Optional[str] = Field(
        default=None,
        description="Default OAuth client ID (if pre-registered)"
    )
    default_client_secret: Optional[str] = Field(
        default=None,
        description="Default OAuth client secret (if pre-registered)"
    )

    @property
    def callback_uri(self) -> str:
        """Get the full callback URI."""
        return f"http://{self.callback_host}:{self.callback_port}/callback"

    @classmethod
    def from_env(cls) -> "TestConfig":
        """
        Load configuration from environment variables.

        Environment variables:
        - MCP_SERVER_URL: MCP server base URL
        - AUTH_PROXY_URL: External auth proxy URL
        - CALLBACK_HOST: Callback server host
        - CALLBACK_PORT: Callback server port
        - AUTHORIZATION_TIMEOUT: Authorization timeout in seconds
        - VERBOSE: Enable verbose output (true/false)
        - AUTO_OPEN_BROWSER: Auto-open browser (true/false)
        - RESULTS_DIR: Test results directory

        Returns:
            TestConfig instance
        """
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass  # python-dotenv not installed, skip

        return cls(
            mcp_server_url=os.getenv("MCP_SERVER_URL", "http://localhost:8090"),
            auth_proxy_url=os.getenv("AUTH_PROXY_URL", "http://localhost:8050"),
            callback_host=os.getenv("CALLBACK_HOST", "127.0.0.1"),
            callback_port=int(os.getenv("CALLBACK_PORT", "8888")),
            authorization_timeout=int(os.getenv("AUTHORIZATION_TIMEOUT", "300")),
            verbose=os.getenv("VERBOSE", "true").lower() == "true",
            auto_open_browser=os.getenv("AUTO_OPEN_BROWSER", "true").lower() == "true",
            results_dir=os.getenv("RESULTS_DIR", "./test_results"),
            default_client_id=os.getenv("DEFAULT_CLIENT_ID"),
            default_client_secret=os.getenv("DEFAULT_CLIENT_SECRET"),
        )

    def model_dump_safe(self) -> dict:
        """Dump configuration without sensitive data."""
        data = self.model_dump()
        # Redact secrets
        if data.get("default_client_secret"):
            data["default_client_secret"] = "***REDACTED***"
        return data
