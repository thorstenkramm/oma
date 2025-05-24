import unittest
import logging
import os
import tempfile
import shutil
from logger import new_logger


class TestLogger(unittest.TestCase):
    """Test cases for the logger module."""

    def setUp(self):
        """Set up test environment before each test."""
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()

        # Store original handlers to restore later
        self.root_handlers = logging.root.handlers.copy()

        # Clear any existing handlers on the root logger
        logging.root.handlers = []

    def tearDown(self):
        """Clean up after each test."""
        # Remove the temporary directory and all its contents
        shutil.rmtree(self.test_dir)

        # Restore original handlers
        logging.root.handlers = self.root_handlers

        # Reset the smart-mysqldump logger if it exists
        if 'smart-mysqldump' in logging.Logger.manager.loggerDict:
            logger = logging.getLogger('smart-mysqldump')
            logger.handlers = []
            logger.setLevel(logging.NOTSET)

    def test_default_logger(self):
        """Test creating a logger with default parameters."""
        logger = new_logger()

        # Check default log level (info)
        self.assertEqual(logger.level, logging.INFO)

        # Check that there's exactly one handler (console)
        self.assertEqual(len(logger.handlers), 1)
        self.assertIsInstance(logger.handlers[0], logging.StreamHandler)

    def test_logger_with_file(self):
        """Test creating a logger with a log file."""
        log_file = os.path.join(self.test_dir, "test.log")
        logger = new_logger(log_file=log_file)

        # Check default log level (info)
        self.assertEqual(logger.level, logging.INFO)

        # Check that there is exactly one handlers
        self.assertEqual(len(logger.handlers), 1)

        # Check that one handler is a FileHandler
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        self.assertEqual(len(file_handlers), 1)

        # Check that the file handler has the correct path
        self.assertEqual(file_handlers[0].baseFilename, log_file)

        # Test logging to file
        test_message = "Test log message"
        logger.info(test_message)

        # Check that the message was written to the file
        with open(log_file, 'r') as f:
            log_content = f.read()
        self.assertIn(test_message, log_content)

    def test_logger_with_debug_level(self):
        """Test creating a logger with debug level."""
        logger = new_logger(log_level="debug")

        # Check log level is set to debug
        self.assertEqual(logger.level, logging.DEBUG)

        # Check handler levels
        for handler in logger.handlers:
            self.assertEqual(handler.level, logging.DEBUG)

    def test_logger_with_warning_level(self):
        """Test creating a logger with warning level."""
        logger = new_logger(log_level="warning")

        # Check log level is set to warning
        self.assertEqual(logger.level, logging.WARNING)

        # Check handler levels
        for handler in logger.handlers:
            self.assertEqual(handler.level, logging.WARNING)

    def test_logger_with_error_level(self):
        """Test creating a logger with error level."""
        logger = new_logger(log_level="error")

        # Check log level is set to error
        self.assertEqual(logger.level, logging.ERROR)

        # Check handler levels
        for handler in logger.handlers:
            self.assertEqual(handler.level, logging.ERROR)

    def test_logger_with_invalid_level(self):
        """Test creating a logger with an invalid log level."""
        logger = new_logger(log_level="invalid_level")

        # Check that it defaults to INFO
        self.assertEqual(logger.level, logging.INFO)

    def test_logger_overwrites_existing_file(self):
        """Test that the logger overwrites existing log files."""
        log_file = os.path.join(self.test_dir, "test.log")

        # Create a file with some content
        with open(log_file, 'w') as f:
            f.write("Existing content\n")

        # Create logger and log a message
        logger = new_logger(log_file=log_file)
        logger.info("New log message")

        # Check that the file was overwritten (not appended)
        with open(log_file, 'r') as f:
            log_content = f.read()

        self.assertNotIn("Existing content", log_content)
        self.assertIn("New log message", log_content)

    def test_multiple_loggers_same_name(self):
        """Test creating multiple loggers with the same name."""
        # Create first logger
        logger1 = new_logger()

        # Create second logger with same name
        logger2 = new_logger()

        # They should be the same object
        self.assertIs(logger1, logger2)

        # But the second call should have cleared and reconfigured handlers
        self.assertEqual(len(logger2.handlers), 1)

    def test_logger_formatter(self):
        """Test that the logger uses the correct formatter."""
        log_file = os.path.join(self.test_dir, "test.log")
        logger = new_logger(log_file=log_file)

        # Log a test message
        logger.info("Test formatter")

        # Check the format in the log file
        with open(log_file, 'r') as f:
            log_content = f.read()

        # Check for the expected format parts
        self.assertRegex(log_content, r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}')  # timestamp
        self.assertIn('INFO', log_content)  # log level
        self.assertIn('Test formatter', log_content)  # message


if __name__ == '__main__':
    unittest.main()
