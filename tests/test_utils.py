import os
import shutil
import tempfile
import unittest
from unittest import mock

import utils


class TestFormatBytes(unittest.TestCase):
    """Test the format_bytes function."""

    def test_zero_bytes(self):
        """Test formatting zero bytes."""
        self.assertEqual(utils.format_bytes(0), "0B")

    def test_bytes(self):
        """Test formatting bytes."""
        self.assertEqual(utils.format_bytes(500), "500.00 B")

    def test_kilobytes(self):
        """Test formatting kilobytes."""
        self.assertEqual(utils.format_bytes(1024), "1.00 KB")
        self.assertEqual(utils.format_bytes(1500), "1.46 KB")

    def test_megabytes(self):
        """Test formatting megabytes."""
        self.assertEqual(utils.format_bytes(1024 * 1024), "1.00 MB")
        self.assertEqual(utils.format_bytes(1.5 * 1024 * 1024), "1.50 MB")

    def test_gigabytes(self):
        """Test formatting gigabytes."""
        self.assertEqual(utils.format_bytes(1024 * 1024 * 1024), "1.00 GB")
        self.assertEqual(utils.format_bytes(2.5 * 1024 * 1024 * 1024), "2.50 GB")

    def test_terabytes(self):
        """Test formatting terabytes."""
        self.assertEqual(utils.format_bytes(1024 * 1024 * 1024 * 1024), "1.00 TB")

    def test_petabytes(self):
        """Test formatting petabytes."""
        self.assertEqual(utils.format_bytes(1024 * 1024 * 1024 * 1024 * 1024), "1.00 PB")


class TestSwapFileForLink(unittest.TestCase):
    """Test the swap_file_for_link function."""

    def setUp(self):
        """Set up temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.source_file = os.path.join(self.temp_dir, "source.txt")
        self.dest_dir = os.path.join(self.temp_dir, "dest")
        self.dest_file = os.path.join(self.dest_dir, "source.txt")

        # Create source file with content
        with open(self.source_file, "w") as f:
            f.write("test content")

    def tearDown(self):
        """Clean up temporary directory after tests."""
        shutil.rmtree(self.temp_dir)

    def test_swap_file_for_symbolic_link(self):
        """Test swapping a file for a symbolic link."""
        utils.swap_file_for_link(self.source_file, self.dest_file,"symbolic")

        # Check that destination file exists and has the content
        self.assertTrue(os.path.exists(self.dest_file))
        with open(self.dest_file, "r") as f:
            self.assertEqual(f.read(), "test content")

        # Check that source is now a symlink to destination
        self.assertTrue(os.path.islink(self.source_file))
        self.assertEqual(os.readlink(self.source_file), self.dest_file)

    def test_swap_file_for_hard_link(self):
        """Test swapping a file for a hard link."""
        utils.swap_file_for_link(self.source_file, self.dest_file,"hard")

        # Check that destination file exists and has the content
        self.assertTrue(os.path.exists(self.dest_file))
        with open(self.dest_file, "r") as f:
            self.assertEqual(f.read(), "test content")

        # Check if file has multiple hard links
        self.assertGreater(os.stat(self.source_file).st_nlink, 1)

        # And check if two files are hard links to each other
        source_stat = os.stat(self.source_file)
        dest_stat = os.stat(self.dest_file)
        self.assertEqual(source_stat.st_ino, dest_stat.st_ino)
        self.assertEqual(source_stat.st_dev, dest_stat.st_dev)

    def test_source_file_not_exists(self):
        """Test error when source file doesn't exist."""
        non_existent_file = os.path.join(self.temp_dir, "non_existent.txt")
        with self.assertRaises(FileNotFoundError):
            utils.swap_file_for_link(non_existent_file, self.dest_file)

    def test_create_destination_directory(self):
        """Test that destination directory is created if it doesn't exist."""
        nested_dest = os.path.join(self.dest_dir, "nested", "source.txt")
        utils.swap_file_for_link(self.source_file, nested_dest)

        # Check that nested directory was created
        self.assertTrue(os.path.exists(os.path.dirname(nested_dest)))
        # Check that destination file exists
        self.assertTrue(os.path.exists(nested_dest))


class TestCalcParallelism(unittest.TestCase):
    """Test the calc_parallelism function."""

    @mock.patch('multiprocessing.cpu_count', return_value=8)
    def test_positive_desired(self, mock_cpu_count):
        """Test with positive desired value."""
        self.assertEqual(utils.calc_parallelism(4), 4)

    @mock.patch('multiprocessing.cpu_count', return_value=8)
    def test_zero_desired(self, mock_cpu_count):
        """Test with zero desired value."""
        self.assertEqual(utils.calc_parallelism(0), 8)

    @mock.patch('multiprocessing.cpu_count', return_value=8)
    def test_negative_desired(self, mock_cpu_count):
        """Test with negative desired value."""
        # Should return cpu_count + desired if result is positive
        self.assertEqual(utils.calc_parallelism(-2), 6)
        self.assertEqual(utils.calc_parallelism(-4), 4)

    @mock.patch('multiprocessing.cpu_count', return_value=8)
    def test_large_negative_desired(self, mock_cpu_count):
        """Test with large negative desired value."""
        # Should return 1 if cpu_count + desired <= 0
        self.assertEqual(utils.calc_parallelism(-8), 1)
        self.assertEqual(utils.calc_parallelism(-10), 1)


if __name__ == "__main__":
    unittest.main()
