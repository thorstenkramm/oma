import socket
import time
import unittest
import subprocess
import os


class TestEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        # Build the app
        subprocess.run(".github/scripts/build.sh")
        self.databases = ['demo1', 'd-e-m-o-2', 'skip1']
        self.backup_dir = "/tmp/oma"
        # Prepare the backup dir
        subprocess.run(f"rm -rf {self.backup_dir} || true", shell=True)
        os.mkdir(self.backup_dir)
        # Prepare the databases
        for database in self.databases:
            print(f"Creating database {database} ...")
            subprocess.run(f"mysql -e 'DROP DATABASE IF EXISTS `{database}`; CREATE DATABASE `{database}`'",
                           shell=True, check=True)
            print(f"Filling database {database} with demo data ...")
            subprocess.run(f"mysql {database}< ./test_data/world.sql", shell=True, check=True)
        # Wait for all mysql background write processes to be completed
        time.sleep(4)

    @classmethod
    def tearDownClass(self):
        # Remove the created database
        for database in self.databases:
            subprocess.run(f"mysql -e 'DROP DATABASE `{database}`'", shell=True, check=True)

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_01_full_backup(self):
        time.sleep(3)
        self.__run_backup()

        log_content = self.__read_log()

        # Assert no errors found in the log
        self.assertNotIn("Error", log_content, "Errors found in the log file")
        # Validate backup parallelism
        self.assertIn("INFO Will start 2 parallel mysqldump processes", log_content, "parallelism does not match")

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
        time.sleep(3)
        self.__run_backup()
        log_content = self.__read_log()

        # Assert no errors found in the log
        self.assertNotIn("Error", log_content, "Errors found in the log file")
        # Validate backup parallelism
        self.assertIn("INFO Will start 2 parallel mysqldump processes", log_content, "parallelism does not match")

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
        # Assert no errors found in the log
        self.assertNotIn("Error", log_content, "Errors found in the log file")

        self.assertIn(
            "INFO DB 'd-e-m-o-2': Backup is newer than last database change. Reusing previous backup",
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

        # Assert no errors found in the log
        self.assertNotIn("Error", log_content, "Errors found in the log file")

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
            subprocess.run(f"mysql -e 'DROP DATABASE `{database}`'", shell=True, check=True)
            subprocess.run(f"mysql -e 'CREATE DATABASE `{database}`'", shell=True, check=True)
            subprocess.run(f"zcat /tmp/oma/last/{database}.sql.gz | mysql {database}", shell=True, check=True)
            response = subprocess.run(
                f"mysql {database} -N -e 'show tables'|wc -l",
                shell=True, check=True, text=True, capture_output=True
            )
            self.assertEqual(int(response.stdout.strip()), 3)

    def test_06_full_backup_no_skip(self):
        self.__run_backup("run2")

        log_content = self.__read_log()

        # Assert no errors found in the log
        self.assertNotIn("Error", log_content, "Errors found in the log file")

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

    def test_07_successfully_skip(self):
        self.__run_backup("skip_condition_success")

        log_content = self.__read_log()

        # Assert backup has been skipped intentionally due to conditions
        self.assertIn(
            "INFO Backup skipped due to skip conditions (but considered successful)",
            log_content,
            "Success message not found in the log file"
        )

    def test_08_faulty_skip(self):
        self.__run_backup("skip_condition_faulty", 1)

        log_content = self.__read_log()
        msgs = [
            'DEBUG Run condition passed: \'echo "Hi There"|grep "Hi There"\' (exit code: 0)',
            'DEBUG Run condition stdout: Hi There',
            'ERROR Run condition failed: \'non-existing-command\' (exit code: 127)',
            'ERROR Run condition stderr: /bin/sh: 1: non-existing-command: not found',
            'ERROR Backup aborted due to failed run conditions',
        ]
        # Assert messages are found
        for msg in msgs:
            self.assertIn(msg, log_content, f"{msg}: not found in the log file")

    def test_09_timeout_skip(self):
        self.__run_backup("skip_condition_timeout", 1)

        log_content = self.__read_log()
        msgs = [
            'DEBUG Run condition passed: \'echo Hi There\' (exit code: 0)',
            'DEBUG Run condition stdout: Hi There',
            'ERROR Command timed out after 1 seconds: \'sleep 3\'',
            'ERROR Run condition stderr: Command timed out after 1 seconds',
            'ERROR Backup aborted due to failed run conditions',
        ]
        # Assert messages are found
        for msg in msgs:
            self.assertIn(msg, log_content, f"{msg}: not found in the log file")

    def test_10_terminate_condition(self):
        self.__run_backup("terminate_condition_success", 0)

        log_content = self.__read_log()
        msgs = [
            'DEBUG Terminate condition stdout: /tmp/oma/oma_',
            'INFO Terminate condition succeeded: \'ls -la $OMA_CURRENT_DIR\'',
            'INFO All terminate conditions succeeded',
        ]
        # Assert messages are found
        for msg in msgs:
            self.assertIn(msg, log_content, f"{msg}: not found in the log file")

    def test_11_delete_before(self):
        self.__run_backup("delete_before", 0)

        log_content = self.__read_log()
        msgs = [
            'DEBUG Removing old backup directories before new backup',
            'INFO Removed old backup directories',
            'Backup is newer than last database change. Reusing previous backup'
        ]
        # Assert backup has been skipped
        for msg in msgs:
            self.assertIn(msg, log_content, f"{msg}: not found in the log file")

    def test_12_double_run(self):
        """
        Test that parallel execution is prevented when a second instance is started.
        Uses sleep_for_double_run.conf which has a 5-second sleep in run_conditions.
        """
        proc1 = None
        proc2 = None

        try:
            # Start first instance in background
            proc1 = subprocess.Popen(
                "./oma -c test_data/sleep_for_double_run.conf",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Give first instance more time to acquire the lock (but not complete)
            time.sleep(1)

            self.assertTrue(is_port_in_use(), "TCP Lock Port not open.")

            # Try to start second instance while first is still running
            proc2 = subprocess.Popen(
                "./oma -c test_data/run1.conf",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Wait for second instance to complete (should exit immediately)
            try:
                stdout2, stderr2 = proc2.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc2.kill()
                stdout2, stderr2 = proc2.communicate()
                self.fail("Second instance timed out, should have exited immediately")

            # Verify second instance exited with correct code
            self.assertEqual(proc2.returncode, 3,
                             f"Expected exit code 3 for second instance, got {proc2.returncode}")

            # Verify error message in stderr
            stderr2_str = stderr2.decode()
            self.assertIn("Another instance of OMA is already running", stderr2_str,
                          f"Expected error message not found in stderr: {stderr2_str}")
            self.assertIn("port", stderr2_str,
                          f"Expected 'port' mention in error message: {stderr2_str}")

            print(f"Second instance stderr: {stderr2_str}")
            print(f"Second instance exit code: {proc2.returncode}")
            print("✓ Parallel execution prevention test passed")

        finally:
            # Clean up both instances
            if proc1:
                proc1.terminate()
                try:
                    proc1.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc1.kill()
                    proc1.wait()

            if proc2 and proc2.poll() is None:
                proc2.terminate()
                try:
                    proc2.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc2.kill()
                    proc2.wait()

    def __run_backup(self, config: str = "run1", expected_exit_code: int = 0):
        response = subprocess.run(
            f"./oma -c test_data/{config}.conf",
            shell=True,
            check=False,
            capture_output=True
        )
        time.sleep(3)
        self.assertEqual(response.returncode, expected_exit_code)
        print(response.stdout.decode())
        print(response.stderr.decode())
        self.__read_zabbix_sender_log()

    def __read_log(self) -> str:
        # Open and read the log file
        log_file = '/tmp/oma/last.log'
        print("Reading log file: " + log_file)
        with open(log_file, "r") as f:
            log_content = f.read()

        print("=" * 120)
        print(log_content)
        print("=" * 120)

        return log_content

    def __read_zabbix_sender_log(self):
        log_file = '/tmp/zabbix_sender.log'
        with open(log_file, "r") as f:
            log_content = f.read()
        self.assertIn("Summary", log_content, f"Summary not found in {log_file}")


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


def is_port_in_use(host='127.0.0.1', port=45678):
    """Check if a port is in use (cannot be bound)"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            # If we can bind, port is free
            return False
    except OSError:
        # If we cannot bind, port is in use
        return True


if __name__ == "__main__":
    unittest.main()
