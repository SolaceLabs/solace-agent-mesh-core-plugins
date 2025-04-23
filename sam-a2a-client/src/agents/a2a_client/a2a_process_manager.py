"""
Manages the lifecycle of an external A2A agent process launched by SAM.
Handles launching, monitoring, and restarting the process.
"""

import subprocess
import shlex
import platform
import threading
import os
from typing import Optional, Dict
from dotenv import dotenv_values

from solace_ai_connector.common.log import log  # Use solace-ai-connector log


class A2AProcessManager:
    """
    Manages the lifecycle of an external A2A agent process.

    Handles launching the process specified by a command, monitoring its status,
    and optionally restarting it if it crashes.

    Attributes:
        command (Optional[str]): The command line string to launch the process.
        working_dir (Optional[str]): The working directory for the command.
        env_file (Optional[str]): Path to the .env file for the command environment.
        restart_on_crash (bool): Whether to attempt restarting the process on non-zero exit.
        agent_name (str): The name of the SAM agent instance for logging purposes.
        stop_event (threading.Event): Event used to signal termination to the monitor thread.
        process (Optional[subprocess.Popen]): The handle to the managed subprocess.
        monitor_thread (Optional[threading.Thread]): The thread monitoring the process.
    """

    def __init__(
        self,
        command: Optional[str],
        working_dir: Optional[str],
        env_file: Optional[str],
        restart_on_crash: bool,
        agent_name: str,
        stop_event: threading.Event,
    ):
        """
        Initializes the A2AProcessManager.

        Args:
            command: The command line string to execute. If None, launch/monitor is disabled.
            working_dir: Optional working directory for the command.
            env_file: Optional path to a .env file to load environment variables from.
            restart_on_crash: If True, attempts to restart the process if it exits unexpectedly.
            agent_name: The name of the associated SAM agent for logging.
            stop_event: A threading.Event to signal termination.
        """
        self.command = command
        self.working_dir = working_dir
        self.env_file = env_file
        self.restart_on_crash = restart_on_crash
        self.agent_name = agent_name
        self.stop_event = stop_event
        self.process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        log.debug(
            "A2AProcessManager initialized for '%s'. Command: '%s', WD: '%s', EnvFile: '%s', Restart: %s",
            self.agent_name,
            self.command,
            self.working_dir,
            self.env_file,
            self.restart_on_crash,
        )

    def _load_env_vars(self) -> Optional[Dict[str, str]]:
        """Loads environment variables from the specified .env file."""
        if not self.env_file:
            return None

        if not os.path.exists(self.env_file):
            log.warning(
                "Environment file '%s' specified for agent '%s' does not exist. Skipping.",
                self.env_file,
                self.agent_name,
            )
            return None

        try:
            log.debug(
                "Loading environment variables from '%s' for agent '%s'.",
                self.env_file,
                self.agent_name,
            )
            # dotenv_values doesn't modify os.environ, it just returns a dict
            loaded_vars = dotenv_values(self.env_file)
            # Merge with current environment, giving precedence to loaded vars
            merged_env = os.environ.copy()
            merged_env.update(loaded_vars)
            log.debug(
                "Loaded %d variables from '%s'.", len(loaded_vars), self.env_file
            )
            return merged_env
        except Exception as e:
            log.error(
                "Failed to load environment variables from '%s' for agent '%s': %s",
                self.env_file,
                self.agent_name,
                e,
                exc_info=True,
            )
            return None # Return None on error, Popen will use default env

    def launch(self):
        """
        Launches the external A2A agent process using the configured command,
        working directory, and environment file. Captures stderr.

        Raises:
            FileNotFoundError: If the command executable is not found or working_dir is invalid.
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
        if self.working_dir:
            log.info("  Working Directory: %s", self.working_dir)
        if self.env_file:
            log.info("  Environment File: %s", self.env_file)

        args = []  # Define args before try block
        try:
            # Use shlex.split for safer command parsing, especially with arguments
            args = shlex.split(self.command)

            # Prepare Popen arguments
            popen_kwargs = {}
            # Set working directory if specified
            if self.working_dir:
                if not os.path.isdir(self.working_dir): # First call to isdir
                     raise FileNotFoundError(f"Specified working directory does not exist or is not a directory: {self.working_dir}")
                popen_kwargs["cwd"] = self.working_dir

            # Load and set environment variables if specified
            process_env = self._load_env_vars()
            if process_env is not None:
                popen_kwargs["env"] = process_env
            # If _load_env_vars returned None due to error or no file, Popen uses default env

            # Ensure the child process runs independently, allowing SAM to exit cleanly
            if platform.system() == "Windows":
                # Creates a new process group, detaching from the parent console
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                # Starts the child in a new session with its own process group ID
                popen_kwargs["start_new_session"] = True

            # Redirect stdout to devnull, capture stderr
            with open(os.devnull, "w", encoding="utf-8") as devnull:
                popen_kwargs["stdout"] = devnull
                popen_kwargs["stderr"] = subprocess.PIPE # Capture stderr
                # Set text mode for stderr for easier decoding
                popen_kwargs["text"] = True
                popen_kwargs["encoding"] = 'utf-8'
                popen_kwargs["errors"] = 'replace' # Handle potential decoding errors

                self.process = subprocess.Popen(args, **popen_kwargs)

            log.info(
                "Launched A2A agent process for '%s' with PID: %d",
                self.agent_name,
                self.process.pid,
            )

        except FileNotFoundError as e:
            # Check if the error message indicates the working directory was the cause
            # This relies on the specific error message raised above.
            if self.working_dir and str(e).startswith("Specified working directory"):
                 log_msg = f"Invalid working directory for '%s': %s."
                 log_args = (self.agent_name, self.working_dir)
            # Otherwise, assume the command was not found
            else:
                 log_msg = "Command not found for '%s': %s. Please ensure it's in the system PATH or provide the full path."
                 log_args = (self.agent_name, args[0] if args else "<empty command>")

            log.error(log_msg, *log_args, exc_info=True)
            self.process = None  # Ensure process is None on failure
            # Re-raise with the specific message determined above
            raise FileNotFoundError(log_msg % log_args) from e
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
        Internal loop run by the monitor thread. Checks the process status,
        captures stderr on error, and attempts restarts if configured and necessary.
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
                stderr_output = ""
                try:
                    # Read stderr output now that the process has terminated
                    # communicate() is safer as it waits for the process and reads all output
                    # Use a timeout to prevent potential hangs
                    stdout_data, stderr_data = self.process.communicate(timeout=5)
                    if stderr_data:
                        stderr_output = stderr_data.strip()
                        # Limit captured output length for logging
                        max_stderr_len = 1024
                        if len(stderr_output) > max_stderr_len:
                            stderr_output = stderr_output[:max_stderr_len] + "... (truncated)"
                except subprocess.TimeoutExpired:
                    log.warning("Timeout reading stderr from terminated process for '%s'.", self.agent_name)
                    stderr_output = "[Timeout reading stderr]"
                except Exception as comm_err:
                    log.warning("Error reading stderr from terminated process for '%s': %s", self.agent_name, comm_err)
                    stderr_output = "[Error reading stderr]"

                log_func = log.info if return_code == 0 else log.error
                log_msg = "Managed A2A process (PID: %d) for '%s' terminated with code %d."
                log_args = [self.process.pid, self.agent_name, return_code]
                if return_code != 0 and stderr_output:
                    log_msg += " Stderr: %s"
                    log_args.append(stderr_output)

                log_func(log_msg, *log_args) # Log termination with optional stderr

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
                        original_process = self.process # Store ref before launch
                        self.launch() # Attempt restart

                        # Check if launch actually assigned a *new* process object
                        # and if that new process is running
                        if self.process and self.process is not original_process and self.process.poll() is None:
                            log.info(
                                "A2A process for '%s' restarted successfully (New PID: %d).",
                                self.agent_name,
                                self.process.pid,
                            )
                            current_restart_attempts = 0
                            continue # Continue monitoring the new process
                        elif self.process and self.process is not original_process:
                            # Launch assigned a new process, but it terminated immediately
                            log.error(
                                "Restarted A2A process for '%s' (PID: %d) terminated immediately. Continuing restart attempts.",
                                self.agent_name,
                                self.process.pid,
                            )
                            # Do NOT reset attempts, let loop poll again
                        elif self.process is original_process:
                            # Launch was mocked or failed internally without changing self.process
                            log.error(
                                "A2A process launch for '%s' did not assign a new process. Assuming persistent failure. Continuing restart attempts.",
                                self.agent_name
                            )
                            # Do NOT reset attempts, let loop poll again
                        else: # self.process became None after launch
                            log.error(
                                "Failed to restart A2A process for '%s' (launch resulted in no process). Stopping monitor.",
                                self.agent_name,
                            )
                            break # Stop monitoring if launch fails completely
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
                    # Wait for a short period, also capture any final output
                    stdout_data, stderr_data = self.process.communicate(timeout=5)
                    log.info(
                        "Managed A2A process (PID: %d) for '%s' terminated gracefully.",
                        pid,
                        self.agent_name,
                    )
                    if stderr_data:
                        log.debug("Final stderr from PID %d: %s", pid, stderr_data.strip())
                except subprocess.TimeoutExpired:
                    # Force kill if graceful termination fails
                    log.warning(
                        "Managed A2A process (PID: %d) for '%s' did not terminate gracefully after 5s, killing.",
                        pid,
                        self.agent_name,
                    )
                    self.process.kill()
                    # Wait for kill to complete, capture output if possible (less likely)
                    try:
                        stdout_data, stderr_data = self.process.communicate(timeout=1)
                        if stderr_data:
                            log.debug("Final stderr after kill from PID %d: %s", pid, stderr_data.strip())
                    except Exception:
                        pass # Ignore errors trying to read after kill
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
                # Ensure streams are closed if they exist
                if self.process and self.process.stderr and not self.process.stderr.closed:
                    self.process.stderr.close()
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
