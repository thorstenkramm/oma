## OMA
**O**ptimized **M**ysqldump **A**rchiver

Many wrappers around `mysqldump` have been written. `OMA` is what fits best the requirements of 
[dimedis GmbH](https://www.linkedin.com/company/dimedis).

Key features at a glance:

- Controlled by toml configuration file
- Built-in Zabbix reporting
- Per database backup files
- Deletion of old backups
- Option to skip backup of databases without changes
- Comprehensive logging
- Option to run multiple mysqldump processes in parallel
- No pip required. All required packages included in Debian & Ubuntu
- Supervision of the mysqldump process and control of final success message
- Distributed as a single-file Python zipap

Refer to the [example of the configuration file](./oma.conf.example):

### Installation

On Debian 11 install required python modules:

```bash
apt install python3-toml
```