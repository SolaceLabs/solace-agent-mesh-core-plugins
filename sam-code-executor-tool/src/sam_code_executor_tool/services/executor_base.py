"""Abstract base class for code execution backends."""

from abc import ABC, abstractmethod
from typing import Optional
import logging

from .execution_models import CodeExecutionInput, CodeExecutionResult, DockerExecutorConfig

log = logging.getLogger(__name__)


class BaseCodeExecutor(ABC):
    """Abstract base class for code execution backends."""

    def __init__(self, config: DockerExecutorConfig):
        """
        Initialize the executor with configuration.

        Args:
            config: Configuration specific to the executor type
        """
        self.config = config
        self._initialized: bool = False

    @property
    def initialized(self) -> bool:
        """Check if the executor has been initialized."""
        return self._initialized

    @abstractmethod
    def initialize(self) -> None:
        """
        Initialize the execution environment.

        For Docker: Creates and starts the container.
        Should be called once before execute_code().

        Raises:
            RuntimeError: If initialization fails
        """
        pass

    @abstractmethod
    def execute_code(
        self, execution_input: CodeExecutionInput, timeout_seconds: Optional[int] = None
    ) -> CodeExecutionResult:
        """
        Execute code in the sandboxed environment.

        Args:
            execution_input: The code and optional files to execute
            timeout_seconds: Override the default timeout

        Returns:
            CodeExecutionResult with stdout, stderr, exit_code, and output_files
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """
        Clean up resources used by the executor.

        For Docker: Stops and removes the container.
        Should be called when the tool is being destroyed.
        """
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """
        Check if the executor is in a healthy state.

        Returns:
            True if the executor is ready to accept code, False otherwise
        """
        pass

    def _run_startup_script(
        self, script: str, script_type: str, timeout_seconds: int
    ) -> None:
        """
        Execute a startup script in the execution environment.

        This hook allows running initialization scripts (python or shell)
        when the executor is first created.

        Args:
            script: The inline script content
            script_type: Either "python" or "shell"
            timeout_seconds: Timeout for the startup script

        Raises:
            RuntimeError: If the startup script fails
        """
        # Default implementation does nothing; subclasses override
        log.debug("Startup script execution not implemented for this executor")
