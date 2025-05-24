import os
import re
import subprocess
import logging
import tempfile
from dataclasses import dataclass

from config import Config
from concurrent.futures import ProcessPoolExecutor, as_completed

from mysql_info import MySQLInfo
from store_manager import StoreManager

from utils import format_bytes, calc_parallelism
from datetime import datetime


@dataclass
class BackupResult:
    skipped: int = 0
    successful: int = 0
    failed: int = 0
    total: int = 0


class MySQLDump:
    def __init__(self, config: Config, store_manager: StoreManager, logger: logging):
        self.logger = logger
        self.config = config
        self.store_manager = store_manager
        self.mysql_info = MySQLInfo(mysql_bin=config.mysql_bin)

    def execute(self) -> BackupResult:
        """
        Execute the mysqldump command in parallel, according to the configured parallelism
        :return:
        """
        self.logger.debug(f"MySQL data directory: {self.mysql_info.data_dir}")
        self.logger.debug(f"Found {len(self.mysql_info.databases)} databases: {', '.join(self.mysql_info.databases)}")
        self.logger.info(f"Skip unchanged databases: {self.config.skip_unchanged_dbs}")

        # Exit, if we don't have enough free space
        if not self._check_free_space():
            return BackupResult()

        # Generate list of databases to be backed up.
        databases = []
        skip = []
        for d in self.mysql_info.databases:
            if d in self.config.exclude_databases:
                skip.append(d)
            else:
                databases.append(d)
        if len(self.config.exclude_databases) > 0:
            self.logger.info(f"Excluding databases {self.config.exclude_databases} from backup job.")
        for e in self.config.exclude_databases:
            if e not in self.mysql_info.databases:
                self.logger.warning(f"Database to be excluded '{e}' does not exist.")

        parallelism = calc_parallelism(self.config.parallelism)
        with ProcessPoolExecutor(max_workers=parallelism) as executor:
            self.logger.info(
                f"Will start {parallelism} parallel mysqldump processes using "
                f"options {self.config.mysqldump_options}")
            # Submit all database dump tasks
            future_to_db = {executor.submit(self._mysqldump_to_gzip, database): database for database in
                            databases}

            # Process results as they complete
            success_count = 0
            for future in as_completed(future_to_db):
                database = future_to_db[future]
                try:
                    result = future.result()
                    if result:
                        success_count += 1
                        self.logger.info(f"DB '{database}': Backup successfully")
                    else:
                        self.logger.error(f"Failed to dump database: {database}")
                except Exception as exc:
                    self.logger.error(f"DB '{database}': Backup failed: {exc}")

            failed = len(databases) - success_count
            if failed == 0:
                self.logger.info(
                    f"Successfully dumped {success_count} of {len(self.mysql_info.databases)}, "
                    f"failed {failed} databases")
            else:
                self.logger.error(
                    f"Backing up all databases: Expected {len(self.mysql_info.databases)}, got {success_count}")

        self.store_manager.store_backup_info(self.mysql_info.data_dir.bytes_used)
        self.store_manager.link_to_last_dir()
        return BackupResult(
            skipped=len(skip),
            successful=success_count,
            failed=len(databases) - success_count,
            total=len(self.mysql_info.databases),
        )

    def _check_free_space(self) -> bool:
        previous_dump_info = self.store_manager.get_backup_info()
        # Check if we have enough free disk space for the backup
        required_free_bytes = self.mysql_info.data_dir.bytes_used * previous_dump_info.compression_ratio
        self.logger.info(
            f"Backup will require {format_bytes(required_free_bytes)} bytes. "
            + f"Having {format_bytes(self.store_manager.current_dir.bytes_free)} free."
        )
        if required_free_bytes > self.store_manager.current_dir.bytes_free:
            self.logger.error("Not enough free space in target directory.")
            return False
        return True

    def _mysqldump_to_gzip(self, database: str):

        output_file = os.path.join(self.store_manager.current_dir.path, f"{database}.sql.gz")

        if self.config.skip_unchanged_dbs:
            database_last_change = self.mysql_info.get_database_last_change(database)
            database_dir_age = datetime.now() - database_last_change
            previous_dump_time = self.store_manager.get_database_backup_time(database)
            previous_dump_age = datetime.now() - previous_dump_time
            self.logger.debug(
                f"DB '{database}' last change: {database_last_change} "
                + f"[ts={database_last_change.timestamp()}] ({database_dir_age.seconds} sec. ago)")
            self.logger.debug(
                f"DB '{database}' previous backup: {previous_dump_time} "
                + f"[ts={previous_dump_time.timestamp()}] ({previous_dump_age.seconds} sec. ago)")

            if previous_dump_time.timestamp() > database_last_change.timestamp():
                self.logger.info(f"DB '{database}': Backup is newer than last database change. Reusing previous backup")
                self.store_manager.reuse_previous_backup(database)
                return "ok"

        # Create a temporary file for the last line of the output
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            self.store_manager.store_database_backup_time(database)
            # Base mysqldump command
            mysqldump_base = f"mysqldump {database} {' '.join(self.config.mysqldump_options)}"

            # Construct the full command
            cmd = (
                f"bash -c '{mysqldump_base} | "
                f"tee >(tail -n 1 > {temp_path}) | "
                f"gzip -c > {output_file}'"
            )

            self.logger.debug(f"Executing command: {cmd}")

            # Execute the command
            with subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    shell=True,
            ) as process:

                # Wait for completion
                _, stderr = process.communicate()
                stderr_text = stderr.decode('utf-8') if stderr else ""

                if process.returncode != 0:
                    self.logger.error(f"mysqldump failed with return code {process.returncode}: {stderr_text}")
                    raise Exception(f"mysqldump pipeline failed: {stderr_text}")

            # Check for completion message in the last line
            with open(temp_path, 'r') as f:
                dump_completion_line = f.read().strip()

            # Check if the last line matches the pattern indicating the dump completion timestamp
            dump_completed_pattern = re.compile(r"^-- Dump completed on \d{4}-\d{2}-\d{2}\s+\d+:\d{2}:\d{2}")
            if not dump_completed_pattern.match(dump_completion_line):
                self.logger.error(f"Completion message not found. Last line: {dump_completion_line}")
                raise Exception("mysqldump did not complete successfully: no completion message found")

            self.logger.info(f"Database dump completed successfully: {output_file}")
            return output_file

        except Exception as e:
            self.logger.exception(f"Error during database dump: {e}")
            raise

        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.remove(temp_path)
                self.logger.debug(f"Temporary file {temp_path} removed")
