#!/bin/bash
set -e

"/opt/hbase-${HBASE_VERSION}/bin/start-hbase.sh"
"/opt/hbase-${HBASE_VERSION}/bin/hbase-daemon.sh" start rest -p 8080 --infoport 8085

exec tail -F "/opt/hbase-${HBASE_VERSION}/logs/"*.log
