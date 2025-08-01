import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
from datetime import datetime, timedelta

# Add the parent directory to sys.path to import the module
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mysql_dump import MySQLDump  # noqa: E402
from config import Config  # noqa: E402
from store_manager import StoreManager  # noqa: E402


class TestMySQLDump(unittest.TestCase):
    def setUp(self):
        # Create mocks for dependencies
        self.mock_config = MagicMock(spec=Config)
        self.mock_config.mysql_bin = "/usr/bin/mysql"
        self.mock_config.exclude_databases = ["information_schema", "performance_schema"]
        self.mock_config.parallelism = 2
        self.mock_config.skip_unchanged_dbs = True
        self.mock_config.mysqldump_options = ["--single-transaction", "--quick"]
        self.mock_config.link_type = "hard"

        self.mock_store_manager = MagicMock(spec=StoreManager)
        self.mock_store_manager.current_dir = MagicMock()  # Create the attribute first
        self.mock_store_manager.current_dir.path = "/tmp/backup"
        self.mock_store_manager.current_dir.bytes_free = 1000000000  # 1GB free

        self.mock_logger = MagicMock()

        # Create the MySQLDump instance with mocked dependencies
        self.mysql_dump = MySQLDump(
            config=self.mock_config,
            store_manager=self.mock_store_manager,
            logger=self.mock_logger
        )

        # Mock the MySQLInfo class
        self.mysql_dump.mysql_info = MagicMock()
        self.mysql_dump.mysql_info.data_dir = MagicMock()  # Create the attribute first
        self.mysql_dump.mysql_info.data_dir.bytes_used = 500000000

    def test_init(self):
        """Test initialization of MySQLDump."""
        self.assertEqual(self.mysql_dump.config, self.mock_config)
        self.assertEqual(self.mysql_dump.store_manager, self.mock_store_manager)
        self.assertEqual(self.mysql_dump.logger, self.mock_logger)

    def test_check_free_space_sufficient(self):
        """Test _check_free_space when there is enough space."""
        # Setup mock for get_backup_info
        mock_backup_info = MagicMock()
        mock_backup_info.compression_ratio = 0.5  # 50% compression
        self.mock_store_manager.get_backup_info.return_value = mock_backup_info

        # Call _check_free_space
        result = self.mysql_dump._check_free_space()

        # Verify result
        self.assertTrue(result)
        self.mock_logger.error.assert_not_called()

    def test_check_free_space_insufficient(self):
        """Test _check_free_space when there is not enough space."""
        # Setup mock for get_backup_info
        mock_backup_info = MagicMock()
        mock_backup_info.compression_ratio = 2.5  # 250% expansion (unlikely but for testing)
        self.mock_store_manager.get_backup_info.return_value = mock_backup_info

        # Reduce free space to force failure
        self.mock_store_manager.current_dir.bytes_free = 1000000  # 1MB free

        # Call _check_free_space
        result = self.mysql_dump._check_free_space()

        # Verify result
        self.assertFalse(result)
        self.mock_logger.error.assert_called_once_with("Not enough free space in target directory.")

    @patch('subprocess.Popen')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_mysqldump_to_gzip_success(self, mock_remove, mock_exists, mock_temp_file, mock_popen):
        """Test _mysqldump_to_gzip with successful execution."""
        # Setup mocks
        mock_temp = MagicMock()
        mock_temp.name = "/tmp/temp_file"
        mock_temp_file.return_value.__enter__.return_value = mock_temp

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (None, b"")
        mock_popen.return_value.__enter__.return_value = mock_process

        mock_exists.return_value = True

        # Setup mock for get_database_last_change and get_database_backup_time
        self.mysql_dump.mysql_info.get_database_last_change.return_value = datetime.now() - timedelta(hours=1)
        self.mock_store_manager.get_database_backup_time.return_value = datetime.now() - timedelta(hours=2)

        # Mock open to return completion message
        with patch('builtins.open', mock_open(read_data="-- Dump completed on 2023-01-01 12:00:00")):
            # Call _mysqldump_to_gzip
            result = self.mysql_dump._mysqldump_to_gzip("test")

            # Verify result
            self.assertEqual(result, "/tmp/backup/test.sql.gz")

            # Verify store_database_backup_time was called
            self.mock_store_manager.store_database_backup_time.assert_called_once_with("test")

            # Verify temp file was removed
            mock_remove.assert_called_once_with("/tmp/temp_file")

    @patch('subprocess.Popen')
    def test_mysqldump_to_gzip_failure(self, mock_popen):
        """Test _mysqldump_to_gzip with failed execution."""
        # Setup mocks
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (None, b"Error message")
        mock_popen.return_value.__enter__.return_value = mock_process

        # Setup mock for get_database_last_change and get_database_backup_time
        self.mysql_dump.mysql_info.get_database_last_change.return_value = datetime.now() - timedelta(hours=1)
        self.mock_store_manager.get_database_backup_time.return_value = datetime.now() - timedelta(hours=2)

        # Mock tempfile.NamedTemporaryFile
        with patch('tempfile.NamedTemporaryFile', return_value=MagicMock(name="/tmp/temp_file")):
            # Call _mysqldump_to_gzip and expect exception
            with self.assertRaises(Exception):
                self.mysql_dump._mysqldump_to_gzip("test")

            # Verify error was logged
            self.mock_logger.error.assert_called()

    def test_mysqldump_to_gzip_reuse_previous(self):
        """Test _mysqldump_to_gzip when previous backup is newer than last change."""
        # Setup mock for get_database_last_change and get_database_backup_time
        self.mysql_dump.mysql_info.get_database_last_change.return_value = datetime.now() - timedelta(hours=2)
        self.mock_store_manager.get_database_backup_time.return_value = datetime.now() - timedelta(hours=1)

        # Call _mysqldump_to_gzip
        result = self.mysql_dump._mysqldump_to_gzip("test")

        # Verify result
        self.assertEqual(result, "ok")

        # Verify reuse_previous_backup was called
        self.mock_store_manager.reuse_previous_backup.assert_called_once_with("test")

        # Verify no subprocess was called
        self.mock_logger.error.assert_not_called()

    @patch('subprocess.Popen')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_mysqldump_to_gzip_encoding_issue(self, mock_remove, mock_exists, mock_temp_file, mock_popen):
        """Test _mysqldump_to_gzip with encoding issues in the completion message."""
        # Setup mocks
        mock_temp = MagicMock()
        mock_temp.name = "/tmp/temp_file"
        mock_temp_file.return_value.__enter__.return_value = mock_temp

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (None, b"")
        mock_popen.return_value.__enter__.return_value = mock_process

        mock_exists.return_value = True

        # Setup mock for get_database_last_change and get_database_backup_time
        self.mysql_dump.mysql_info.get_database_last_change.return_value = datetime.now() - timedelta(hours=1)
        self.mock_store_manager.get_database_backup_time.return_value = datetime.now() - timedelta(hours=2)

        # Mock open to return completion message with non-UTF8 character (0xb5 = µ in Latin-1)
        completion_msg = b"-- Dump completed on 2023-01-01 12:00:00 \xb5"

        # Create a mock that handles both text and binary mode
        def mock_open_func(path, mode='r', **kwargs):
            if 'b' in mode:
                # Binary mode
                mock_file = MagicMock()
                mock_file.read.return_value = completion_msg
                mock_file.__enter__.return_value = mock_file
                mock_file.__exit__.return_value = None
                return mock_file
            else:
                # Text mode - this should raise UnicodeDecodeError
                raise UnicodeDecodeError('utf-8', completion_msg, 42, 43, 'invalid start byte')

        with patch('builtins.open', side_effect=mock_open_func):
            # Call _mysqldump_to_gzip
            result = self.mysql_dump._mysqldump_to_gzip("test")

            # Verify result
            self.assertEqual(result, "/tmp/backup/test.sql.gz")

            # Verify store_database_backup_time was called
            self.mock_store_manager.store_database_backup_time.assert_called_once_with("test")

            # Verify warning was logged about encoding issue
            warning_calls = [call for call in self.mock_logger.warning.call_args_list]
            self.assertTrue(any("Failed to read temp file with UTF-8 encoding" in str(call) for call in warning_calls))

            # Verify temp file was removed
            mock_remove.assert_called_once_with("/tmp/temp_file")


if __name__ == '__main__':
    unittest.main()
