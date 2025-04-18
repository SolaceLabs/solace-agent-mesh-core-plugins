import subprocess
import shlex
import platform
import threading
import time
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class A2AProcessManager:
    """Manages the lifecycle of an external A2A agent process."""

    def __init__(
        self,
        command: Optional[str],
        restart_on_crash: bool,
        agent_name: str,
        stop_event: threading.Event,
    ):
        self.command = command
        self.restart_on_crash = restart_on_crash
        self.agent_name = agent_name
        self.stop_event = stop_event
        self.process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None

    def launch(self):
        """Launches the external A2A agent process."""
        if not self.command:
            logger.warning("No 'a2a_server_command' configured, cannot launch process.")
            return

        if self.process and self.process.poll() is None:
            logger.warning(
                f"A2A process (PID: {self.process.pid}) seems to be already running."
            )
            return

        logger.info(f"Launching A2A agent process with command: {self.command}")
        try:
            args = shlex.split(self.command)
            popen_kwargs = {}
            if platform.system() == "Windows":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True

            with open(os.devnull, "w", encoding="utf-8") as devnull:
                self.process = subprocess.Popen(
                    args, stdout=devnull, stderr=devnull, **popen_kwargs
                )
            logger.info(f"Launched A2A agent process with PID: {self.process.pid}")

        except FileNotFoundError:
            logger.error(
                f"Command not found: {args[0]}. Please ensure it's in the system PATH or provide the full path.",
                exc_info=True,
            )
            self.process = None
            raise
        except Exception as e:
            logger.error(f"Failed to launch A2A agent process: {e}", exc_info=True)
            self.process = None
            raise

    def start_monitor(self):
        """Starts the monitoring thread if restart is enabled and process exists."""
        if (
            self.restart_on_crash
            and self.process
            and not self.monitor_thread
            and not self.stop_event.is_set()
        ):
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True
            )
            self.monitor_thread.start()
            logger.info(f"Started monitor thread for A2A process '{self.agent_name}'.")

    def _monitor_loop(self):
        """Monitors the managed A2A process and restarts it if configured."""
        logger.debug(f"Monitor thread running for '{self.agent_name}'.")
        while not self.stop_event.is_set():
            if not self.process:
                logger.warning("Monitor thread: No A2A process to monitor. Exiting.")
                break

            return_code = self.process.poll()

            if return_code is not None:
                log_func = logger.info if return_code == 0 else logger.error
                log_func(
                    f"Managed A2A process (PID: {self.process.pid}) terminated with code {return_code}."
                )

                if (
                    self.restart_on_crash
                    and return_code != 0
                    and not self.stop_event.is_set()
                ):
                    logger.info("Attempting to restart the A2A process...")
                    if self.stop_event.wait(2):  # Wait a moment before restarting
                        break

                    try:
                        self.launch()
                        if not self.process:
                            logger.error(
                                "Failed to restart A2A process. Stopping monitor."
                            )
                            break
                        logger.info("A2A process restarted successfully.")
                        continue
                    except Exception as e:
                        logger.error(
                            f"Exception during A2A process restart: {e}. Stopping monitor.",
                            exc_info=True,
                        )
                        break
                else:
                    break

            if self.stop_event.wait(timeout=5):
                break

        logger.info(f"Stopping monitor thread for A2A process '{self.agent_name}'.")

    def stop(self):
        """Stops the managed process and the monitor thread."""
        logger.debug(f"Stopping A2AProcessManager for '{self.agent_name}'.")
        # Signal monitor thread first
        self.stop_event.set()

        if self.process:
            logger.info(
                f"Terminating managed A2A process (PID: {self.process.pid})..."
            )
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                    logger.info("Managed A2A process terminated gracefully.")
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Managed A2A process did not terminate gracefully after 5s, killing."
                    )
                    self.process.kill()
                    self.process.wait()
                    logger.info("Managed A2A process killed.")
            except Exception as e:
                logger.error(
                    f"Error terminating managed A2A process: {e}", exc_info=True
                )
            self.process = None

        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.info("Waiting for monitor thread to exit...")
            self.monitor_thread.join(timeout=5)
            if self.monitor_thread.is_alive():
                logger.warning("Monitor thread did not exit cleanly.")
            else:
                logger.info("Monitor thread exited.")
            self.monitor_thread = None
        logger.debug(f"A2AProcessManager for '{self.agent_name}' stopped.")

    def is_running(self) -> bool:
        """Checks if the managed process is currently running."""
        return self.process is not None and self.process.poll() is None
