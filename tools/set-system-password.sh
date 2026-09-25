#!/bin/sh
set -eu
password_file="$1"
VECTOR_ADMIN_SYSTEM_PASSWORD="$(cat "$password_file")"
export VECTOR_ADMIN_SYSTEM_PASSWORD
iris session IRIS -U %SYS < /usr/irissys/csp/vector-admin/iris/set-password.script > /tmp/vector-password.log 2>&1
grep -q '^VECTOR_PASSWORD_OK' /tmp/vector-password.log
unset VECTOR_ADMIN_SYSTEM_PASSWORD
