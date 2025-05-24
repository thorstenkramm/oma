#!/usr/bin/env python3
import argparse
import os
import sys

from mysql_dump import MySQLDump, BackupResult
from config import get_config
from logger import new_logger
from store_manager import StoreManager
from zabbix_sender import ZabbixSender
from version import get_version


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

    # Clean up before doing the backup, if desired
    store_manager.cleanup_before(config.versions) if config.delete_before else None
    # Do the backup
    logger.info("Performing the backup now ...")
    try:
        mysql_dump = MySQLDump(config, store_manager, logger)
        backup_result = mysql_dump.execute()
    except Exception as e:
        logger.error(e)
        backup_result = BackupResult(0, 0, 0, 0)

    # Clean up after doing the backup, if desired
    if not config.delete_before:
        removed = store_manager.cleanup_after(config.versions)
        logger.info(f"Removed old backup directories: {removed}")

    # Send log to zabbix, if desired
    if config.zbx.item_key != "":
        zs = ZabbixSender(backup_result, config.zbx.sender_bin, config.zbx.agent_conf)
        try:
            zs.send_file(config.zbx.item_key, log_file)
            logger.debug(f"Logfile sent successfully via zabbix_sender. Item key: {config.zbx.item_key}")
        except Exception as e:
            logger.error(f"zabbix_sender: {e}")


if __name__ == "__main__":
    main()
