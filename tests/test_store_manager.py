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

    @patch('store_manager.get_dir_info')
    @patch('store_manager.shutil.rmtree')
    @patch('store_manager.glob.glob')
    def test_cleanup_before_refreshes_current_dir(self, mock_glob, mock_rmtree, mock_get_dir_info):
        """Test that cleanup_before refreshes current_dir.bytes_free after removing directories"""
        # Setup: simulate 3 existing backup dirs, versions=2 means 1 should be removed
        self.store_manager.backup_dir = '/backup'
        self.store_manager.current_dir = MagicMock()
        self.store_manager.current_dir.path = '/backup/oma_20231003-120000'

        mock_glob.return_value = [
            '/backup/oma_20231001-120000',
            '/backup/oma_20231002-120000',
            '/backup/oma_20231003-120000',
        ]

        # Mock get_dir_info to return a new DirInfo with updated bytes_free
        new_dir_info = MagicMock()
        new_dir_info.path = '/backup/oma_20231003-120000'
        new_dir_info.bytes_free = 500000000000  # 500 GB free after cleanup
        mock_get_dir_info.return_value = new_dir_info

        # Call cleanup_before with versions=2
        removed = self.store_manager.cleanup_before(versions=2)

        # Verify one directory was removed
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0], '/backup/oma_20231001-120000')

        # Verify get_dir_info was called to refresh current_dir
        mock_get_dir_info.assert_called_once_with('/backup/oma_20231003-120000')

        # Verify current_dir was updated
        self.assertEqual(self.store_manager.current_dir, new_dir_info)

    @patch('store_manager.get_dir_info')
    @patch('store_manager.shutil.rmtree')
    @patch('store_manager.glob.glob')
    def test_cleanup_before_no_refresh_when_nothing_removed(self, mock_glob, mock_rmtree, mock_get_dir_info):
        """Test that cleanup_before does NOT refresh current_dir when no directories are removed"""
        # Setup: only 2 backup dirs, versions=2 means nothing should be removed
        self.store_manager.backup_dir = '/backup'
        original_current_dir = MagicMock()
        original_current_dir.path = '/backup/oma_20231002-120000'
        original_current_dir.bytes_free = 100000000000  # 100 GB
        self.store_manager.current_dir = original_current_dir

        mock_glob.return_value = [
            '/backup/oma_20231001-120000',
            '/backup/oma_20231002-120000',
        ]

        # Call cleanup_before with versions=2
        removed = self.store_manager.cleanup_before(versions=2)

        # Verify no directories were removed
        self.assertEqual(len(removed), 0)

        # Verify get_dir_info was NOT called (no refresh needed)
        mock_get_dir_info.assert_not_called()

        # Verify current_dir is unchanged
        self.assertEqual(self.store_manager.current_dir, original_current_dir)


if __name__ == '__main__':
    unittest.main()
