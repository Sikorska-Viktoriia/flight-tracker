#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:?VM role is required}"
PROJECT_DIR="/opt/flight-tracker"
SCRIPT_DIR="$PROJECT_DIR/scripts"
ENV_FILE="$PROJECT_DIR/.env"
UI_ENV_FILE="$PROJECT_DIR/configs/vagrant/ui.env"

if [[ "$ROLE" == bastion ]]; then
  apt-get update
  apt-get install -y openssh-server
  install -m 644 \
    "$PROJECT_DIR/configs/ssh/flight-tracker-jump.conf" \
    /etc/ssh/sshd_config.d/flight-tracker-jump.conf
  python3 "$PROJECT_DIR/provision/bastion/configure_ssh.py"
  sshd -t
  systemctl enable --now ssh
  echo "[INFO] Bastion SSH is enabled with forwarding restricted to the application VMs."
  exit 0
fi

case "$ROLE" in
  database|fetcher|history|ui) ;;
  *)
    printf 'Unknown VM role: %s\n' "$ROLE" >&2
    exit 2
    ;;
esac

apt-get update
apt-get install -y docker.io docker-compose-v2
systemctl enable --now docker
usermod -aG docker vagrant
python3 "$SCRIPT_DIR/provision/install_host_key.py"

UPLOADED_ENV_FILE="/tmp/flight-tracker.env"
if [[ -f "$UPLOADED_ENV_FILE" ]]; then
  install -m 600 "$UPLOADED_ENV_FILE" "$ENV_FILE"
  rm -f "$UPLOADED_ENV_FILE"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ "$ROLE" != ui ]]; then
    printf 'Required environment file not found: %s\n' "$ENV_FILE" >&2
    exit 1
  fi
  install -m 600 "$UI_ENV_FILE" "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
STORAGE_BACKEND="${STORAGE_BACKEND:-standalone}"

case "$STORAGE_BACKEND" in
  standalone|postgres_native|postgres_extensions) ;;
  *)
    printf 'STORAGE_BACKEND must be standalone, postgres_native, or postgres_extensions.\n' >&2
    exit 2
    ;;
esac

case "$ROLE" in
  database)
    : "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in .env}"
    : "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set in .env}"
    if [[ "$STORAGE_BACKEND" == standalone ]]; then
      : "${RABBITMQ_PASSWORD:?RABBITMQ_PASSWORD must be set in .env}"
      : "${REDIS_PASSWORD:?REDIS_PASSWORD must be set in .env}"
    else
      : "${DATABASE_URL:?DATABASE_URL must be set for PostgreSQL backends}"
    fi
    bash "$SCRIPT_DIR/provision/postgres-stack.sh"
    ;;
  fetcher)
    if [[ "$STORAGE_BACKEND" == standalone ]]; then
      : "${RABBITMQ_PASSWORD:?RABBITMQ_PASSWORD must be set in .env}"
    else
      : "${DATABASE_URL:?DATABASE_URL must be set for PostgreSQL backends}"
    fi
    bash "$SCRIPT_DIR/provision/application-stack.sh" "$ROLE"
    ;;
  history)
    : "${DATABASE_URL:?DATABASE_URL must be set in .env}"
    if [[ "$STORAGE_BACKEND" == standalone ]]; then
      : "${RABBITMQ_PASSWORD:?RABBITMQ_PASSWORD must be set in .env}"
      : "${REDIS_PASSWORD:?REDIS_PASSWORD must be set in .env}"
    fi
    bash "$SCRIPT_DIR/provision/application-stack.sh" "$ROLE"
    ;;
  ui)
    bash "$SCRIPT_DIR/provision/application-stack.sh" "$ROLE"
    ;;
esac

echo "[INFO] Provisioned the $ROLE Compose stack with STORAGE_BACKEND=$STORAGE_BACKEND."
bash "$SCRIPT_DIR/docker-compose-vagrant.sh" --profile "$ROLE" ps
