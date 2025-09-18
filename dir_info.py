import subprocess
from dataclasses import dataclass
from datetime import datetime
import os
import shutil


@dataclass
class DirInfo:
    path: str
    bytes_used: int
    bytes_free: int


def get_dir_info(dir_path) -> DirInfo:
    """
    Get information about a directory including path, free space on the partition,
    and the total size of files contained within the directory tree.

    Args:
        dir_path (str): Path to the directory

    Returns:
        DirInfo: Dataclass containing directory information (path, partition free bytes,
                 sum of contained file sizes in bytes).
    """
    # Get disk usage statistics
    disk_usage = shutil.disk_usage(dir_path)

    # Create and return the DirInfo dataclass
    return DirInfo(
        path=dir_path,
        bytes_free=disk_usage.free,
        bytes_used=get_dir_size(dir_path)
    )


def get_dir_size(dir_path: str) -> int:
    """
    Return the dir size aka bytes used of a directory
    :param dir_path:
    :return:
    """
    # Execute du -sb <dir_path>
    # -s: summarize - display only a total for the directory
    # -k: kilobytes - print size in kilobytes
    result = subprocess.run(
        ['du', '-sk', dir_path],
        capture_output=True,
        text=True,
        check=True,  # Raise CalledProcessError on non-zero exit status
        encoding='utf-8'
    )
    # Output is typically "SIZE\tPATH"
    output = result.stdout.strip()
    if not output:
        raise ValueError(f"'du -sk {dir_path}' produced empty output.")
    dir_size_str = output.split()[0]

    return int(dir_size_str) * 1024


def get_dir_last_change(dir_path: str) -> datetime:
    """
    Descents into the folder and examines the change time of all files.
    Returns the datetime of the most recently changed file inside the folder.

    Args:
        dir_path: Path to the directory to examine

    Returns:
        datetime: The timestamp of the most recently changed file

    Raises:
        FileNotFoundError: If the directory doesn't exist or is empty
    """
    if not os.path.exists(dir_path):
        raise FileNotFoundError(f"Directory does not exist: {dir_path}")

    # Use a safe datetime that works on both 32-bit and 64-bit systems
    latest_time = datetime(1900, 1, 1, 0, 0, 0)

    for root, dirs, files in os.walk(dir_path):
        # Check modification time of all files in this directory
        for file in files:
            file_path = os.path.join(root, file)
            # Skip symbolic links to avoid potential issues
            if not os.path.islink(file_path):
                try:
                    # Get the modification time
                    mtime = os.path.getmtime(file_path)
                    try:
                        mtime_dt = datetime.fromtimestamp(mtime)
                    except (OSError, OverflowError, ValueError):
                        # On 32-bit systems, timestamps outside the valid range will fail
                        # Skip this file if we can't convert its timestamp
                        continue

                    # Update latest_time if this file is more recent
                    if mtime_dt > latest_time:
                        latest_time = mtime_dt
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    continue

    return latest_time
