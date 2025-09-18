import os
import shutil
from datetime import datetime
import glob
import re
import json
from dataclasses import dataclass

from dir_info import get_dir_info, DirInfo
from utils import swap_file_for_link

DIR_PREFIX = 'oma'


@dataclass
class MySQLDumpInfo():
    mysql_data_dir_bytes_used: int
    backup_bytes_used: int
    compression_ratio: float


class StoreManager:
    def __init__(self, backup_dir: str):
        """
        Initialize a new folder in backup_dir that will hold the mysqldump backup files and the log file.
        Directory names consist of the dir prefix and the current date in format YYYYMMDD-hhmmss
        Returns the full path to the created directory.
        :param backup_dir:
        :return: str
        """
        self.backup_dir = backup_dir
        self.link_type = 'hard'

        # Ensure base directory exists
        if not os.path.exists(backup_dir):
            raise ValueError(f"Base directory '{backup_dir}' does not exist")

        # Get the directory of the previous backup
        try:
            previous_dir = self._get_backup_dirs()[-1]
            self.previous_dir = get_dir_info(previous_dir)
        except IndexError:
            # Return zero values, if previous backup directory does not exist.
            self.previous_dir = DirInfo("", 0, 0)

        # Create new backup directory with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        current_dir = os.path.join(backup_dir, f"{DIR_PREFIX}_{timestamp}")
        os.makedirs(current_dir, exist_ok=True)
        self.current_dir = get_dir_info(os.path.join(backup_dir, f"{DIR_PREFIX}_{timestamp}"))

    def store_backup_info(self, mysql_data_dir_bytes_used: int):
        """
        Store information about the completed backup.
        Required for the next run to calculate the disk space needed based
        on the compression of the previous backup
        :param mysql_data_dir_bytes_used:
        :return:
        """
        # Refresh data usage of current dir
        self.current_dir = get_dir_info(self.current_dir.path)
        # Calculate the compression ratio
        backup_bytes_used = self.current_dir.bytes_used
        compression_ratio = (backup_bytes_used / mysql_data_dir_bytes_used
                             if mysql_data_dir_bytes_used != 0 else 0)
        mysql_dump_info = MySQLDumpInfo(
            mysql_data_dir_bytes_used=mysql_data_dir_bytes_used,
            backup_bytes_used=backup_bytes_used,
            compression_ratio=compression_ratio
        )
        mysql_dump_info_file = os.path.join(self.current_dir.path, 'info.json')
        with open(mysql_dump_info_file, "w") as f:
            f.write(json.dumps(mysql_dump_info.__dict__, indent=4))

    def link_to_last_dir(self):
        link_dst = os.path.join(self.backup_dir, 'last')
        log_dst = os.path.join(self.backup_dir, 'last.log')
        # Handle removal properly whether it's a file, directory, or symlink
        if os.path.islink(link_dst):
            os.unlink(link_dst)
        elif os.path.isdir(link_dst):
            shutil.rmtree(link_dst)
        elif os.path.exists(link_dst):
            os.remove(link_dst)
        os.symlink(self.current_dir.path, link_dst, target_is_directory=True)
        log_src = os.path.join(self.current_dir.path, 'oma.log')
        if os.path.exists(log_dst) or os.path.islink(log_dst):
            os.unlink(log_dst)
        os.symlink(log_src, log_dst, target_is_directory=False)

    def remove_skipped(self):
        """
        Remove a folder if the backup has been skipped entirely.
        :return:
        """
        log_file = os.path.join(self.current_dir.path, 'oma.log')
        os.rename(log_file, os.path.join(self.backup_dir, 'last.log'))
        shutil.rmtree(self.current_dir.path)

    def get_backup_info(self) -> MySQLDumpInfo:
        try:
            with open(os.path.join(self.previous_dir.path, 'info.json')) as f:
                info_dict = json.load(f)
                # Create and return a dataclass instance from the dictionary

                return MySQLDumpInfo(**info_dict)
        except FileNotFoundError:
            return MySQLDumpInfo(0, 0, 0.5)

    def get_database_backup_time(self, database: str) -> datetime:
        try:
            timestamp_file = os.path.join(self.previous_dir.path, database + '.timestamp')
            with open(timestamp_file, "r") as f:
                return datetime.fromisoformat(f.read().strip())
        except FileNotFoundError:
            return datetime(1900, 1, 1, 0, 0, 0)

    def store_database_backup_time(self, database: str):
        timestamp_file = os.path.join(self.current_dir.path, database + '.timestamp')
        with open(timestamp_file, "w+") as f:
            f.write(datetime.now().isoformat())

    def cleanup_before(self, versions: int) -> list[str]:
        return self._cleanup(versions)

    def cleanup_after(self, versions: int) -> list[str]:
        return self._cleanup(versions)

    def get_previous_database_backup_time(self, database: str) -> datetime:
        return self.get_database_backup_time(database)

    def reuse_previous_backup(self, database: str):
        """
        Move the previous backup of a database to the current directory.
        Replace the previous backup of a database by a symbolic link to the current backup
        :param database:
        :return:
        """
        for suffix in ['.sql.gz', '.timestamp']:
            previous_file = os.path.join(self.previous_dir.path, database + suffix)
            current_file = os.path.join(self.current_dir.path, database + suffix)
            swap_file_for_link(previous_file, current_file, self.link_type)

    def _get_backup_dirs(self):
        """
        Returns a list of sub directories in backup_dir, oldest first
        :return:
        """
        # Get all potential backup directories
        all_dirs = glob.glob(os.path.join(self.backup_dir, f"{DIR_PREFIX}_*"))
        # Filter directories using regex pattern to match only the specific format
        pattern = re.compile(DIR_PREFIX + r'_\d{8}-\d{6}$')
        backup_dirs = [d for d in all_dirs if pattern.search(os.path.basename(d))]
        # Sort the directories (oldest first)
        backup_dirs.sort()

        return backup_dirs

    def _cleanup(self, versions: int) -> list[str]:
        backup_dirs = self._get_backup_dirs()
        removed = []

        # Remove oldest directories if we have more than the specified versions
        if len(backup_dirs) > versions:
            # Calculate how many directories need to be removed
            num_to_remove = len(backup_dirs) - versions
            # Get the directories to remove (oldest ones first)
            dirs_to_remove = backup_dirs[:num_to_remove]

            # Remove each directory
            for old_dir in dirs_to_remove:
                shutil.rmtree(old_dir)
                removed.append(old_dir)

        return removed
