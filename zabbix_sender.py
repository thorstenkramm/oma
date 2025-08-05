import subprocess
from time import sleep

from mysql_dump import BackupResult
from config import ZbxConfig
from logger import OmaLogger


class ZabbixSender:
    def __init__(self, zbx_config: ZbxConfig, logger: OmaLogger):
        self.sender_bin = zbx_config.sender_bin
        self.agent_conf = zbx_config.agent_conf
        self.item_key = zbx_config.item_key
        self.logger = logger
        self.retries = 10

    def set_retires(self, retires: int):
        self.retries = retires

    def send_value(self, item_value: str):
        if not self.item_key:
            return
        cmd = [
            self.sender_bin,
            '-c',
            self.agent_conf,
            '-k',
            self.item_key,
            '-o',
            item_value
        ]
        for i in range(self.retries):
            result = subprocess.run(cmd, capture_output=True, text=True)
            stdout = result.stdout.replace('\r\n', '').replace('\n', '').replace('\r', '')
            stderr = result.stderr.replace('\r\n', '').replace('\n', '').replace('\r', '')
            exit_code = result.returncode
            if exit_code == 0:
                self.logger.info(f"{self.sender_bin}: sent successfully, item_key: {self.item_key}")
                break
            if result.returncode != 0:
                backup_off = (i + 1) * 2
                self.logger.warning(
                    f"{self.sender_bin} failed: {exit_code=}, {stdout=}, {stderr=}, retry in {backup_off} seconds")
                sleep(backup_off)
            self.logger.error(f"{self.sender_bin} failed: giving up after {i} tries.")

    def send_log_file(self, backup_result: BackupResult):
        if not self.item_key:
            return
        # Maximum value size zabbix_sender can send to the zabbix server.
        # https://www.zabbix.com/documentation/current/en/manual/config/items/item#text-data-limits
        max_bytes = 65536
        message = (
            f"\n** Zabbix item values has been truncated because it exceeds {max_bytes} bytes.**\n"
            f"** Refer to {self.logger.log_file} on the monitored host to get the full report.**\n"
        )
        if backup_result.all_skipped_successfully:
            summary = "Summary: Successfully skipped all databases due to skip_conditions. Error=0"
        elif backup_result.all_skipped_faulty:
            summary = "Summary: All databases were skipped due to faulty run_conditions. Error=1"
        else:
            summary = (
                f"Summary: Successfully dumped {backup_result.successful} of {backup_result.total} databases. "
                f"Skipped {backup_result.skipped}, Failed {backup_result.failed}. Error=0"
            )
        # with open(self.logger.log_file, 'r', encoding='utf-8') as f:
        file_content = summary + "\n" + self.logger.read_log()
        if len(file_content) < max_bytes:
            self.send_value(file_content)
            return
        # Subtract the size of the message to leave room to append it later without exceeding the max.
        max_bytes -= len(message)
        # Split log file into lines and append lines until max bytes have been reached.
        log_lines = file_content.splitlines()
        truncated_log_lines = ""
        for line in log_lines:
            if len(truncated_log_lines) + len(line) > max_bytes:
                break
            truncated_log_lines += f" {line}\n"
        truncated_log_lines += message
        self.send_value(truncated_log_lines)
