"""
Manages the lifecycle of an external A2A agent process launched by SAM.
Handles launching, monitoring, and restarting the process.
"""

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
        logger.debug(f"A2AProcessManager initialized for '{agent_name}'. Command: '{command}', Restart: {restart_on_crash}")

    def launch(self):
        """
        Launches the external A2A agent process using the configured command.

        Raises:
            FileNotFoundError: If the command executable is not found.
            Exception: For other errors during process launch.
        """
        if not self.command:
            logger.warning(f"No 'a2a_server_command' configured for '{self.agent_name}', cannot launch process.")
            return

        if self.process and self.process.poll() is None:
            logger.warning(
                f"A2A process (PID: {self.process.pid}) for '{self.agent_name}' seems to be already running."
            )
            return

        logger.info(f"Launching A2A agent process for '{self.agent_name}' with command: {self.command}")
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
            logger.info(f"Launched A2A agent process for '{self.agent_name}' with PID: {self.process.pid}")

        except FileNotFoundError:
            logger.error(
                f"Command not found for '{self.agent_name}': {args[0]}. "
                "Please ensure it's in the system PATH or provide the full path.",
                exc_info=True,
            )
            self.process = None # Ensure process is None on failure
            raise # Re-raise the specific error for the component to handle
        except Exception as e:
            logger.error(f"Failed to launch A2A agent process for '{self.agent_name}': {e}", exc_info=True)
            self.process = None # Ensure process is None on failure
            raise # Re-raise for the component

    def start_monitor(self):
        """
        Starts the monitoring thread if restart is enabled, a process exists,
        the thread isn't already running, and the stop event isn't set.
        """
        if (
            self.restart_on_crash
            and self.process
            and not self.monitor_thread # Check if thread object exists
            and not self.stop_event.is_set()
        ):
            # Check if the existing thread object is actually alive before creating a new one
            # This handles cases where start_monitor might be called multiple times erroneously
            if self.monitor_thread and self.monitor_thread.is_alive():
                 logger.warning(f"Monitor thread for '{self.agent_name}' is already running.")
                 return

            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name=f"A2AMonitor-{self.agent_name}", # Give the thread a name
                daemon=True
            )
            self.monitor_thread.start()
            logger.info(f"Started monitor thread for A2A process '{self.agent_name}'.")
        elif not self.restart_on_crash:
             logger.debug(f"Restart on crash disabled for '{self.agent_name}', monitor not started.")
        elif not self.process:
             logger.debug(f"No process to monitor for '{self.agent_name}', monitor not started.")


    def _monitor_loop(self):
        """
        Internal loop run by the monitor thread. Checks the process status
        and attempts restarts if configured and necessary.
        """
        logger.info(f"Monitor thread running for '{self.agent_name}'.")
        restart_delay = 2 # Seconds to wait before attempting restart
        max_restart_attempts = 5 # Limit consecutive restart attempts
        current_restart_attempts = 0

        while not self.stop_event.is_set():
            if not self.process:
                logger.warning(f"Monitor thread ({self.agent_name}): No A2A process to monitor. Exiting.")
                break

            try:
                return_code = self.process.poll()
            except Exception as poll_err:
                 logger.error(f"Error polling A2A process for '{self.agent_name}': {poll_err}. Stopping monitor.", exc_info=True)
                 break # Exit monitor loop on poll error

            if return_code is not None: # Process has terminated
                log_func = logger.info if return_code == 0 else logger.error
                log_func(
                    f"Managed A2A process (PID: {self.process.pid}) for '{self.agent_name}' terminated with code {return_code}."
                )

                if (
                    self.restart_on_crash
                    and return_code != 0 # Only restart on non-zero exit code
                    and not self.stop_event.is_set()
                ):
                    current_restart_attempts += 1
                    if current_restart_attempts > max_restart_attempts:
                         logger.error(f"Exceeded maximum restart attempts ({max_restart_attempts}) for '{self.agent_name}'. Stopping monitor.")
                         break

                    logger.info(f"Attempting restart {current_restart_attempts}/{max_restart_attempts} for '{self.agent_name}' in {restart_delay}s...")
                    # Wait for the delay, but check stop_event frequently
                    if self.stop_event.wait(timeout=restart_delay):
                        logger.info(f"Stop signal received during restart delay for '{self.agent_name}'. Aborting restart.")
                        break

                    try:
                        self.launch() # Attempt to relaunch
                        if self.process: # Check if launch was successful
                            logger.info(f"A2A process for '{self.agent_name}' restarted successfully (New PID: {self.process.pid}).")
                            current_restart_attempts = 0 # Reset attempts on successful restart
                            continue # Continue monitoring the new process
                        else:
                            # Launch might have failed and set self.process to None
                            logger.error(f"Failed to restart A2A process for '{self.agent_name}' (launch returned no process). Stopping monitor.")
                            break
                    except Exception as e:
                        logger.error(
                            f"Exception during A2A process restart for '{self.agent_name}': {e}. Stopping monitor.",
                            exc_info=True,
                        )
                        break # Stop monitoring if restart fails critically
                else:
                    # Process exited cleanly or restart is disabled/aborted
                    logger.info(f"Monitor loop for '{self.agent_name}' exiting as process terminated and restart is not applicable.")
                    break # Exit monitor loop
            else:
                 # Process is still running, reset restart attempts
                 current_restart_attempts = 0

            # Wait for a longer interval or until stop_event is set
            if self.stop_event.wait(timeout=5): # Check every 5 seconds
                logger.info(f"Stop signal received by monitor thread for '{self.agent_name}'.")
                break

        logger.info(f"Stopping monitor thread for A2A process '{self.agent_name}'.")

    def stop(self):
        """
        Stops the managed A2A process (if running) and the monitor thread.
        """
        logger.info(f"Stopping A2AProcessManager for '{self.agent_name}'.")
        # 1. Signal monitor thread to stop *first* to prevent restart attempts during shutdown
        self.stop_event.set()

        # 2. Terminate the process
        if self.process:
            pid = self.process.pid # Store PID for logging before process becomes None
            logger.info(
                f"Terminating managed A2A process (PID: {pid}) for '{self.agent_name}'..."
            )
            try:
                # Attempt graceful termination first
                self.process.terminate()
                try:
                    # Wait for a short period
                    self.process.wait(timeout=5)
                    logger.info(f"Managed A2A process (PID: {pid}) for '{self.agent_name}' terminated gracefully.")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful termination fails
                    logger.warning(
                        f"Managed A2A process (PID: {pid}) for '{self.agent_name}' did not terminate gracefully after 5s, killing."
                    )
                    self.process.kill()
                    self.process.wait() # Wait for kill to complete
                    logger.info(f"Managed A2A process (PID: {pid}) for '{self.agent_name}' killed.")
            except Exception as e:
                # Catch potential errors during termination (e.g., process already died)
                logger.error(
                    f"Error terminating managed A2A process (PID: {pid}) for '{self.agent_name}': {e}", exc_info=True
                )
            finally:
                 self.process = None # Ensure process handle is cleared

        # 3. Join the monitor thread
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.info(f"Waiting for monitor thread of '{self.agent_name}' to exit...")
            self.monitor_thread.join(timeout=5) # Wait for thread to finish
            if self.monitor_thread.is_alive():
                logger.warning(f"Monitor thread for '{self.agent_name}' did not exit cleanly after 5s.")
            else:
                logger.info(f"Monitor thread for '{self.agent_name}' exited.")
        self.monitor_thread = None # Clear thread handle

        logger.info(f"A2AProcessManager for '{self.agent_name}' stopped.")

    def is_running(self) -> bool:
        """
        Checks if the managed process is currently running.

        Returns:
            True if the process exists and has not terminated, False otherwise.
        """
        return self.process is not None and self.process.poll() is None
