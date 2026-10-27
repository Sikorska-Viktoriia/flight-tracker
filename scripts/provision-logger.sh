#!/usr/bin/env bash
set -euo pipefail

apt-get update
apt-get install -y openssh-client logrotate
python3 /opt/flight-tracker/logger/provision_logger.py

install -m 644 -o root -g root \
  /opt/flight-tracker/configs/systemd/flight-tracker-logger.service \
  /etc/systemd/system/flight-tracker-logger.service
install -m 644 -o root -g root \
  /opt/flight-tracker/configs/systemd/flight-tracker-logger.timer \
  /etc/systemd/system/flight-tracker-logger.timer
install -m 644 -o root -g root \
  /opt/flight-tracker/configs/systemd/flight-tracker-logger.logrotate \
  /etc/logrotate.d/flight-tracker-logger

systemctl daemon-reload
systemctl enable --now flight-tracker-logger.timer
echo "[INFO] Logger key ready; collection is scheduled every fifteen minutes."
