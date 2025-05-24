import os


def get_version() -> str:
    if os.path.exists("VERSION"):
        with open("VERSION") as version_file:
            return version_file.read().strip()
    return "0.0.0-src"
