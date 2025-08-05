import unittest
from unittest.mock import Mock, patch, MagicMock
import logging
import subprocess

from conditions_manager import ConditionsManager
from config import ConditionsConfig


class TestConditionsManager(unittest.TestCase):
    def setUp(self):
        self.logger = Mock(spec=logging.Logger)
        self.logger.level = logging.INFO

    def test_skip_conditions_no_conditions(self):
        """Test skip conditions when no conditions are configured"""
        config = ConditionsConfig(
            skip_conditions=[],
            skip_conditions_timeout=0,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.check_skip_conditions()
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_skip_conditions_success(self, mock_run):
        """Test skip conditions when one condition succeeds"""
        mock_run.return_value = MagicMock(returncode=0, stdout='success', stderr='')

        config = ConditionsConfig(
            skip_conditions=['test command 1', 'test command 2'],
            skip_conditions_timeout=10,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.check_skip_conditions()
        self.assertTrue(result)
        # Should stop after first success
        self.assertEqual(mock_run.call_count, 1)

    @patch('subprocess.run')
    def test_skip_conditions_all_fail(self, mock_run):
        """Test skip conditions when all conditions fail"""
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='error')

        config = ConditionsConfig(
            skip_conditions=['test command 1', 'test command 2'],
            skip_conditions_timeout=10,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.check_skip_conditions()
        self.assertFalse(result)
        # Should try all conditions
        self.assertEqual(mock_run.call_count, 2)

    def test_run_conditions_no_conditions(self):
        """Test run conditions when no conditions are configured"""
        config = ConditionsConfig(
            skip_conditions=[],
            skip_conditions_timeout=0,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.check_run_conditions()
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_run_conditions_all_success(self, mock_run):
        """Test run conditions when all conditions succeed"""
        mock_run.return_value = MagicMock(returncode=0, stdout='success', stderr='')

        config = ConditionsConfig(
            skip_conditions=[],
            skip_conditions_timeout=0,
            run_conditions=['test command 1', 'test command 2'],
            run_conditions_timeout=10,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.check_run_conditions()
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)

    @patch('subprocess.run')
    def test_run_conditions_one_fails(self, mock_run):
        """Test run conditions when one condition fails"""
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='error')

        config = ConditionsConfig(
            skip_conditions=[],
            skip_conditions_timeout=0,
            run_conditions=['test command 1', 'test command 2'],
            run_conditions_timeout=10,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.check_run_conditions()
        self.assertFalse(result)
        # Should stop after first failure
        self.assertEqual(mock_run.call_count, 1)

    def test_terminate_conditions_no_conditions(self):
        """Test terminate conditions when no conditions are configured"""
        config = ConditionsConfig(
            skip_conditions=[],
            skip_conditions_timeout=0,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.execute_terminate_conditions('/path/to/backup')
        self.assertTrue(result)

    @patch('subprocess.run')
    def test_terminate_conditions_all_success(self, mock_run):
        """Test terminate conditions when all conditions succeed"""
        mock_run.return_value = MagicMock(returncode=0, stdout='success', stderr='')

        config = ConditionsConfig(
            skip_conditions=[],
            skip_conditions_timeout=0,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=['rsync command', 'notify command'],
            terminate_conditions_timeout=300
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.execute_terminate_conditions('/path/to/backup')
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)

        # Check that environment variable was set
        for call in mock_run.call_args_list:
            env = call.kwargs['env']
            self.assertEqual(env['OMA_CURRENT_DIR'], '/path/to/backup')

    @patch('subprocess.run')
    def test_terminate_conditions_one_fails(self, mock_run):
        """Test terminate conditions when one condition fails"""
        # First command succeeds, second fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='success', stderr=''),
            MagicMock(returncode=1, stdout='', stderr='error')
        ]

        config = ConditionsConfig(
            skip_conditions=[],
            skip_conditions_timeout=0,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=['rsync command', 'notify command'],
            terminate_conditions_timeout=300
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.execute_terminate_conditions('/path/to/backup')
        self.assertFalse(result)
        # Should execute all conditions even if one fails
        self.assertEqual(mock_run.call_count, 2)

    @patch('subprocess.run')
    def test_timeout_handling(self, mock_run):
        """Test timeout handling"""
        mock_run.side_effect = subprocess.TimeoutExpired('cmd', 10)

        config = ConditionsConfig(
            skip_conditions=['test command'],
            skip_conditions_timeout=10,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.check_skip_conditions()
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_exception_handling(self, mock_run):
        """Test general exception handling"""
        mock_run.side_effect = Exception('Test exception')

        config = ConditionsConfig(
            skip_conditions=['test command'],
            skip_conditions_timeout=0,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.check_skip_conditions()
        self.assertFalse(result)

    @patch('subprocess.run')
    def test_debug_logging(self, mock_run):
        """Test debug logging behavior"""
        self.logger.level = logging.DEBUG
        mock_run.return_value = MagicMock(returncode=0, stdout='debug output', stderr='')

        config = ConditionsConfig(
            skip_conditions=['test command'],
            skip_conditions_timeout=0,
            run_conditions=[],
            run_conditions_timeout=0,
            terminate_conditions=[],
            terminate_conditions_timeout=0
        )
        manager = ConditionsManager(config, self.logger)

        result = manager.check_skip_conditions()
        self.assertTrue(result)
        # Should log stdout in debug mode
        self.logger.debug.assert_any_call('Skip condition stdout: debug output')


if __name__ == '__main__':
    unittest.main()
