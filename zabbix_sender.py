import subprocess

from mysql_dump import BackupResult


class ZabbixSender:
    def __init__(self,
                 backup_result: BackupResult,
                 sender_bin: str = "zabbix_sender",
                 agent_conf: str = "/etc/zabbix/zabbix_agent.conf"):
        self.sender_bin = sender_bin
        self.agent_conf = agent_conf
        self.backup_result = backup_result

    def send_value(self, item_key: str, item_value: str):
        cmd = [
            self.sender_bin,
            '-c',
            self.agent_conf,
            '-k',
            item_key,
            '-o',
            item_value
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                returncode=result.returncode,
                cmd=cmd,
                output=result.stdout,
                stderr=result.stderr
            )

    def send_file(self, item_key: str, file_path: str):
        # Maximum value size zabbix_sender can send to the zabbix server.
        # https://www.zabbix.com/documentation/current/en/manual/config/items/item#text-data-limits
        max_bytes = 65536
        message = (
            f"\n** Zabbix item values has been truncated because it exceeds {max_bytes} bytes.**\n"
            f"** Refer to {file_path} on the monitored host to get the full report.**\n"
        )
        summary = (
            f"Summary: Successfully dumped {self.backup_result.successful} of {self.backup_result.total} databases. "
            f"Skipped {self.backup_result.skipped}, Failed {self.backup_result.failed}."
        )
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = summary + "\n" + str(f.read())
        if len(file_content) < max_bytes:
            self.send_value(item_key, file_content)
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
        self.send_value(item_key, truncated_log_lines)
