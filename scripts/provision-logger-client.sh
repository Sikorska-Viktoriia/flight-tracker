#!/usr/bin/env bash
set -euo pipefail

install -m 755 -o root -g root \
  /opt/flight-tracker/logger/remote-logger-command.sh \
  /usr/local/sbin/flight-tracker-logger-remote
python3 /opt/flight-tracker/logger/provision_logger_client.py
echo "[INFO] Logger SSH key installed with restricted status and log collection access."
