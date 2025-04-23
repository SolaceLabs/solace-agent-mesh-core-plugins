"""
Manages the lifecycle of an external A2A agent process launched by SAM.
Handles launching, monitoring, and restarting the process.
"""

import subprocess
import shlex
import platform
import threading
import os
from typing import Optional

from solace_ai_connector.common.log import log  # Use solace-ai-connector log


class A2AProcessManager:
    """
    Manages the lifecycle of an external A2A agent process.

    Handles launching the process specified by a command, monitoring its status,
    and optionally restarting it if it crashes.

    Attributes:
        command (Optional[str]): The command line string to launch the process.
        restart_on_crash (bool): Whether to attempt restarting the process on non-zero exit.
        agent_name (str): The name of the SAM agent instance for logging purposes.
        stop_event (threading.Event): Event used to signal termination to the monitor thread.
        process (Optional[subprocess.Popen]): The handle to the managed subprocess.
        monitor_thread (Optional[threading.Thread]): The thread monitoring the process.
    """

    def __init__(
        self,
        command: Optional[str],
        restart_on_crash: bool,
        agent_name: str,
        stop_event: threading.Event,
    ):
        """
        Initializes the A2AProcessManager.

        Args:
            command: The command line string to execute. If None, launch/monitor is disabled.
            restart_on_crash: If True, attempts to restart the process if it exits unexpectedly.
            agent_name: The name of the associated SAM agent for logging.
            stop_event: A threading.Event to signal termination.
        """
        self.command = command
        self.restart_on_crash = restart_on_crash
        self.agent_name = agent_name
        self.stop_event = stop_event
        self.process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        log.debug(
            "A2AProcessManager initialized for '%s'. Command: '%s', Restart: %s",
            self.agent_name,
            self.command,
            self.restart_on_crash,
        )

    def launch(self):
        """
        Launches the external A2A agent process using the configured command.

        Raises:
            FileNotFoundError: If the command executable is not found.
            Exception: For other errors during process launch.
        """
        if not self.command:
            log.warning(
                "No 'a2a_server_command' configured for '%s', cannot launch process.",
                self.agent_name,
            )
            return

        if self.process and self.process.poll() is None:
            log.warning(
                "A2A process (PID: %d) for '%s' seems to be already running.",
                self.process.pid,
                self.agent_name,
            )
            return

        log.info(
            "Launching A2A agent process for '%s' with command: %s",
            self.agent_name,
            self.command,
        )
        args = []  # Define args before try block
        try:
            # Use shlex.split for safer command parsing, especially with arguments
            args = shlex.split(self.command)
            popen_kwargs = {}
            # Ensure the child process runs independently, allowing SAM to exit cleanly
            if platform.system() == "Windows":
                # Creates a new process group, detaching from the parent console
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                # Starts the child in a new session with its own process group ID
                popen_kwargs["start_new_session"] = True

            # Redirect stdout/stderr to devnull to prevent blocking and keep SAM logs clean
            with open(os.devnull, "w", encoding="utf-8") as devnull:
                self.process = subprocess.Popen(
                    args, stdout=devnull, stderr=devnull, **popen_kwargs
                )
            log.info(
                "Launched A2A agent process for '%s' with PID: %d",
                self.agent_name,
                self.process.pid,
            )

        except FileNotFoundError:
            log.error(
                "Command not found for '%s': %s. "
                "Please ensure it's in the system PATH or provide the full path.",
                self.agent_name,
                args[0] if args else "<empty command>",
                exc_info=True,
            )
            self.process = None  # Ensure process is None on failure
            raise  # Re-raise the specific error for the component to handle
        except Exception as e:
            log.error(
                "Failed to launch A2A agent process for '%s': %s",
                self.agent_name,
                e,
                exc_info=True,
            )
            self.process = None  # Ensure process is None on failure
            raise  # Re-raise for the component

    def start_monitor(self):
        """
        Starts the monitoring thread if restart is enabled, a process exists,
        the thread isn't already running, and the stop event isn't set.
        """
        if (
            self.restart_on_crash
            and self.process
            and not self.monitor_thread  # Check if thread object exists
            and not self.stop_event.is_set()
        ):
            # Check if the existing thread object is actually alive before creating a new one
            # This handles cases where start_monitor might be called multiple times erroneously
            if self.monitor_thread and self.monitor_thread.is_alive():
                log.warning(
                    "Monitor thread for '%s' is already running.", self.agent_name
                )
                return

            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name=f"A2AMonitor-{self.agent_name}",  # Give the thread a name
                daemon=True,
            )
            self.monitor_thread.start()
            log.info("Started monitor thread for A2A process '%s'.", self.agent_name)
        elif not self.restart_on_crash:
            log.debug(
                "Restart on crash disabled for '%s', monitor not started.",
                self.agent_name,
            )
        elif not self.process:
            log.debug(
                "No process to monitor for '%s', monitor not started.", self.agent_name
            )

    def _monitor_loop(self):
        """
        Internal loop run by the monitor thread. Checks the process status
        and attempts restarts if configured and necessary.
        """
        log.info("Monitor thread running for '%s'.", self.agent_name)
        restart_delay = 2  # Seconds to wait before attempting restart
        max_restart_attempts = 5  # Limit consecutive restart attempts
        current_restart_attempts = 0

        while not self.stop_event.is_set():
            if not self.process:
                log.warning(
                    "Monitor thread (%s): No A2A process to monitor. Exiting.",
                    self.agent_name,
                )
                break

            try:
                return_code = self.process.poll()
            except Exception as poll_err:
                log.error(
                    "Error polling A2A process for '%s': %s. Stopping monitor.",
                    self.agent_name,
                    poll_err,
                    exc_info=True,
                )
                break  # Exit monitor loop on poll error

            if return_code is not None:  # Process has terminated
                log_func = log.info if return_code == 0 else log.error
                log_func(
                    "Managed A2A process (PID: %d) for '%s' terminated with code %d.",
                    self.process.pid,
                    self.agent_name,
                    return_code,
                )

                if (
                    self.restart_on_crash
                    and return_code != 0  # Only restart on non-zero exit code
                    and not self.stop_event.is_set()
                ):
                    current_restart_attempts += 1
                    if current_restart_attempts > max_restart_attempts:
                        log.error(
                            "Exceeded maximum restart attempts (%d) for '%s'. Stopping monitor.",
                            max_restart_attempts,
                            self.agent_name,
                        )
                        break

                    log.info(
                        "Attempting restart %d/%d for '%s' in %ds...",
                        current_restart_attempts,
                        max_restart_attempts,
                        self.agent_name,
                        restart_delay,
                    )
                    # Wait for the delay, but check stop_event frequently
                    if self.stop_event.wait(timeout=restart_delay):
                        log.info(
                            "Stop signal received during restart delay for '%s'. Aborting restart.",
                            self.agent_name,
                        )
                        break

                    try:
                        self.launch()  # Attempt to relaunch
                        # *** FIX START ***
                        # Check if launch succeeded AND the new process is running
                        if self.process and self.process.poll() is None:
                            log.info(
                                "A2A process for '%s' restarted successfully (New PID: %d).",
                                self.agent_name,
                                self.process.pid,
                            )
                            current_restart_attempts = (
                                0  # Reset attempts ONLY on successful restart AND running process
                            )
                            continue  # Continue monitoring the new process
                        elif self.process:
                            # Launch succeeded but process terminated immediately
                            log.error(
                                "Restarted A2A process for '%s' (PID: %d) terminated immediately. Continuing restart attempts.",
                                self.agent_name,
                                self.process.pid,
                            )
                            # Do NOT reset current_restart_attempts
                            # Do NOT continue; let the loop poll again
                        else:
                            # Launch failed and set self.process to None
                            log.error(
                                "Failed to restart A2A process for '%s' (launch returned no process). Stopping monitor.",
                                self.agent_name,
                            )
                            break # Stop monitoring if launch fails completely
                        # *** FIX END ***
                    except Exception as e:
                        log.error(
                            "Exception during A2A process restart for '%s': %s. Stopping monitor.",
                            self.agent_name,
                            e,
                            exc_info=True,
                        )
                        break  # Stop monitoring if restart fails critically
                else:
                    # Process exited cleanly or restart is disabled/aborted
                    log.info(
                        "Monitor loop for '%s' exiting as process terminated and restart is not applicable.",
                        self.agent_name,
                    )
                    break  # Exit monitor loop
            else:
                # Process is still running, reset restart attempts if they were > 0
                # This handles the case where a process might have crashed, restarted,
                # and is now running correctly.
                if current_restart_attempts > 0:
                    log.info("A2A process for '%s' is running after restart. Resetting attempt counter.", self.agent_name)
                    current_restart_attempts = 0

            # Wait for a longer interval or until stop_event is set
            if self.stop_event.wait(timeout=5):  # Check every 5 seconds
                log.info(
                    "Stop signal received by monitor thread for '%s'.", self.agent_name
                )
                break

        log.info("Stopping monitor thread for A2A process '%s'.", self.agent_name)

    def stop(self):
        """
        Stops the managed A2A process (if running) and the monitor thread.
        """
        log.info("Stopping A2AProcessManager for '%s'.", self.agent_name)
        # 1. Signal monitor thread to stop *first* to prevent restart attempts during shutdown
        self.stop_event.set()

        # 2. Terminate the process
        pid = None # Initialize pid
        if self.process:
            pid = self.process.pid  # Store PID for logging before process becomes None
            log.info(
                "Terminating managed A2A process (PID: %d) for '%s'...",
                pid,
                self.agent_name,
            )
            try:
                # Attempt graceful termination first
                self.process.terminate()
                try:
                    # Wait for a short period
                    self.process.wait(timeout=5)
                    log.info(
                        "Managed A2A process (PID: %d) for '%s' terminated gracefully.",
                        pid,
                        self.agent_name,
                    )
                except subprocess.TimeoutExpired:
                    # Force kill if graceful termination fails
                    log.warning(
                        "Managed A2A process (PID: %d) for '%s' did not terminate gracefully after 5s, killing.",
                        pid,
                        self.agent_name,
                    )
                    self.process.kill()
                    self.process.wait()  # Wait for kill to complete
                    log.info(
                        "Managed A2A process (PID: %d) for '%s' killed.",
                        pid,
                        self.agent_name,
                    )
            except Exception as e:
                # Catch potential errors during termination (e.g., process already died)
                log.error(
                    "Error terminating managed A2A process (PID: %s) for '%s': %s",
                    pid if pid else "unknown",
                    self.agent_name,
                    e,
                    exc_info=True,
                )
            finally:
                self.process = None  # Ensure process handle is cleared

        # 3. Join the monitor thread
        if self.monitor_thread and self.monitor_thread.is_alive():
            log.info("Waiting for monitor thread of '%s' to exit...", self.agent_name)
            self.monitor_thread.join(timeout=5)  # Wait for thread to finish
            if self.monitor_thread.is_alive():
                log.warning(
                    "Monitor thread for '%s' did not exit cleanly after 5s.",
                    self.agent_name,
                )
            else:
                log.info("Monitor thread for '%s' exited.", self.agent_name)
        self.monitor_thread = None  # Clear thread handle

        log.info("A2AProcessManager for '%s' stopped.", self.agent_name)

    def is_running(self) -> bool:
        """
        Checks if the managed process is currently running.

        Returns:
            True if the process exists and has not terminated, False otherwise.
        """
        return self.process is not None and self.process.poll() is None
