import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import tempfile
import time
import datetime
import subprocess

# Import the module and classes/functions to test
from dir_info import DirInfo, get_dir_info, get_dir_size, get_dir_last_change


class TestDirInfoFunctions(unittest.TestCase):

    def setUp(self):
        """Set up a temporary directory for filesystem tests."""
        self.test_dir = tempfile.mkdtemp()
        # Create some structure for get_dir_last_change tests
        self.file1_path = os.path.join(self.test_dir, "file1.txt")
        self.subdir_path = os.path.join(self.test_dir, "subdir")
        self.file2_path = os.path.join(self.subdir_path, "file2.txt")

        os.makedirs(self.subdir_path)

        # Create files with slightly different timestamps
        with open(self.file1_path, 'w') as f:
            f.write("content1")
        time.sleep(0.01)  # Ensure different timestamps
        self.time_file1 = os.path.getmtime(self.file1_path)

        with open(self.file2_path, 'w') as f:
            f.write("content2")
        time.sleep(0.01)  # Ensure different timestamps
        self.time_file2 = os.path.getmtime(self.file2_path)

    def tearDown(self):
        """Clean up the temporary directory."""
        shutil.rmtree(self.test_dir)

    # --- Tests for get_dir_size ---

    @patch('subprocess.run')
    def test_get_dir_size_success(self, mock_run):
        """Test get_dir_size with successful subprocess call."""
        mock_process = MagicMock()
        mock_process.stdout = "12345\t/fake/dir\n"
        mock_process.stderr = ""
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        size = get_dir_size("/fake/dir")

        self.assertEqual(size, 12345 * 1024)  # Mock returns bytes,
        mock_run.assert_called_once_with(
            ['du', '-sk', '/fake/dir'],
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8'
        )

    @patch('subprocess.run')
    def test_get_dir_size_empty_output(self, mock_run):
        """Test get_dir_size when 'du' returns empty output."""
        mock_process = MagicMock()
        mock_process.stdout = ""  # Empty output
        mock_process.stderr = ""
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        with self.assertRaisesRegex(ValueError, "'du -sk /fake/dir' produced empty output."):
            get_dir_size("/fake/dir")

    @patch('subprocess.run')
    def test_get_dir_size_subprocess_error(self, mock_run):
        """Test get_dir_size when subprocess raises CalledProcessError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            cmd=['du', '-sk', '/fake/dir'],
            returncode=1,
            stderr="du: cannot access '/fake/dir': No such file or directory"
        )

        with self.assertRaises(subprocess.CalledProcessError):
            get_dir_size("/fake/dir")

    # --- Tests for get_dir_last_change ---

    def test_get_dir_last_change_success(self):
        """Test get_dir_last_change finds the most recent file."""
        # file2 should be the most recent
        expected_dt = datetime.datetime.fromtimestamp(self.time_file2)
        actual_dt = get_dir_last_change(self.test_dir)
        # Compare timestamps with a small tolerance for precision issues
        self.assertAlmostEqual(actual_dt, expected_dt, delta=datetime.timedelta(seconds=0.1))

    def test_get_dir_last_change_not_found(self):
        """Test get_dir_last_change with a non-existent directory."""
        non_existent_path = os.path.join(self.test_dir, "not_a_real_dir")
        with self.assertRaisesRegex(FileNotFoundError, f"Directory does not exist: {non_existent_path}"):
            get_dir_last_change(non_existent_path)

    def test_get_dir_last_change_empty_dir(self):
        """Test get_dir_last_change with an empty directory."""
        empty_dir = os.path.join(self.test_dir, "empty")
        os.makedirs(empty_dir)
        with self.assertRaisesRegex(FileNotFoundError, f"No accessible files found in directory: {empty_dir}"):
            get_dir_last_change(empty_dir)

    def test_get_dir_last_change_dir_with_only_subdir(self):
        """Test get_dir_last_change with a directory containing only an empty subdirectory."""
        dir_only_subdir = os.path.join(self.test_dir, "only_subdir")
        os.makedirs(os.path.join(dir_only_subdir, "sub"))
        with self.assertRaisesRegex(FileNotFoundError, f"No accessible files found in directory: {dir_only_subdir}"):
            get_dir_last_change(dir_only_subdir)

    # --- Tests for get_dir_info ---

    @patch('dir_info.get_dir_size')  # Patch within the dir_info module where it's used
    @patch('shutil.disk_usage')
    def test_get_dir_info_success(self, mock_disk_usage, mock_get_dir_size):
        """Test get_dir_info successfully combines info."""
        # Configure mocks
        # Create a mock object that mimics the return value of shutil.disk_usage
        mock_usage_result = MagicMock()
        mock_usage_result.total = 1000000
        mock_usage_result.used = 200000
        mock_usage_result.free = 800000
        mock_disk_usage.return_value = mock_usage_result

        mock_get_dir_size.return_value = 54321  # Mocked size of files within the dir

        test_path = "/some/test/path"
        dir_info_result = get_dir_info(test_path)

        # Assertions
        self.assertIsInstance(dir_info_result, DirInfo)
        self.assertEqual(dir_info_result.path, test_path)
        self.assertEqual(dir_info_result.bytes_free, 800000)  # From mock_disk_usage
        self.assertEqual(dir_info_result.bytes_used, 54321)  # From mock_get_dir_size

        # Verify mocks were called
        mock_disk_usage.assert_called_once_with(test_path)
        mock_get_dir_size.assert_called_once_with(test_path)


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
