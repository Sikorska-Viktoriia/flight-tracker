#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "postgres" ]]; then
  postgres_args=("$@" -c "config_file=/etc/postgresql/postgresql.conf")
  if [[ "${STORAGE_BACKEND:-standalone}" == "postgres_extensions" ]]; then
    postgres_args+=(
      -c "shared_preload_libraries=pg_cron"
      -c "cron.database_name=${POSTGRES_DB:-flightdb}"
    )
  fi
  exec /usr/local/bin/docker-entrypoint.sh "${postgres_args[@]}"
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
