import subprocess
import logging
import os
from typing import Tuple

from config import ConditionsConfig
from logger import OmaLogger


class ConditionsManager:
    def __init__(self, conditions_config: ConditionsConfig, logger: OmaLogger):
        self.config = conditions_config
        self.logger = logger

    def check_skip_conditions(self) -> bool:
        """
        Execute skip conditions commands.
        Returns True if any condition succeeds (exit code 0), meaning backup should be skipped.
        """
        if not self.config.skip_conditions:
            return False

        self.logger.info("Checking skip conditions...")
        for command in self.config.skip_conditions:
            exit_code, stdout, stderr = self._execute_condition(
                command, self.config.skip_conditions_timeout
            )

            if exit_code == 0:
                self.logger.info(f"Skip condition met: '{command}' (exit code: 0)")
                if self.logger.level == logging.DEBUG and stdout:
                    self.logger.debug(f"Skip condition stdout: '{stdout.strip()}'")
                return True
            else:
                self.logger.debug(f"Skip condition not met: '{command}' (exit code: {exit_code})")
                if stderr:
                    self.logger.debug(f"Skip condition stderr: '{stderr.strip()}'")

        self.logger.info("No skip conditions met, proceeding with backup")
        return False

    def check_run_conditions(self) -> bool:
        """
        Execute run conditions commands.
        Returns True only if all conditions succeed (exit code 0).
        """
        if not self.config.run_conditions:
            return True

        for command in self.config.run_conditions:
            exit_code, stdout, stderr = self._execute_condition(
                command, self.config.run_conditions_timeout
            )

            if exit_code != 0:
                self.logger.error(
                    f"Run condition failed: '{command}' (exit code: {exit_code})"
                )
                if stderr:
                    self.logger.error(f"Run condition stderr: {stderr}")
                return False
            else:
                self.logger.debug(f"Run condition passed: '{command}' (exit code: 0)")
                if self.logger.level == logging.DEBUG and stdout:
                    self.logger.debug(f"Run condition stdout: {stdout}")

        self.logger.info("All run conditions met")
        return True

    def execute_terminate_conditions(self, current_backup_dir: str) -> bool:
        """
        Execute terminate conditions commands after backup.
        Returns True only if all conditions succeed (exit code 0).

        Args:
            current_backup_dir: Path to the current backup directory (passed as OMA_CURRENT_DIR env var)
        """
        if not self.config.terminate_conditions:
            return True

        # Set up environment variable
        env = os.environ.copy()
        env['OMA_CURRENT_DIR'] = current_backup_dir

        all_success = True
        for command in self.config.terminate_conditions:
            exit_code, stdout, stderr = self._execute_condition(
                command, self.config.terminate_conditions_timeout, env
            )

            if exit_code != 0:
                self.logger.error(
                    f"Terminate condition failed: '{command}' (exit code: {exit_code})"
                )
                if stderr:
                    self.logger.error(f"Terminate condition stderr: {stderr}")
                all_success = False
                # Continue with other conditions even if one fails
            else:
                self.logger.info(f"Terminate condition succeeded: '{command}'")
                if self.logger.level == logging.DEBUG and stdout:
                    self.logger.debug(f"Terminate condition stdout: {stdout}")

        if all_success:
            self.logger.info("All terminate conditions succeeded")
        else:
            self.logger.error("One or more terminate conditions failed")

        return all_success

    def _execute_condition(
            self, command: str, timeout: int, env: dict = None
    ) -> Tuple[int, str, str]:
        """
        Execute a single command with timeout.

        Args:
            command: Command to execute with /bin/sh
            timeout: Timeout in seconds (0 means no timeout)
            env: Environment variables dict (optional)

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        try:
            # Use None for timeout if it's 0 (no limit)
            timeout_value = timeout if timeout > 0 else None

            result = subprocess.run(
                ['/bin/sh', '-c', command],
                capture_output=True,
                text=True,
                timeout=timeout_value,
                env=env
            )

            return result.returncode, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            self.logger.error(f"Command timed out after {timeout} seconds: '{command}'")
            return 1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            self.logger.error(f"Failed to execute command '{command}': {str(e)}")
            return 1, "", str(e)
