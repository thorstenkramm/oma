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
- Option to run additional command before and after the backup
- Distributed as a single-file Python zipap

Refer to the [example of the configuration file](./oma.conf.example):

## Installation

On Debian 11 and Ubuntu 20.04 install required python modules:

```bash
apt install python3-toml
```

Debian 12 and Ubuntu 24.04. come with a python 3.11+ which has toml support built-in.

Install:

```bash
cd /tmp
wget https://github.com/thorstenkramm/oma/releases/download/0.0.3/oma-0.0.3.tar.gz
tar xf oma-0.0.3.tar.gz
sudo mv oma.pyz /usr/local/bin/oma
sudo chmod +x /usr/local/bin/oma
sudo mkdir /etc/oma
sudo mv oma.conf.example /etc/oma/oma.conf
rm oma-0.0.3.tar.gz
```

## Run the backup

Edit `/etc/oma/oma.conf` to your needs. Then run `oma` from cron.

> [!IMPORTANT]
> You must run `oma` from a user account – such as root – that has read access to the mysql data directory.

To determine which databases haven't change since the last backup `oma` checks the modification timestamps of
the mysql table files in the filesystem.

Adding a user to the `mysql` user group is usually not sufficient because the mysql data directory hase mode 0700.

### Authentication

Oma uses the mysql client and mysqldump executable installed to your system. These command line utilities will read
all mysql configuration files as configured for your database installation. If you need authentication to backup your
database you can for example create a file `~/.my.cnf` and put the password for accessing the database there.  
Alternatively you can setup passwordless access via the authentication socket. The latter is since MySQL 8.X the default
on most installations.

## Conditions

Conditions are command that are executed before and after the backup. You can hook in your commands at three different
phases of the backup process.

- `skip_conditions`, with this list of commands you can intentionally skip a backup but it's logged as successfully.
  This is useful to dynamically react on role changes in a cluster. 
- `run_conditions`, with this list of commands you can asure all conditions are met to run the backup. If a run
  condition is not met, an error is logged and the backup is aborted and considered faulty. This is useful to mount
  or verify storage devices. 
- `terminate_conditions`, this list of commands is run after the mysqldump backup and all storage cleanup routines
  have terminated. If command from the terminate conditions fail (exit code >0), an error is logged and the backup
  is considered faulty. This is useful to copy the backup to remote locations.

Refer to the [example of the configuration file](./oma.conf.example) for more details and all options.

When running OMA in debug logging mode, stdout of the condition command is written to the OMA log.
In info logging mode, only the exit code of commands is logged. Errors (stderr) are always logged. 