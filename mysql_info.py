import os.path
import subprocess
from datetime import datetime

from dir_info import get_dir_last_change, get_dir_info


def encode_database_name(name: str) -> str:
    """
    Encode database name according to MySQL's filesystem naming rules.
    MySQL encodes special characters when creating directories on the filesystem.
    For example:
    - Hyphen (-) becomes @002d
    - Period (.) becomes @002e
    - Space ( ) becomes @0020

    Args:
        name: The database name as it appears in MySQL

    Returns:
        The encoded name as it appears on the filesystem
    """
    # Process each character individually to avoid double-encoding issues
    encoded = []

    for char in name:
        # Check if this character needs encoding
        if char == '-':
            encoded.append('@002d')  # Hyphen/dash
        elif char == '.':
            encoded.append('@002e')  # Period
        elif char == ' ':
            encoded.append('@0020')  # Space
        elif char == '$':
            encoded.append('@0024')  # Dollar sign
        elif char == '!':
            encoded.append('@0021')  # Exclamation mark
        elif char == '#':
            encoded.append('@0023')  # Hash/pound
        elif char == '%':
            encoded.append('@0025')  # Percent
        elif char == '&':
            encoded.append('@0026')  # Ampersand
        elif char == '(':
            encoded.append('@0028')  # Left parenthesis
        elif char == ')':
            encoded.append('@0029')  # Right parenthesis
        elif char == '*':
            encoded.append('@002a')  # Asterisk
        elif char == '+':
            encoded.append('@002b')  # Plus
        elif char == ',':
            encoded.append('@002c')  # Comma
        elif char == '/':
            encoded.append('@002f')  # Forward slash
        elif char == ':':
            encoded.append('@003a')  # Colon
        elif char == ';':
            encoded.append('@003b')  # Semicolon
        elif char == '<':
            encoded.append('@003c')  # Less than
        elif char == '=':
            encoded.append('@003d')  # Equals
        elif char == '>':
            encoded.append('@003e')  # Greater than
        elif char == '?':
            encoded.append('@003f')  # Question mark
        elif char == '@':
            encoded.append('@0040')  # At sign
        elif char == '[':
            encoded.append('@005b')  # Left square bracket
        elif char == '\\':
            encoded.append('@005c')  # Backslash
        elif char == ']':
            encoded.append('@005d')  # Right square bracket
        elif char == '^':
            encoded.append('@005e')  # Caret
        elif char == '{':
            encoded.append('@007b')  # Left curly brace
        elif char == '|':
            encoded.append('@007c')  # Pipe
        elif char == '}':
            encoded.append('@007d')  # Right curly brace
        elif char == '~':
            encoded.append('@007e')  # Tilde
        else:
            # Keep the character as-is
            encoded.append(char)

    return ''.join(encoded)


class MySQLInfo:
    def __init__(self, mysql_bin='mysql'):
        self.mysql_bin = mysql_bin
        self.data_dir = get_dir_info(self.get_data_dir())
        self.databases = self.get_databases()

    def get_data_dir(self) -> str:
        """
        Get the MySQL data directory path by querying the MySQL server.

        Returns:
            str: Path to the MySQL data directory
        """
        # Execute SQL query to get the data directory
        cmd = [self.mysql_bin, "-N", "-e", "SELECT @@datadir"]

        result = subprocess.run(cmd, check=True, capture_output=True, text=True)

        # Return the output to get the data directory path
        # Typically, the output will be a single line with the path
        return result.stdout.strip()

    def get_databases(self) -> list:
        """
        Get list of all databases.
        Executes "mysql -e "show databases" -N"
        :return: list
        """

        # Execute the MySQL command to show databases
        cmd = [self.mysql_bin, "-e", "show databases", "-N"]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)

        # Split the output by newlines and filter out empty strings
        databases = [db.strip() for db in result.stdout.split('\n') if db.strip()]
        # Filter out system databases
        system_dbs = ['information_schema', 'sys', 'performance_schema']
        databases = [db for db in databases if db not in system_dbs]

        return databases

    def get_database_last_change(self, database: str) -> datetime:
        encoded_name = encode_database_name(database)
        database_dir = os.path.join(self.data_dir.path, encoded_name)
        return get_dir_last_change(database_dir)

    def get_database_size(self, database: str) -> int:
        """
        get the size of the database in bytes.
        :param database:
        :return:
        """
        encoded_name = encode_database_name(database)
        database_dir = os.path.join(self.data_dir.path, encoded_name)
        info = get_dir_info(database_dir)
        return info.bytes_used

    def get_databases_size(self, databases: list[str]) -> int:
        """
        Get the size of all databases.
        :param list of databases:
        :return: size in bytes
        """
        size = 0
        for database in databases:
            size += self.get_database_size(database)
        return size
