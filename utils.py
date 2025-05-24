import multiprocessing
import os
import shutil


def format_bytes(size_bytes: float) -> str:
    """Convert bytes to human-readable format"""
    if size_bytes == 0:
        return "0B"

    size_names = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1

    # Round to 2 decimal places
    return f"{size_bytes:.2f} {size_names[i]}"


def swap_file_for_link(source, destination):
    """
    Moves a source file to a destination file.
    The source file will be replaced by a symbolic link to the new destination
    :param source: Path to the source file to be moved
    :param destination: Path where the file will be moved to
    :return: None
    """
    # Ensure the source file exists
    if not os.path.exists(source):
        raise FileNotFoundError(f"Source file does not exist: {source}")

    # Ensure the destination directory exists
    dest_dir = os.path.dirname(destination)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)

    # Move the file to the destination
    shutil.move(source, destination)

    # Create a symbolic link at the source location pointing to the destination
    os.symlink(destination, source)


def calc_parallelism(desired: int) -> int:
    if desired > 0:
        return desired
    if multiprocessing.cpu_count() + desired > 0:
        return multiprocessing.cpu_count() + desired
    return 1
