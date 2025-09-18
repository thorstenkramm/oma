import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

from config import Config
from concurrent.futures import ProcessPoolExecutor, as_completed

from mysql_info import MySQLInfo
from store_manager import StoreManager
from logger import OmaLogger

from utils import format_bytes, calc_parallelism
from datetime import datetime


class NotEnoughDiskSpaceError(Exception):
    """Exception raised when backup wouldn't fit in disk space"

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


@dataclass
class BackupResult:
    skipped: int = 0
    successful: int = 0
    failed: int = 0
    total: int = 0
    all_skipped_successfully: bool = False
    all_skipped_faulty: bool = False


class MySQLDump:
    def __init__(self, config: Config, store_manager: StoreManager, logger: OmaLogger):
        self.logger = logger
        self.config = config
        self.store_manager = store_manager
        store_manager.link_type = config.link_type
        self.mysql_info = MySQLInfo(mysql_bin=config.mysql_bin)

    def execute(self) -> BackupResult:
        """
        Execute the mysqldump command in parallel, according to the configured parallelism
        :return:
        """
        self.logger.debug(f"MySQL data directory: {self.mysql_info.data_dir}")
        self.logger.debug(f"Found {len(self.mysql_info.databases)} databases: {', '.join(self.mysql_info.databases)}")
        self.logger.info(f"Skip unchanged databases: {self.config.skip_unchanged_dbs}")

        # Generate list of databases to be backed up.
        databases = []
        skip = []

        # Check if do_databases is specified
        if self.config.do_databases:
            # Use only the specified databases
            for db in self.config.do_databases:
                if db in self.mysql_info.databases:
                    databases.append(db)
                else:
                    self.logger.warning(f"Database '{db}' specified in do_databases does not exist.")
            # Skip all other databases
            skip = [d for d in self.mysql_info.databases if d not in self.config.do_databases]
            self.logger.info(f"Backing up only specified databases: {self.config.do_databases}")
        else:
            # Use the exclude logic
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

        # Exit, if we don't have enough free space
        self.logger.debug("Checking for free disk space...")
        if not self._check_free_space(databases):
            return BackupResult()

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

    def _check_free_space(self, databases: list[str]) -> bool:
        previous_dump_info = self.store_manager.get_backup_info()
        # Check if we have enough free disk space for the backup
        required_free_bytes = self.mysql_info.get_databases_size(databases) * previous_dump_info.compression_ratio
        self.logger.info(
            f"Backup will require {format_bytes(required_free_bytes)} bytes. "
            + f"Having {format_bytes(self.store_manager.current_dir.bytes_free)} free."
        )
        if required_free_bytes > self.store_manager.current_dir.bytes_free:
            raise NotEnoughDiskSpaceError("Not enough free space in target directory.")
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
                + f"({database_dir_age.seconds} sec. ago)")
            self.logger.debug(
                f"DB '{database}' previous backup: {previous_dump_time} "
                + f"({previous_dump_age.seconds} sec. ago)")

            if previous_dump_time > database_last_change:
                self.logger.info(f"DB '{database}': Backup is newer than last database change. Reusing previous backup")
                try:
                    self.store_manager.reuse_previous_backup(database)
                except Exception as exc:
                    self.logger.error(f"DB '{database}': Moving previous backup to current directory: {exc}")
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
            # Handle potential encoding issues when reading the temp file
            dump_completion_line = ""
            try:
                with open(temp_path, 'r', encoding='utf-8', errors='replace') as f:
                    dump_completion_line = f.read().strip()
            except Exception as e:
                self.logger.warning(f"Failed to read temp file with UTF-8 encoding, trying binary mode: {e}")
                try:
                    with open(temp_path, 'rb') as f:
                        content = f.read()
                        # Try multiple encodings
                        for encoding in ['utf-8', 'latin-1', 'cp1252']:
                            try:
                                dump_completion_line = content.decode(encoding).strip()
                                self.logger.debug(f"Successfully decoded temp file using {encoding} encoding")
                                break
                            except UnicodeDecodeError:
                                continue
                        if not dump_completion_line:
                            # Last resort: ignore errors
                            dump_completion_line = content.decode('utf-8', errors='ignore').strip()
                            self.logger.warning("Used UTF-8 with ignore errors to read temp file")
                except Exception as e:
                    self.logger.error(f"Failed to read temp file even in binary mode: {e}")
                    raise Exception(f"Could not read mysqldump completion status: {e}")

            # Check for errors on stderr of mysqldump process
            if len(stderr_text) > 0:
                self.logger.error(f"mysqldump for DB '{database}' stderr: {stderr_text}")
            # Check if the last line matches the pattern indicating the dump completion timestamp
            dump_completed_pattern = re.compile(r"^-- Dump completed on \d{4}-\d{2}-\d{2}\s+\d+:\d{2}:\d{2}")
            if not dump_completed_pattern.match(dump_completion_line):
                self.logger.error(
                    f"Completion message not found for db '{database}'.")
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
