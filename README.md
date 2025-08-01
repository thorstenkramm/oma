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

## Installation

On Debian 11 and Ubuntu 20.04 install required python modules:

```bash
apt install python3-toml
```

Debian 12 and Ubuntu 24.04. come with a python 3.11+ which has toml support built-in.

Install:

```bash
cd /tmp
wget https://github.com/thorstenkramm/oma/releases/download/0.0.2/oma-0.0.2.tar.gz
tar xf oma-0.0.2.tar.gz
sudo mv oma.pyz /usr/local/bin/oma
sudo chmod +x /usr/local/bin/oma
sudo mkdir /etc/oma
sudo mv oma.conf.example /etc/oma/oma.conf
rm oma-0.0.2.tar.gz
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
