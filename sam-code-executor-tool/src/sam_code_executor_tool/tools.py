"""DynamicTool implementation for code execution."""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from google.genai import types as adk_types
from google.adk.tools import ToolContext
from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from solace_agent_mesh.agent.sac.component import SamAgentComponent
from solace_agent_mesh.agent.utils.artifact_helpers import (
    save_artifact_with_metadata,
    ensure_correct_extension,
    get_original_session_id,
)

from .services.execution_models import (
    CodeExecutorConfig,
    CodeExecutionInput,
    ExecutorType,
)
from .services.executor_base import BaseCodeExecutor
from .services.docker_executor import DockerCodeExecutor
from .services.kubernetes_executor import KubernetesCodeExecutor

log = logging.getLogger(__name__)


class CodeExecutorTool(DynamicTool):
    """
    A dynamic tool that executes Python code in a sandboxed environment.

    This tool creates a persistent execution environment (e.g., Docker container)
    on initialization and reuses it for multiple code executions, providing
    efficient and isolated code execution.
    """

    config_model = CodeExecutorConfig

    def __init__(self, tool_config: CodeExecutorConfig):
        super().__init__(tool_config)
        self._executor: Optional[BaseCodeExecutor] = None
        self._executor_healthy: bool = False
        self._executor_error: Optional[str] = None

    @property
    def tool_name(self) -> str:
        """Return the function name that the LLM will call."""
        return self.tool_config.get("tool_name", "code_executor")

    @property
    def tool_description(self) -> str:
        """Return the description, including health status."""
        base_description = self.tool_config.get(
            "tool_description", "Execute Python code in a sandboxed environment"
        )

        if not self._executor_healthy:
            status_message = "\n\nWARNING: Code executor is currently UNAVAILABLE.\n"
            if self._executor_error:
                status_message += f"Error: {self._executor_error}\n"
            status_message += (
                "Code execution requests will fail until the executor is restored."
            )
            return f"{base_description}{status_message}"

        return f"{base_description}\n\nCode Executor: READY"

    @property
    def parameters_schema(self) -> adk_types.Schema:
        """Define the parameters the LLM can pass to this tool."""
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "code": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="The Python code to execute",
                ),
                "timeout_seconds": adk_types.Schema(
                    type=adk_types.Type.INTEGER,
                    description="Optional timeout in seconds (uses default if not specified)",
                ),
                "save_output_as_artifact": adk_types.Schema(
                    type=adk_types.Type.BOOLEAN,
                    description="If true, save the output as an artifact",
                ),
                "output_filename": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Filename for the output artifact (required if save_output_as_artifact is true)",
                ),
            },
            required=["code"],
        )

    async def init(self, component: SamAgentComponent, tool_config: Dict):
        """
        Initialize the code executor.

        Creates the execution environment (e.g., Docker container) and
        optionally runs startup commands.
        """
        log_identifier = f"[{self.tool_name}:init]"
        log.info("%s Initializing code executor...", log_identifier)

        executor_type = self.tool_config.executor_type

        try:
            # Create the appropriate executor based on type
            if executor_type == ExecutorType.DOCKER:
                self._executor = DockerCodeExecutor(self.tool_config.docker)
            elif executor_type == ExecutorType.KUBERNETES:
                self._executor = KubernetesCodeExecutor(self.tool_config.kubernetes)
            else:
                raise ValueError(f"Unsupported executor type: {executor_type}")

            # Initialize the executor (creates container, runs startup commands)
            self._executor.initialize()

            self._executor_healthy = True
            self._executor_error = None
            log.info("%s Code executor initialized successfully", log_identifier)

        except Exception as e:
            self._executor_healthy = False
            self._executor_error = (
                f"Initialization failed: {type(e).__name__}: {str(e)}"
            )
            log.error(
                "%s Failed to initialize executor: %s. Tool will be marked as unavailable.",
                log_identifier,
                e,
            )
            log.warning(
                "%s Tool '%s' initialized in DEGRADED mode.", log_identifier, self.tool_name
            )

    async def cleanup(self, component: SamAgentComponent, tool_config: Dict):
        """
        Clean up the code executor.

        Stops and removes the execution environment.
        """
        log_identifier = f"[{self.tool_name}:cleanup]"
        log.info("%s Cleaning up code executor...", log_identifier)

        if self._executor:
            try:
                self._executor.cleanup()
            except Exception as e:
                log.error("%s Error during cleanup: %s", log_identifier, e)

        self._executor = None
        self._executor_healthy = False
        log.info("%s Code executor cleanup complete", log_identifier)

    async def _save_output_artifact(
        self, tool_context: ToolContext, stdout: str, filename: str, execution_id: str, exit_code: int
    ) -> Optional[Dict[str, Any]]:
        """Save execution output as an artifact."""
        log_identifier = f"[{self.tool_name}:save_artifact]"

        try:
            inv_context = tool_context._invocation_context
            artifact_service = inv_context.artifact_service

            if not artifact_service:
                log.warning("%s Artifact service not available", log_identifier)
                return None

            content_bytes = stdout.encode("utf-8")

            save_result = await save_artifact_with_metadata(
                artifact_service=artifact_service,
                app_name=inv_context.app_name,
                user_id=inv_context.user_id,
                session_id=get_original_session_id(inv_context),
                filename=ensure_correct_extension(filename, "txt"),
                content_bytes=content_bytes,
                mime_type="text/plain",
                metadata_dict={
                    "source": "code_executor",
                    "tool_name": self.tool_name,
                    "exit_code": exit_code,
                    "execution_id": execution_id,
                },
                timestamp=datetime.now(timezone.utc),
                tool_context=tool_context,
            )

            log.debug("%s Artifact saved: %s", log_identifier, save_result)
            return save_result

        except Exception as e:
            log.error("%s Failed to save artifact: %s", log_identifier, e)
            return {"status": "error", "message": str(e)}

    async def _run_async_impl(
        self, args: Dict[str, Any], tool_context: ToolContext = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Execute the provided code.

        Args:
            args: Dictionary containing 'code' and optional parameters
            tool_context: The tool context for artifact operations

        Returns:
            Dictionary with execution results or error information
        """
        log_identifier = f"[{self.tool_name}:run]"

        code = args.get("code")
        timeout = args.get("timeout_seconds", self.tool_config.default_timeout_seconds)
        save_artifact = args.get("save_output_as_artifact", False)
        output_filename = args.get("output_filename", "execution_output.txt")

        if not code:
            return {"error": "No code provided to execute"}

        if not self._executor:
            return {
                "error": f"Code executor '{self.tool_name}' is not available. "
                f"Executor failed to initialize."
            }

        if not self._executor_healthy:
            # Try to recover
            if not self._executor.is_healthy():
                return {
                    "error": f"Code executor '{self.tool_name}' is not healthy. "
                    f"{self._executor_error or 'Please try again later.'}"
                }
            else:
                # Recovery detected
                self._executor_healthy = True
                self._executor_error = None
                log.info("%s Executor recovered", log_identifier)

        log.info("%s Executing code (timeout=%ds)", log_identifier, timeout)

        try:
            execution_input = CodeExecutionInput(code=code, timeout_seconds=timeout)

            result = self._executor.execute_code(execution_input, timeout)

            response = {
                "status": "success" if result.success else "error",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "execution_id": result.execution_id,
            }

            if not result.success:
                response["error"] = result.error_message or "Execution failed"

            # Save artifact if requested
            if save_artifact and tool_context and result.stdout:
                artifact_result = await self._save_output_artifact(
                    tool_context,
                    result.stdout,
                    output_filename,
                    result.execution_id,
                    result.exit_code,
                )
                if artifact_result:
                    response["artifact"] = artifact_result

            return response

        except Exception as e:
            # Mark executor as unhealthy
            was_healthy = self._executor_healthy
            self._executor_healthy = False
            self._executor_error = f"Execution error: {type(e).__name__}: {str(e)}"

            if was_healthy:
                log.error("%s Executor became unhealthy: %s", log_identifier, e)

            return {"status": "error", "error": str(e)}
