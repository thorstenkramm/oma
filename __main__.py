#!/usr/bin/env python3
import argparse
import os
import socket
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


def acquire_execution_lock(port):
    """
    Acquire an exclusive execution lock by binding to a local port.
    Returns the socket if successful, None if port is already in use.
    """
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lock_socket.bind(('127.0.0.1', port))
        lock_socket.listen(1)  # Put socket in listening state so port shows as open
        return lock_socket
    except OSError:
        return None


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

    # Try to acquire execution lock to prevent parallel runs
    lock_socket = acquire_execution_lock(config.lock_port)
    if lock_socket is None:
        sys.stderr.write("Another instance of OMA is already running (port %d is in use)\n" % config.lock_port)
        sys.exit(3)

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
    if config.delete_before:
        logger.debug(f"Removing old backup directories before new backup. Will keep {config.versions} versions ...")
        removed = store_manager.cleanup_before(config.versions)
        logger.info(f"Removed old backup directories: {removed}")

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
        logger.debug(f"Removing old backup directories after current backup. Will keep {config.versions} versions ...")
        removed = store_manager.cleanup_after(config.versions)
        logger.info(f"Removed old backup directories: {removed}")

    # Execute terminate conditions
    if not conditions_manager.execute_terminate_conditions(store_manager.current_dir.path):
        logger.error("One or more terminate conditions failed")
        # Note: We don't exit with error here as the backup itself was successful

    # Send log to zabbix, if desired
    zabbix_sender.send_log_file(backup_result)

    # Close the lock socket to release the port
    lock_socket.close()


if __name__ == "__main__":
    main()
