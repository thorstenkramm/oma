import time
import unittest
import subprocess
import os


class TestEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        # Build the app
        subprocess.run(".github/scripts/build.sh")
        self.databases = ['demo1', 'demo2', 'skip1']
        self.backup_dir = "/tmp/oma"
        # Prepare the backup dir
        subprocess.run(f"rm -rf {self.backup_dir} || true", shell=True)
        os.mkdir(self.backup_dir)
        # Prepare the databases
        for database in self.databases:
            print(f"Creating database {database} ...")
            subprocess.run(f"mysql -e 'DROP DATABASE IF EXISTS {database}; CREATE DATABASE {database}'",
                           shell=True, check=True)
            print(f"Filling database {database} with demo data ...")
            subprocess.run(f"mysql {database}< ./test_data/world.sql", shell=True, check=True)
        # Wait for all mysql background write processes to be completed
        time.sleep(4)

    @classmethod
    def tearDownClass(self):
        # Remove the created database
        for database in self.databases:
            subprocess.run(f"mysql -e 'DROP DATABASE {database}'", shell=True, check=True)

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_01_full_backup(self):
        self.__run_backup()

        log_content = self.__read_log()

        # Assert all databases have been backed up and not re-used
        for database in [db for db in self.databases if not db.startswith("skip")]:
            self.assertIn(
                f"INFO DB '{database}': Backup successfully",
                log_content,
                "Success message not found in the log file"
            )
            # Validate mysqldump options have been applied
            self.assertIn(
                f"Executing command: bash -c 'mysqldump {database} --single-transaction --quick",
                log_content,
                "mysqldump options not applied"
            )

    def test_02_no_changes(self):
        """
        Run the backup again. Because no table has changed, all databases are marked as re-used.
        :return:
        """
        time.sleep(1)
        self.__run_backup()
        log_content = self.__read_log()

        for database in [db for db in self.databases if not db.startswith("skip")]:
            self.assertIn(
                f"INFO DB '{database}': Backup is newer than last database change. Reusing previous backup",
                log_content,
                "Previous backup reused."
            )

    def test_03_partial_changes(self):
        """
        Update a single database. Expect only this database to be backed up. The rest must be skipped.
        :return:
        """
        subprocess.run(r'mysql demo1 -e "update city set Population=FLOOR(RAND()*1000) where ID=1"',
                       shell=True,
                       check=True)
        # Wait for all mysql background write processes to be completed
        time.sleep(4)
        self.__run_backup()
        log_content = self.__read_log()
        print(log_content)
        self.assertIn(
            "INFO DB 'demo2': Backup is newer than last database change. Reusing previous backup",
            log_content,
            "Previous backup reused."
        )
        self.assertIn(
            "INFO DB 'demo1': Backup successfully",
            log_content,
            "Backup successfully"
        )

    def test_04_no_changes(self):
        """
        Run the backup again. Because no table has changed, all databases are marked as re-used.
        :return:
        """
        self.__run_backup()
        log_content = self.__read_log()

        for database in [db for db in self.databases if not db.startswith("skip")]:
            self.assertIn(
                f"INFO DB '{database}': Backup is newer than last database change. Reusing previous backup",
                log_content,
                "Previous backup reused."
            )
        # Because we want to store only 3 version, check we have 3 (and not 4) versions
        self.assertEqual(count_subfolders('/tmp/oma'), 3, 'Number of subfolders should equal 3.')

    def test_05_restore_from_backup(self):
        for database in [db for db in self.databases if not db.startswith("skip")]:
            subprocess.run(f"mysql -e 'DROP DATABASE {database}'", shell=True, check=True)
            subprocess.run(f"mysql -e 'CREATE DATABASE {database}'", shell=True, check=True)
            subprocess.run(f"zcat /tmp/oma/last/{database}.sql.gz | mysql {database}", shell=True, check=True)
            response = subprocess.run(
                f"mysql {database} -N -e 'show tables'|wc -l",
                shell=True, check=True, text=True, capture_output=True
            )
            self.assertEqual(int(response.stdout.strip()), 3)

    def test_06_full_backup_no_skip(self):
        self.__run_backup("run2")

        log_content = self.__read_log()

        # Assert all databases have been backed up and not re-used
        for database in [db for db in self.databases if not db.startswith("skip")]:
            self.assertIn(
                f"INFO DB '{database}': Backup successfully",
                log_content,
                "Success message not found in the log file"
            )
            # Validate mysqldump options have been applied
            self.assertIn(
                f"Executing command: bash -c 'mysqldump {database} --single-transaction --quick",
                log_content,
                "mysqldump options not applied"
            )
            self.assertNotIn(
                f"DB '{database}' last change: ",
                log_content,
                "database last change found. skip_unchanged_dbs shall supress this."
            )

    def __run_backup(self, config: str = "run1"):
        response = subprocess.run(
            f"./oma -c test_data/{config}.conf",
            shell=True,
            check=True,
            capture_output=True
        )
        time.sleep(3)
        print(response.stdout.decode())
        print(response.stderr.decode())

    def __read_log(self) -> str:
        # Open and read the log file
        # log_file = self.__get_subdirs('/tmp/oma')[0] + "/oma.log"
        log_file = '/tmp/oma/last/oma.log'
        print("Reading log file: " + log_file)
        with open(log_file, "r") as f:
            log_content = f.read()

        # Assert no errors found in the log
        self.assertNotIn("Error", log_content, "Errors found in the log file")
        # Validate backup parallelism
        self.assertIn("INFO Will start 2 parallel mysqldump processes", log_content, "parallelism does not match")

        return log_content


def count_subfolders(directory_path):
    """
    Count the number of real subfolders in the specified directory,
    excluding symbolic links to folders.

    Args:
        directory_path (str): Path to the directory

    Returns:
        int: Number of real subfolders (excluding symlinks)
    """
    # Check if the directory exists
    if not os.path.isdir(directory_path):
        raise ValueError(f"The path {directory_path} is not a valid directory")

    # Get all items in the directory
    items = os.listdir(directory_path)

    # Count only real directories (not symbolic links)
    real_subfolders = 0
    for item in items:
        full_path = os.path.join(directory_path, item)
        # Check if it's a directory AND not a symbolic link
        if os.path.isdir(full_path) and not os.path.islink(full_path):
            real_subfolders += 1

    return real_subfolders


if __name__ == "__main__":
    unittest.main()
