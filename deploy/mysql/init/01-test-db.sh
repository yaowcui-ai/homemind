#!/bin/sh
set -eu

# Run only during initialization of this new project's empty volume.
# setup_mysql.py generates URL-safe passwords, excluding SQL metacharacters.
case "$HOMEMIND_MYSQL_TEST_PASSWORD" in
  *[!a-zA-Z0-9_-]*|'') echo 'Invalid local test credential format' >&2; exit 1 ;;
esac
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=socket --user=root <<EOSQL
CREATE DATABASE homemind_test CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER 'homemind_test'@'%' IDENTIFIED BY '${HOMEMIND_MYSQL_TEST_PASSWORD}';
GRANT ALL PRIVILEGES ON homemind_test.* TO 'homemind_test'@'%';
EOSQL
