import unittest
import os
import tempfile
from unittest.mock import patch
import shutil
from config import get_config


class TestConfig(unittest.TestCase):
    """Test cases for the config module."""

    def setUp(self):
        """Set up test environment before each test."""
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        self.backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        # Create a valid config file for testing
        self.valid_config_path = os.path.join(self.test_dir, "valid_config.toml")
        with open(self.valid_config_path, "w") as f:
            f.write(f"""
[main]
backup_dir = "{self.backup_dir}"
parallelism = 2
versions = 3
delete_before = true
mysqldump_bin = "/usr/bin/mysqldump"
mysql_bin = "/usr/bin/mysql"
mysqldump_options = ["--single-transaction", "--quick"]
exclude_databases = ["demo1", "demo2"]
log_level = "debug"
[zabbix]
item_key = "oma.log"
sender_bin = "./test_data/zabbix_sender"
agent_conf = "/tmp/zabbix_agent.conf"
""")

        # Create a minimal config file
        self.minimal_config_path = os.path.join(self.test_dir, "minimal_config.toml")
        with open(self.minimal_config_path, "w") as f:
            f.write(f"""
[main]
backup_dir = "{self.backup_dir}"
""")

        # Create an invalid config file (missing main section)
        self.invalid_config_path = os.path.join(self.test_dir, "invalid_config.toml")
        with open(self.invalid_config_path, "w") as f:
            f.write("""
[settings]
backup_dir = "/tmp"
""")

        # Create a config with missing required field
        self.missing_required_path = os.path.join(self.test_dir, "missing_required.toml")
        with open(self.missing_required_path, "w") as f:
            f.write("""
[main]
parallelism = 2
""")

        # Create a config with invalid backup_dir
        self.invalid_dir_path = os.path.join(self.test_dir, "invalid_dir.toml")
        with open(self.invalid_dir_path, "w") as f:
            f.write("""
[main]
backup_dir = "/path/that/does/not/exist"
""")

    def tearDown(self):
        """Clean up after each test."""
        # Remove the temporary directory and all its contents
        shutil.rmtree(self.test_dir)

    def test_valid_config(self):
        """Test loading a valid configuration file."""
        config = get_config(self.valid_config_path)

        # Verify all fields are loaded correctly
        self.assertEqual(config.backup_dir, self.backup_dir)
        self.assertEqual(config.parallelism, 2)
        self.assertEqual(config.versions, 3)
        self.assertTrue(config.delete_before)
        self.assertEqual(config.mysqldump_bin, "/usr/bin/mysqldump")
        self.assertEqual(config.mysql_bin, "/usr/bin/mysql")
        self.assertEqual(config.mysqldump_options, ["--single-transaction", "--quick"])
        self.assertEqual(config.exclude_databases, ['demo1', 'demo2'])
        self.assertEqual(config.log_level, "debug")
        self.assertEqual(config.skip_unchanged_dbs, False)
        self.assertEqual(config.zbx.item_key, "oma.log")
        self.assertEqual(config.zbx.sender_bin, "./test_data/zabbix_sender")
        self.assertEqual(config.zbx.agent_conf, "/tmp/zabbix_agent.conf")

    def test_minimal_config(self):
        """Test loading a minimal configuration file with defaults."""
        config = get_config(self.minimal_config_path)

        # Verify required field is set
        self.assertEqual(config.backup_dir, self.backup_dir)

        # Verify defaults are applied
        import multiprocessing
        self.assertEqual(config.parallelism, multiprocessing.cpu_count())
        self.assertEqual(config.versions, 1)
        self.assertFalse(config.delete_before)
        self.assertEqual(config.mysqldump_bin, "mysqldump")
        self.assertEqual(config.mysql_bin, "mysql")
        self.assertEqual(config.mysqldump_options, [])
        self.assertEqual(config.log_level, "info")

    def test_file_not_found(self):
        """Test behavior when config file doesn't exist."""
        with self.assertRaises(FileNotFoundError):
            get_config(os.path.join(self.test_dir, "nonexistent.toml"))

    def test_missing_main_section(self):
        """Test behavior when 'main' section is missing."""
        with self.assertRaises(ValueError) as context:
            get_config(self.invalid_config_path)
        self.assertIn("Missing 'main' section", str(context.exception))

    def test_missing_required_field(self):
        """Test behavior when required field is missing."""
        with self.assertRaises(ValueError) as context:
            get_config(self.missing_required_path)
        self.assertIn("Required setting 'backup_dir' is missing", str(context.exception))

    def test_invalid_backup_dir(self):
        """Test behavior when backup_dir doesn't exist."""
        with self.assertRaises(ValueError) as context:
            get_config(self.invalid_dir_path)
        self.assertIn("Backup directory does not exist", str(context.exception))

    def test_invalid_toml_syntax(self):
        """Test behavior with invalid TOML syntax."""
        # Create a file with invalid TOML syntax
        invalid_syntax_path = os.path.join(self.test_dir, "invalid_syntax.toml")
        with open(invalid_syntax_path, "w") as f:
            f.write("This is not valid TOML syntax")

        with self.assertRaises(ValueError) as context:
            get_config(invalid_syntax_path)
        self.assertIn("Error parsing TOML file", str(context.exception))

    def test_mutually_exclusive_values(self):
        """Test behavior with mutually exclusive values."""
        # Create a file with invalid TOML syntax
        invalid_syntax_path = os.path.join(self.test_dir, "mutually_exclusive.toml")
        with open(invalid_syntax_path, "w") as f:
            f.write(
                "[main]\n"
                "backup_dir = \"/tmp\"\n"
                "delete_before = true\n"
                "skip_unchanged_dbs = true\n")

        with self.assertRaises(ValueError) as context:
            get_config(invalid_syntax_path)
        self.assertIn(
            "Mutually exclusive values: cannot specify 'skip_unchanged_dbs' with 'delete_before' option",
            str(context.exception)
        )

    @patch('multiprocessing.cpu_count')
    def test_cpu_count_fallback(self, mock_cpu_count):
        """Test that parallelism defaults to CPU count."""
        mock_cpu_count.return_value = 8
        config = get_config(self.minimal_config_path)
        self.assertEqual(config.parallelism, 8)
        mock_cpu_count.assert_called_once()

    def test_do_databases_config(self):
        """Test loading configuration with do_databases."""
        do_databases_path = os.path.join(self.test_dir, "do_databases.toml")
        with open(do_databases_path, "w") as f:
            f.write(f"""
[main]
backup_dir = "{self.backup_dir}"
do_databases = ["db1", "db2", "db3"]
""")

        config = get_config(do_databases_path)
        self.assertEqual(config.do_databases, ["db1", "db2", "db3"])
        self.assertEqual(config.exclude_databases, [])

    def test_do_databases_exclude_databases_mutually_exclusive(self):
        """Test that do_databases and exclude_databases are mutually exclusive."""
        mutex_path = os.path.join(self.test_dir, "mutex.toml")
        with open(mutex_path, "w") as f:
            f.write(f"""
[main]
backup_dir = "{self.backup_dir}"
do_databases = ["db1", "db2"]
exclude_databases = ["db3", "db4"]
""")

        with self.assertRaises(ValueError) as context:
            get_config(mutex_path)
        self.assertIn("cannot specify both 'exclude_databases' and 'do_databases'", str(context.exception))


if __name__ == '__main__':
    unittest.main()
