import unittest
from unittest.mock import patch, mock_open, MagicMock
from datetime import datetime
from store_manager import StoreManager  # Assuming StoreManager is the class containing the method


class TestStoreManager(unittest.TestCase):
    def setUp(self):
        # Provide a mock backup directory path
        backup_dir = '/tmp'

        # Setup a StoreManager instance with the backup_dir parameter
        self.store_manager = StoreManager(backup_dir=backup_dir)

        # Mocking an object for previous_dir
        self.store_manager.previous_dir = type('', (), {})()
        self.store_manager.previous_dir.path = '/mock/path'

    @patch('builtins.open', new_callable=mock_open, read_data='2023-10-01T12:00:00')
    @patch('os.path.join', return_value='/mock/path/database.timestamp')
    def test_get_previous_database_backup_time(self, mock_join, mock_open):
        # Test the method with a mocked timestamp file
        database = 'database'
        expected_time = datetime.fromisoformat('2023-10-01T12:00:00')

        result = self.store_manager.get_previous_database_backup_time(database)

        self.assertEqual(result, expected_time)
        mock_join.assert_called_once_with('/mock/path', 'database.timestamp')
        mock_open.assert_called_once_with('/mock/path/database.timestamp', 'r')

    @patch('os.path.join', return_value='/mock/path/database.timestamp')
    def test_get_previous_database_backup_time_file_not_found(self, mock_join):
        # Test the method when the timestamp file does not exist
        database = 'database'
        expected_time = datetime(1900, 1, 1, 0, 0, 0)

        with patch('builtins.open', side_effect=FileNotFoundError):
            result = self.store_manager.get_previous_database_backup_time(database)

        self.assertEqual(result, expected_time)
        mock_join.assert_called_once_with('/mock/path', 'database.timestamp')

    @patch('store_manager.shutil.rmtree')
    @patch('store_manager.os.rename')
    def test_remove_skipped(self, mock_rename, mock_rmtree):
        """Test the remove_skipped method - happy path"""
        # Set up current_dir mock
        self.store_manager.current_dir = MagicMock()
        self.store_manager.current_dir.path = '/tmp/oma_20231001-120000'
        self.store_manager.backup_dir = '/tmp'

        # Call the method
        self.store_manager.remove_skipped()

        # Verify os.rename was called to move the log file
        mock_rename.assert_called_once_with(
            '/tmp/oma_20231001-120000/oma.log',
            '/tmp/last.log'
        )

        # Verify shutil.rmtree was called to remove the directory
        mock_rmtree.assert_called_once_with('/tmp/oma_20231001-120000')

    @patch('store_manager.shutil.rmtree')
    @patch('store_manager.os.rename')
    def test_remove_skipped_with_different_paths(self, mock_rename, mock_rmtree):
        """Test remove_skipped with different directory paths"""
        # Set up with different paths
        self.store_manager.current_dir = MagicMock()
        self.store_manager.current_dir.path = '/var/backups/mysql/oma_20231002-180000'
        self.store_manager.backup_dir = '/var/backups/mysql'

        # Call the method
        self.store_manager.remove_skipped()

        # Verify correct paths are used
        mock_rename.assert_called_once_with(
            '/var/backups/mysql/oma_20231002-180000/oma.log',
            '/var/backups/mysql/last.log'
        )
        mock_rmtree.assert_called_once_with('/var/backups/mysql/oma_20231002-180000')

    @patch('shutil.rmtree')
    @patch('os.rename', side_effect=FileNotFoundError('Log file not found'))
    def test_remove_skipped_no_log_file(self, mock_rename, mock_rmtree):
        """Test remove_skipped when log file doesn't exist"""
        # Set up current_dir mock
        self.store_manager.current_dir = MagicMock()
        self.store_manager.current_dir.path = '/tmp/oma_20231001-120000'
        self.store_manager.backup_dir = '/tmp'

        # The method should raise the exception since it doesn't handle FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            self.store_manager.remove_skipped()

        # Verify rename was attempted
        mock_rename.assert_called_once()

        # Verify rmtree was not called since rename failed
        mock_rmtree.assert_not_called()


if __name__ == '__main__':
    unittest.main()
