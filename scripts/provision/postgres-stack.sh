#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/flight-tracker"
SCRIPT_DIR="$PROJECT_DIR/scripts"
COMPOSE_RUNNER="$SCRIPT_DIR/docker-compose-vagrant.sh"
DATA_DIR="/var/lib/flight-tracker"
POSTGRES_DUMP="$DATA_DIR/postgres.dump"
POSTGRES_RESTORED="$DATA_DIR/postgres-docker-restored"
POSTGRES_DB="${POSTGRES_DB:-flightdb}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
STORAGE_BACKEND="${STORAGE_BACKEND:-standalone}"

source "$SCRIPT_DIR/provision/common.sh"
disable_services postgresql rabbitmq-server redis-server

install -d -m 700 "$DATA_DIR"
if [[ ! -e "$POSTGRES_RESTORED" ]]; then
  if systemctl is-active --quiet postgresql; then
    dump_tmp="$(mktemp "$DATA_DIR/postgres.dump.XXXXXX")"
    if ! runuser -u postgres -- pg_dump --format=custom --dbname="$POSTGRES_DB" > "$dump_tmp"; then
      rm -f "$dump_tmp"
      printf 'Could not back up the existing PostgreSQL database %s.\n' "$POSTGRES_DB" >&2
      exit 1
    fi
    chmod 600 "$dump_tmp"
    mv -f "$dump_tmp" "$POSTGRES_DUMP"
  elif [[ -d /etc/postgresql && ! -s "$POSTGRES_DUMP" ]]; then
    printf 'PostgreSQL is installed but stopped and no migration dump exists; start it and retry.\n' >&2
    exit 1
  fi
fi

bash "$COMPOSE_RUNNER" --profile database up --detach --wait db
if [[ -s "$POSTGRES_DUMP" && ! -e "$POSTGRES_RESTORED" ]]; then
  if ! bash "$COMPOSE_RUNNER" --profile database exec -T db pg_restore \
    --clean --if-exists --create --no-acl --exit-on-error \
    --username "$POSTGRES_USER" \
    --dbname postgres < "$POSTGRES_DUMP"; then
    printf 'PostgreSQL migration failed; the original dump is preserved at %s.\n' "$POSTGRES_DUMP" >&2
    exit 1
  fi
  touch "$POSTGRES_RESTORED"
fi

if [[ "$STORAGE_BACKEND" == postgres_extensions ]]; then
  bash "$COMPOSE_RUNNER" --profile database exec -T db \
    psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --file /opt/flight-tracker/database/extensions/001-install.sql
fi
if [[ "$STORAGE_BACKEND" != standalone ]]; then
  bash "$COMPOSE_RUNNER" --profile history run --rm migrate
fi

if [[ "$STORAGE_BACKEND" == standalone ]]; then
  bash "$COMPOSE_RUNNER" --profile rabbitmq up --detach --wait rabbitmq
  bash "$COMPOSE_RUNNER" --profile redis up --detach --wait redis
else
  bash "$COMPOSE_RUNNER" --profile rabbitmq rm --stop --force rabbitmq
  bash "$COMPOSE_RUNNER" --profile redis rm --stop --force redis
fi
