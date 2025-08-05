import unittest
from tempfile import NamedTemporaryFile
from unittest.mock import patch, MagicMock
import sys
import os

from config import ZbxConfig

# Add the parent directory to sys.path to import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from zabbix_sender import ZabbixSender  # noqa: E402
from mysql_dump import BackupResult  # noqa: E402
from logger import new_logger  # noqa: E402


class TestZabbixSender(unittest.TestCase):
    def setUp(self):
        # Create a sample backup result for testing
        self.backup_result = BackupResult(total=5, successful=3, failed=1, skipped=1)

        # Create a temporary log file for testing
        with NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            self.log_file = f.name

        self.logger = new_logger(self.log_file, 'debug')
        self.logger.info("Test log entry")

        zbx_config = ZbxConfig(
            item_key='mysql.backup.status',
            sender_bin='zabbix_sender',
            agent_conf='/etc/zabbix/zabbix_agent.conf',
        )
        self.sender = ZabbixSender(zbx_config, self.logger)

    def tearDown(self):
        # Clean up the temporary log file
        if os.path.exists(self.log_file):
            os.unlink(self.log_file)

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
        self.sender.send_value("success")

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
        mock_process.stdout = "Failed output"
        mock_process.stderr = "Connection refused"
        mock_run.return_value = mock_process

        # Call the method
        self.sender.send_value("test_value")

        # Read log and verify the error created by the zabbix_sender sub process is logged
        log_content = self.logger.read_log()
        self.assertIn("exit_code=1", log_content)
        self.assertIn("Connection refused", log_content)
        self.assertIn("Failed output", log_content)

    @patch('subprocess.run')
    def test_send_log_file_small(self, mock_run):
        """Test sending a small log file that doesn't need truncation."""
        # Setup mock
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        # Add some content to the log
        self.logger.info("Small test log content")
        self.logger.error("Test error message")

        # Call the method
        self.sender.send_log_file(self.backup_result)

        # Verify subprocess.run was called
        mock_run.assert_called_once()

        # Get the actual content that was sent
        sent_content = mock_run.call_args[0][0][6]

        # Verify the summary is included
        self.assertIn("Summary: Successfully dumped 3 of 5 databases", sent_content)
        self.assertIn("Skipped 1, Failed 1", sent_content)

        # Verify log content is included
        self.assertIn("Small test log content", sent_content)
        self.assertIn("Test error message", sent_content)

        # Verify no truncation message
        self.assertNotIn("has been truncated", sent_content)

    @patch('subprocess.run')
    def test_send_log_file_large(self, mock_run):
        """Test sending a large log file that needs truncation."""
        # Setup mock
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_run.return_value = mock_process

        # Create a large log content
        # Each line is about 100 chars, so we need ~700 lines to exceed 65536 bytes
        for i in range(800):
            self.logger.info(f"This is log line {i:04d} with some extra content to make it longer - " + "x" * 50)

        # Call the method
        self.sender.send_log_file(self.backup_result)

        # Verify subprocess.run was called
        mock_run.assert_called_once()

        # Get the actual content that was sent
        sent_content = mock_run.call_args[0][0][6]

        # Verify the content was truncated
        self.assertLess(len(sent_content), 65536)
        self.assertIn("has been truncated", sent_content)
        self.assertIn(self.log_file, sent_content)  # Should mention the log file path

        # Verify summary is still included
        self.assertIn("Summary: Successfully dumped 3 of 5 databases", sent_content)

    def test_send_value_no_item_key(self):
        """Test that send_value does nothing when item_key is empty."""
        # Create sender with no item key
        zbx_config = ZbxConfig(
            item_key='',
            sender_bin='zabbix_sender',
            agent_conf='/etc/zabbix/zabbix_agent.conf',
        )
        sender = ZabbixSender(zbx_config, self.logger)

        with patch('subprocess.run') as mock_run:
            sender.send_value("test")
            # Should not call subprocess.run
            mock_run.assert_not_called()

    def test_send_log_file_no_item_key(self):
        """Test that send_log_file does nothing when item_key is empty."""
        # Create sender with no item key
        zbx_config = ZbxConfig(
            item_key='',
            sender_bin='zabbix_sender',
            agent_conf='/etc/zabbix/zabbix_agent.conf',
        )
        sender = ZabbixSender(zbx_config, self.logger)

        with patch('subprocess.run') as mock_run:
            sender.send_log_file(self.backup_result)
            # Should not call subprocess.run
            mock_run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
