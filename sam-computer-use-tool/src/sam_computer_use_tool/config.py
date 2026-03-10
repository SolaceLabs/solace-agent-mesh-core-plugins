"""Pydantic configuration models for ComputerUseTool."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ViewportConfig(BaseModel):
    """Configuration for browser viewport dimensions."""

    width: int = Field(
        default=1920,
        ge=320,
        le=7680,
        description="Viewport width in pixels",
    )
    height: int = Field(
        default=1080,
        ge=240,
        le=4320,
        description="Viewport height in pixels",
    )


class BrowserConfig(BaseModel):
    """Configuration for Playwright browser settings."""

    headless: bool = Field(
        default=True,
        description="Run browser in headless mode",
    )
    browser_type: str = Field(
        default="chromium",
        description="Browser type: chromium, firefox, or webkit",
    )
    timeout_ms: int = Field(
        default=30000,
        ge=1000,
        description="Default timeout for browser operations in milliseconds",
    )
    slow_mo: int = Field(
        default=0,
        ge=0,
        description="Slow down operations by specified ms (useful for debugging)",
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="Custom user agent string",
    )

    @field_validator("browser_type")
    @classmethod
    def validate_browser_type(cls, v: str) -> str:
        allowed = {"chromium", "firefox", "webkit"}
        if v not in allowed:
            raise ValueError(f"browser_type must be one of {allowed}, got '{v}'")
        return v


class ComputerUseToolConfig(BaseModel):
    """Complete configuration model for the ComputerUseTool."""

    tool_name: str = Field(
        default="computer_use",
        description="Tool name for LLM invocation",
    )
    tool_description: str = Field(
        default="Control a web browser to navigate, click, type, and interact with web pages.",
        description="Description of the tool for the LLM",
    )
    viewport: ViewportConfig = Field(default_factory=ViewportConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)

    # Coordinate normalization settings
    normalize_coordinates: bool = Field(
        default=True,
        description="If true, accept coordinates as 0.0-1.0 fractions of viewport; if false, use raw pixels",
    )

    # Screenshot settings
    screenshot_format: str = Field(
        default="png",
        description="Screenshot format: png or jpeg",
    )
    screenshot_quality: int = Field(
        default=80,
        ge=1,
        le=100,
        description="JPEG quality (ignored for PNG)",
    )

    # Artifact storage
    artifact_filename_prefix: str = Field(
        default="screenshot",
        description="Prefix for screenshot artifact filenames",
    )

    # LLM naming
    use_llm_naming: bool = Field(
        default=True,
        description="Use LLM to generate descriptive screenshot filenames",
    )

    @field_validator("screenshot_format")
    @classmethod
    def validate_screenshot_format(cls, v: str) -> str:
        allowed = {"png", "jpeg"}
        if v not in allowed:
            raise ValueError(f"screenshot_format must be one of {allowed}, got '{v}'")
        return v

    class Config:
        extra = "allow"
