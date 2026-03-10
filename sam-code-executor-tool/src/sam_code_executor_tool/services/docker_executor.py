"""Docker container-based code executor implementation."""

import base64
import io
import logging
import tarfile
import uuid
from typing import Optional

import docker
from docker.errors import ImageNotFound

from .executor_base import BaseCodeExecutor
from .execution_models import (
    CodeExecutionInput,
    CodeExecutionResult,
    DockerExecutorConfig,
)

log = logging.getLogger(__name__)


class DockerCodeExecutor(BaseCodeExecutor):
    """
    Code executor that runs Python code in a Docker container.

    The container is created on initialization and persists across
    multiple code executions for efficiency. It is cleaned up when
    the tool's cleanup() method is called.
    """

    def __init__(self, config: DockerExecutorConfig):
        super().__init__(config)
        self._client: Optional[docker.DockerClient] = None
        self._container = None
        self._container_id: Optional[str] = None

    def initialize(self) -> None:
        """
        Create and start the Docker container.

        Steps:
        1. Connect to Docker daemon
        2. Pull image if not available
        3. Create container with security constraints
        4. Start container in detached mode
        5. Verify Python is available
        6. Execute optional startup script
        """
        log_identifier = "[DockerCodeExecutor:initialize]"
        log.info("%s Starting container initialization...", log_identifier)

        try:
            # Connect to Docker daemon
            self._client = docker.from_env()
            log.debug("%s Connected to Docker daemon", log_identifier)

            # Ensure image is available
            try:
                self._client.images.get(self.config.image)
                log.debug(
                    "%s Image '%s' found locally", log_identifier, self.config.image
                )
            except ImageNotFound:
                log.info(
                    "%s Pulling image '%s'...", log_identifier, self.config.image
                )
                self._client.images.pull(self.config.image)
                log.info("%s Image pulled successfully", log_identifier)

            # Create container with security constraints
            container_name = f"sam-code-executor-{uuid.uuid4().hex[:12]}"

            # Build container creation kwargs
            create_kwargs = {
                "image": self.config.image,
                "name": container_name,
                "detach": True,
                "tty": True,
                "stdin_open": True,  # Keep container running
                "working_dir": self.config.working_directory,
                "mem_limit": self.config.memory_limit,
                "network_disabled": self.config.network_disabled,
            }

            # Add CPU limit if specified
            if self.config.cpu_limit:
                create_kwargs["nano_cpus"] = int(self.config.cpu_limit * 1e9)

            # Add environment variables if specified
            if self.config.environment:
                create_kwargs["environment"] = self.config.environment

            # Add volumes if specified
            if self.config.volumes:
                create_kwargs["volumes"] = self.config.volumes

            self._container = self._client.containers.create(**create_kwargs)

            self._container_id = self._container.id
            log.debug(
                "%s Container created: %s", log_identifier, self._container_id[:12]
            )

            # Start the container
            self._container.start()
            log.debug("%s Container started", log_identifier)

            # Create working directory if it doesn't exist
            self._ensure_working_directory()

            # Verify Python is available
            self._verify_python()

            # Run optional startup script
            startup_config = self.config.startup_command
            if startup_config.enabled and startup_config.script:
                log.info(
                    "%s Running startup script (type=%s)...",
                    log_identifier,
                    startup_config.script_type,
                )
                self._run_startup_script(
                    startup_config.script,
                    startup_config.script_type,
                    startup_config.timeout_seconds,
                )

            self._initialized = True
            log.info(
                "%s Container initialized successfully: %s",
                log_identifier,
                container_name,
            )

        except Exception as e:
            log.exception("%s Failed to initialize container: %s", log_identifier, e)
            # Clean up partial state
            self._cleanup_container()
            raise RuntimeError(f"Docker executor initialization failed: {e}") from e

    def _ensure_working_directory(self) -> None:
        """Ensure the working directory exists in the container."""
        log_identifier = "[DockerCodeExecutor:ensure_workdir]"

        exit_code, output = self._container.exec_run(
            ["mkdir", "-p", self.config.working_directory], demux=True
        )

        if exit_code != 0:
            stderr = output[1].decode() if output[1] else ""
            log.warning(
                "%s Could not create working directory: %s", log_identifier, stderr
            )

    def _verify_python(self) -> None:
        """Verify Python is available in the container."""
        log_identifier = "[DockerCodeExecutor:verify_python]"

        exit_code, output = self._container.exec_run(
            ["python3", "--version"], demux=True
        )

        stdout = output[0].decode() if output[0] else ""
        stderr = output[1].decode() if output[1] else ""

        if exit_code != 0:
            raise RuntimeError(
                f"Python verification failed (exit code {exit_code}): {stderr or stdout}"
            )

        log.debug("%s Python available: %s", log_identifier, stdout.strip())

    def _run_startup_script(
        self, script: str, script_type: str, timeout_seconds: int
    ) -> None:
        """
        Execute a startup script in the container.

        Args:
            script: The inline script content
            script_type: Either "python" or "shell"
            timeout_seconds: Timeout for execution
        """
        log_identifier = "[DockerCodeExecutor:startup_script]"

        # Determine command based on script type
        if script_type == "python":
            cmd = ["python3", "-c", script]
        elif script_type == "shell":
            cmd = ["/bin/sh", "-c", script]
        else:
            raise RuntimeError(
                f"Unsupported startup script type: {script_type}. Use 'python' or 'shell'"
            )

        log.debug("%s Executing startup script...", log_identifier)

        try:
            exit_code, output = self._container.exec_run(
                cmd, demux=True, workdir=self.config.working_directory
            )
        except Exception as e:
            raise RuntimeError(f"Startup script execution error: {e}") from e

        stdout = output[0].decode() if output[0] else ""
        stderr = output[1].decode() if output[1] else ""

        if exit_code != 0:
            raise RuntimeError(
                f"Startup script failed (exit code {exit_code}):\n"
                f"stdout: {stdout}\nstderr: {stderr}"
            )

        log.info("%s Startup script completed successfully", log_identifier)
        if stdout:
            log.debug("%s Startup stdout: %s", log_identifier, stdout[:500])

    def _copy_bytes_to_container(self, content: bytes, container_path: str) -> None:
        """Copy bytes content to a file in the container using tar."""
        import os

        # Create a tar archive in memory
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tarinfo = tarfile.TarInfo(name=os.path.basename(container_path))
            tarinfo.size = len(content)
            tar.addfile(tarinfo, io.BytesIO(content))

        tar_stream.seek(0)

        # Put archive into container
        container_dir = os.path.dirname(container_path)
        self._container.put_archive(container_dir, tar_stream)

    def _get_file_from_container(self, container_path: str) -> bytes:
        """Get file content from container."""
        bits, _ = self._container.get_archive(container_path)

        # Extract from tar
        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)

        with tarfile.open(fileobj=tar_stream, mode="r") as tar:
            member = tar.getmembers()[0]
            f = tar.extractfile(member)
            return f.read() if f else b""

    def execute_code(
        self, execution_input: CodeExecutionInput, timeout_seconds: Optional[int] = None
    ) -> CodeExecutionResult:
        """
        Execute Python code in the container.

        Args:
            execution_input: The code and optional files to execute
            timeout_seconds: Override the default timeout

        Returns:
            CodeExecutionResult with stdout, stderr, exit_code
        """
        log_identifier = "[DockerCodeExecutor:execute]"

        if not self._initialized or not self._container:
            return CodeExecutionResult(
                success=False, error_message="Executor not initialized", exit_code=-1
            )

        execution_id = execution_input.execution_id or uuid.uuid4().hex

        log.debug("%s Starting execution %s", log_identifier, execution_id)

        try:
            # Refresh container reference
            self._container.reload()

            # Check container is running
            if self._container.status != "running":
                return CodeExecutionResult(
                    success=False,
                    error_message=f"Container not running (status: {self._container.status})",
                    exit_code=-1,
                    execution_id=execution_id,
                )

            # Copy input files if provided
            if execution_input.input_files:
                for input_file in execution_input.input_files:
                    content = base64.b64decode(input_file.content)
                    dest_path = (
                        f"{self.config.working_directory}/{input_file.filename}"
                    )
                    self._copy_bytes_to_container(content, dest_path)
                    log.debug(
                        "%s Copied input file: %s", log_identifier, input_file.filename
                    )

            # Execute the code
            exec_kwargs = {
                "demux": True,
                "workdir": self.config.working_directory,
            }

            exit_code, output = self._container.exec_run(
                ["python3", "-c", execution_input.code], **exec_kwargs
            )

            stdout = output[0].decode() if output[0] else ""
            stderr = output[1].decode() if output[1] else ""

            log.debug(
                "%s Execution %s completed with exit code %d",
                log_identifier,
                execution_id,
                exit_code,
            )

            return CodeExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                success=(exit_code == 0),
                execution_id=execution_id,
                error_message=stderr if exit_code != 0 else None,
            )

        except Exception as e:
            log.exception("%s Execution failed: %s", log_identifier, e)
            return CodeExecutionResult(
                success=False,
                error_message=str(e),
                exit_code=-1,
                execution_id=execution_id,
            )

    def cleanup(self) -> None:
        """Stop and remove the container."""
        log_identifier = "[DockerCodeExecutor:cleanup]"
        log.info("%s Cleaning up container...", log_identifier)
        self._cleanup_container()
        self._initialized = False
        log.info("%s Cleanup complete", log_identifier)

    def _cleanup_container(self) -> None:
        """Internal method to stop and remove container."""
        if self._container:
            try:
                self._container.stop(timeout=10)
            except Exception as e:
                log.warning("Error stopping container: %s", e)

            try:
                self._container.remove(force=True)
            except Exception as e:
                log.warning("Error removing container: %s", e)

            self._container = None
            self._container_id = None

        if self._client:
            try:
                self._client.close()
            except Exception as e:
                log.warning("Error closing Docker client: %s", e)
            self._client = None

    def is_healthy(self) -> bool:
        """Check if the container is running and healthy."""
        if not self._initialized or not self._container:
            return False

        try:
            self._container.reload()
            return self._container.status == "running"
        except Exception:
            return False
