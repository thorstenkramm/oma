#!/usr/bin/env bash

echo "📦 Setting up MySQL Database ... "
set -e

if systemctl status mysql;then
  echo "🚚 Stopping mysqld ... "
  systemctl stop mysql
fi

rm -rf /var/lib/mysql/*
test -e /var/log/mysql/error.log && rm /var/log/mysql/error.log
echo "🚚 Recreating mysql data dir ... "
mysqld --initialize --user=mysql --datadir=/var/lib/mysql

echo "🚚 Staring mysqld ... "
systemctl start mysql

echo "🚚 Setting new mysql root password ..."
PASSWORD=$(grep 'temporary password' /var/log/mysql/error.log|grep -o "root@localhost.*"|cut -d' ' -f2)
mysql -p"$PASSWORD" --connect-expired-password -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '12345'"

echo "🚚 Storing mysql root password ..."
cat << EOF > /root/.my.cnf
[client]
password = 12345
EOF
mysql -e "SHOW DATABASES"