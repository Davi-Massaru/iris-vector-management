#!/bin/sh
set -eu
iris start IRIS quietly
trap 'iris stop IRIS quietly || true' EXIT
if [ "${VECTOR_ADMIN_SEED:-0}" = "1" ]; then
    mkdir -p /usr/irissys/mgr/vector-fixture-data /usr/irissys/mgr/vector-fixture-index
    iris session IRIS < iris/fixture-mappings.script > /tmp/vector-mappings.log 2>&1
    cat /tmp/vector-mappings.log
    grep -q '^VECTOR_MAPPING_OK' /tmp/vector-mappings.log
fi
iris session IRIS < iris/install.script > /tmp/vector-install.log 2>&1
cat /tmp/vector-install.log
grep -q '^VECTOR_INSTALL_OK' /tmp/vector-install.log
