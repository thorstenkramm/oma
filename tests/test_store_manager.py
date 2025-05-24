import unittest
from unittest.mock import patch, mock_open
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


if __name__ == '__main__':
    unittest.main()
