import os.path
import subprocess
from datetime import datetime

from dir_info import get_dir_last_change, get_dir_info


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
        database_dir = os.path.join(self.data_dir.path, database)
        return get_dir_last_change(database_dir)

    def get_database_size(self, database: str) -> int:
        """
        get the size of the database in bytes.
        :param database:
        :return:
        """
        database_dir = os.path.join(self.data_dir.path, database)
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
