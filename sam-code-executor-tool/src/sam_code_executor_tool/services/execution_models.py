"""Pydantic models for code execution configuration and results."""

from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


class ExecutorType(str, Enum):
    """Supported executor types."""

    DOCKER = "docker"
    KUBERNETES = "kubernetes"


class InputFile(BaseModel):
    """Represents a file to be provided to the code execution environment."""

    filename: str = Field(description="Name of the file in the execution environment")
    content: str = Field(description="Base64-encoded content of the file")


class OutputFile(BaseModel):
    """Represents a file produced by code execution."""

    filename: str = Field(description="Name of the output file")
    content: str = Field(description="Base64-encoded content of the file")


class CodeExecutionInput(BaseModel):
    """Input data for code execution."""

    code: str = Field(description="Python code to execute")
    input_files: Optional[List[InputFile]] = Field(
        default=None, description="Optional files to make available during execution"
    )
    execution_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for this execution (auto-generated if not provided)",
    )
    timeout_seconds: Optional[int] = Field(
        default=None,
        description="Execution timeout override (uses default if not specified)",
    )


class CodeExecutionResult(BaseModel):
    """Result of code execution."""

    stdout: str = Field(default="", description="Standard output from execution")
    stderr: str = Field(default="", description="Standard error from execution")
    exit_code: int = Field(default=0, description="Exit code of the execution")
    output_files: Optional[List[OutputFile]] = Field(
        default=None, description="Files produced by the execution"
    )
    execution_id: Optional[str] = Field(
        default=None, description="Identifier for this execution"
    )
    success: bool = Field(default=True, description="Whether execution succeeded")
    error_message: Optional[str] = Field(
        default=None, description="Error message if execution failed"
    )


class StartupCommandConfig(BaseModel):
    """Configuration for optional startup scripts."""

    enabled: bool = Field(default=False, description="Whether to run startup script")
    script_type: Literal["python", "shell"] = Field(
        default="shell", description="Type of script: 'python' or 'shell'"
    )
    script: str = Field(
        default="", description="Inline script content to execute on container start"
    )
    timeout_seconds: int = Field(
        default=300, description="Timeout for startup script execution"
    )


class DockerExecutorConfig(BaseModel):
    """Configuration specific to Docker executor."""

    image: str = Field(
        default="python:3.11-slim", description="Docker image to use for execution"
    )
    working_directory: str = Field(
        default="/workspace", description="Working directory inside the container"
    )
    memory_limit: str = Field(
        default="512m",
        description="Memory limit for the container (e.g., '512m', '1g')",
    )
    cpu_limit: Optional[float] = Field(
        default=1.0, description="CPU limit (1.0 = one full CPU)"
    )
    network_disabled: bool = Field(
        default=True,
        description="Disable network access in the container for security",
    )
    environment: Dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to set in the container",
    )
    volumes: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Volume mounts (host_path -> {bind: container_path, mode: 'ro'/'rw'})",
    )
    startup_command: StartupCommandConfig = Field(
        default_factory=StartupCommandConfig,
        description="Optional startup script configuration",
    )


class KubernetesExecutorConfig(BaseModel):
    """Configuration specific to Kubernetes executor."""

    # Cluster connection
    kubeconfig_path: Optional[str] = Field(
        default=None, description="Path to kubeconfig file (uses default if not set)"
    )
    kubeconfig_context: Optional[str] = Field(
        default=None, description="Kubernetes context to use"
    )
    namespace: str = Field(
        default="default", description="Kubernetes namespace for Jobs"
    )

    # Container settings
    image: str = Field(
        default="python:3.11-slim", description="Docker image to use for execution"
    )
    working_directory: str = Field(
        default="/app", description="Working directory inside the container"
    )

    # Resource limits
    cpu_requested: str = Field(
        default="200m", description="CPU request (e.g., '200m' = 0.2 CPU)"
    )
    cpu_limit: str = Field(
        default="500m", description="CPU limit (e.g., '500m' = 0.5 CPU)"
    )
    memory_requested: str = Field(
        default="256Mi", description="Memory request (e.g., '256Mi')"
    )
    memory_limit: str = Field(
        default="512Mi", description="Memory limit (e.g., '512Mi')"
    )

    # Security
    use_gvisor: bool = Field(
        default=False, description="Use gVisor runtime for sandboxing (requires GKE)"
    )
    run_as_user: int = Field(
        default=1001, description="User ID to run the container as"
    )
    run_as_non_root: bool = Field(
        default=True, description="Enforce non-root execution"
    )
    read_only_root_filesystem: bool = Field(
        default=True, description="Make root filesystem read-only"
    )

    # Cleanup
    ttl_seconds_after_finished: int = Field(
        default=600, description="Seconds to keep completed Jobs before cleanup"
    )

    # Environment
    environment: Dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to set in the container",
    )

    # Startup script (runs as InitContainer)
    startup_command: StartupCommandConfig = Field(
        default_factory=StartupCommandConfig,
        description="Optional startup script configuration (runs as InitContainer)",
    )


class CodeExecutorConfig(BaseModel):
    """Main configuration for the CodeExecutorTool."""

    tool_name: str = Field(
        description="The name of the tool as it will be invoked by the LLM"
    )
    tool_description: Optional[str] = Field(
        default="Execute Python code in a sandboxed environment",
        description="Description of what this tool does",
    )
    executor_type: ExecutorType = Field(
        default=ExecutorType.DOCKER, description="Type of executor to use"
    )
    default_timeout_seconds: int = Field(
        default=30, description="Default timeout for code execution in seconds"
    )
    max_output_size: int = Field(
        default=1048576,  # 1MB
        description="Maximum size of stdout/stderr output in bytes",
    )
    docker: DockerExecutorConfig = Field(
        default_factory=DockerExecutorConfig,
        description="Docker-specific configuration",
    )
    kubernetes: KubernetesExecutorConfig = Field(
        default_factory=KubernetesExecutorConfig,
        description="Kubernetes-specific configuration",
    )

    def get(self, key: str, default: Any = None) -> Any:
        """Allows dictionary-like access to the model's attributes."""
        return getattr(self, key, default)
