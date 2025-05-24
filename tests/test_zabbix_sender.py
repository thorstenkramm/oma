import unittest
from unittest.mock import patch, MagicMock
import subprocess
import sys
import os

# Add the parent directory to sys.path to import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from zabbix_sender import ZabbixSender  # noqa: E402
from mysql_dump import BackupResult  # noqa: E402


class TestZabbixSender(unittest.TestCase):
    def setUp(self):
        # Create a sample backup result for testing
        self.backup_result = BackupResult(total=5, successful=3, failed=1, skipped=1)
        self.sender = ZabbixSender(
            backup_result=self.backup_result,
            sender_bin="zabbix_sender",
            agent_conf="/etc/zabbix/zabbix_agent.conf"
        )

    @patch('subprocess.run')
    def test_send_value(self, mock_run):
        """Test sending a simple value to Zabbix."""
        # Setup mock
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "Processed: 1; Failed: 0; Total: 1"
        mock_process.stderr = ""
        mock_run.return_value = mock_process

        # Call the method
        self.sender.send_value("mysql.backup.status", "success")

        # Verify subprocess.run was called with correct arguments
        mock_run.assert_called_once_with(
            [
                'zabbix_sender',
                '-c',
                '/etc/zabbix/zabbix_agent.conf',
                '-k',
                'mysql.backup.status',
                '-o',
                'success'
            ],
            capture_output=True,
            text=True
        )

    @patch('subprocess.run')
    def test_send_value_error(self, mock_run):
        """Test error handling when sending a value fails."""
        # Setup mock to simulate failure
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = ""
        mock_process.stderr = "Error"
        mock_run.return_value = mock_process

        # Verify that CalledProcessError is raised
        with self.assertRaises(subprocess.CalledProcessError):
            self.sender.send_value("mysql.backup.status", "failed")

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="Test log content")
    @patch('subprocess.run')
    def test_send_file_small(self, mock_run, mock_open):
        """Test sending a small file that doesn't need truncation."""
        # Setup mock
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        # Call the method
        self.sender.send_file("mysql.backup.log", "/tmp/backup.log")

        # Verify the file was read and content was sent
        mock_open.assert_called_once_with('/tmp/backup.log', 'r', encoding='utf-8')
        mock_run.assert_called_once()
        # Verify the content was sent without truncation
        self.assertIn("Test log content", mock_run.call_args[0][0][6])

    @patch('builtins.open')
    @patch('subprocess.run')
    def test_send_file_large(self, mock_run, mock_open):
        """Test sending a large file that needs truncation."""
        # Create a large string that exceeds the max bytes
        large_content = "x" * 70000  # Larger than 65536

        # Setup mock file
        mock_file = MagicMock()
        mock_file.read.return_value = large_content.encode()
        mock_open.return_value.__enter__.return_value = mock_file

        # Setup subprocess mock
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        # Call the method
        self.sender.send_file("mysql.backup.log", "/tmp/large_backup.log")

        # Verify the file was read
        mock_open.assert_called_once_with('/tmp/large_backup.log', 'r', encoding='utf-8')

        # Verify subprocess.run was called
        mock_run.assert_called_once()

        # Verify the content was truncated
        sent_content = mock_run.call_args[0][0][6]
        self.assertLess(len(sent_content), 65536)
        self.assertIn("has been truncated", sent_content)

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        sender = ZabbixSender(backup_result=self.backup_result)
        self.assertEqual(sender.sender_bin, "zabbix_sender")
        self.assertEqual(sender.agent_conf, "/etc/zabbix/zabbix_agent.conf")
        self.assertEqual(sender.backup_result, self.backup_result)


if __name__ == '__main__':
    unittest.main()
