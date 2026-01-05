import json
import subprocess
import logging
from pathlib import Path

from sam_sql_analytics_db_tool.subprocess.bootstrap import (
    ensure_runtime_ready,
)

log = logging.getLogger(__name__)


class AnalyticsSubprocessManager:
    """
    Controls the isolated subprocess venv + executes runtime scripts.
    """

    def __init__(self):
        self._venv_path = None   # set after initialize_env()

    # --------------------------------------------------------------
    # Helpers
    # --------------------------------------------------------------

    def _python(self) -> str:
        py = self._venv_path / "bin" / "python"
        if not py.exists():
            raise RuntimeError(f"python missing in venv: {py}")
        return str(py)

    def _run(self, cmd: list[str]) -> str:
        proc = subprocess.run(
            cmd, text=True, capture_output=True,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"Subprocess failed:\n"
                f"CMD: {' '.join(cmd)}\n"
                f"STDOUT:\n{proc.stdout}\n"
                f"STDERR:\n{proc.stderr}"
            )

        return proc.stdout

    # --------------------------------------------------------------
    # Initialization
    # --------------------------------------------------------------

    def initialize_env(self, connection_string: str):
        log.info("Preparing runtime environment...")
        self._venv_path = ensure_runtime_ready(connection_string)
        log.info("Runtime venv ready: %s", self._venv_path)

    # --------------------------------------------------------------
    # Operations
    # --------------------------------------------------------------

    def run_discovery(self, dsn: str) -> dict:
        if self._venv_path is None:
            self.initialize_env(dsn)

        script = self._venv_path / "runtime" / "run_discovery.py"

        output = self._run([
            self._python(),
            str(script),
            dsn,
        ])

        return json.loads(output)

    def run_profiling(self, dsn: str) -> dict:
        if self._venv_path is None:
            self.initialize_env(dsn)

        script = self._venv_path / "runtime" / "run_profiling.py"

        output = self._run([
            self._python(),
            str(script),
            dsn,
        ])

        return json.loads(output)

    def run_combined(self, dsn: str) -> dict:
        """
        Run both discovery and profiling in parallel in a single subprocess.
        Optimizes first-run by avoiding duplicate subprocess overhead.

        Returns:
            dict with "discovery" and "profiling" keys
        """
        if self._venv_path is None:
            self.initialize_env(dsn)

        script = self._venv_path / "runtime" / "run_combined.py"

        output = self._run([
            self._python(),
            str(script),
            dsn,
        ])

        # Subprocess outputs JSON on last line of stdout (pip messages may appear above)
        lines = output.strip().splitlines()
        if not lines:
            raise RuntimeError("Subprocess returned empty output")

        json_output = lines[-1]

        try:
            return json.loads(json_output)
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse JSON from last line. Content: {json_output[:500]}")
            raise RuntimeError(f"Invalid JSON from subprocess: {e}") from e
