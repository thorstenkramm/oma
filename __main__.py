#!/usr/bin/env python3
import argparse
import os
import sys

from mysql_dump import MySQLDump, BackupResult, NotEnoughDiskSpaceError
from config import get_config
from logger import new_logger
from store_manager import StoreManager
from zabbix_sender import ZabbixSender
from version import get_version
from conditions_manager import ConditionsManager


def parse_arguments():
    """
    Parse command line arguments
    :return: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Optimized MySQLDump Archiver - A smart wrapper around mysqldump')
    parser.add_argument('-c', '--config',
                        default='/etc/oma/oma.conf',
                        help='Path to the configuration file (default: /etc/oma/oma.conf)')
    parser.add_argument('-d', '--debug',
                        action='store_true',
                        help='Set log level to debug and override log level from config file')
    parser.add_argument('-v', '--version',
                        action='store_true',
                        help='Print version information and exit')

    return parser.parse_args()


def main():
    # Parse command line options
    args = parse_arguments()

    # Print version and exit
    if args.version:
        print(get_version())
        sys.exit(0)

    # Read configuration file
    try:
        config = get_config(args.config)
    except ValueError as e:
        sys.stderr.write("Invalid configuration: %s\n" % e)
        sys.exit(1)

    # Initialize logger with appropriate log level
    log_level = "debug" if args.debug else config.log_level

    # Initialize the store manage that handles all backup directories
    store_manager = StoreManager(config.backup_dir)

    # Initialize the logger
    log_file = os.path.join(store_manager.current_dir.path, "oma.log")
    logger = new_logger(log_file, log_level)
    logger.debug(f"Using configuration file: {args.config}")
    if args.debug:
        logger.debug("Debug mode enabled via command line argument")

    # Initialize a backup result
    backup_result = BackupResult(0, 0, 0, 0)

    # Initialize zabbix sender
    zabbix_sender = ZabbixSender(config.zbx, logger)

    # Initialize conditions manager
    conditions_manager = ConditionsManager(config.conditions, logger)

    # Check skip conditions
    if conditions_manager.check_skip_conditions():
        logger.info("Backup skipped due to skip conditions (but considered successful)")
        backup_result.all_skipped_successfully = True
        zabbix_sender.send_log_file(backup_result)
        store_manager.remove_skipped()
        sys.exit(0)

    # Check run conditions
    if not conditions_manager.check_run_conditions():
        logger.error("Backup aborted due to failed run conditions")
        backup_result.all_skipped_faulty = True
        zabbix_sender.send_log_file(backup_result)
        store_manager.remove_skipped()
        sys.exit(1)

    # Clean up before doing the backup, if desired
    store_manager.cleanup_before(config.versions) if config.delete_before else None
    # Do the backup
    logger.info("Performing the backup now ...")
    try:
        mysql_dump = MySQLDump(config, store_manager, logger)
        backup_result = mysql_dump.execute()
    except NotEnoughDiskSpaceError as e:
        logger.error(e)
        backup_result.all_skipped_faulty = True
        zabbix_sender.send_log_file(backup_result)
        store_manager.remove_skipped()
        sys.exit(2)
    except Exception as e:
        logger.error(e)

    # Clean up after doing the backup, if desired
    if not config.delete_before:
        removed = store_manager.cleanup_after(config.versions)
        logger.info(f"Removed old backup directories: {removed}")

    # Execute terminate conditions
    if not conditions_manager.execute_terminate_conditions(store_manager.current_dir.path):
        logger.error("One or more terminate conditions failed")
        # Note: We don't exit with error here as the backup itself was successful

    # Send log to zabbix, if desired
    zabbix_sender.send_log_file(backup_result)


if __name__ == "__main__":
    main()
