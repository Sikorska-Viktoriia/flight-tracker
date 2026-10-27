#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"

if [[ ! -r "$ENV_FILE" ]]; then
  printf 'Missing %s. Copy .env.example to .env and configure it.\n' "$ENV_FILE" >&2
  exit 1
fi

read_env_value() {
  awk -F= -v key="$1" '
    $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
    }
    END { print value }
  ' "$ENV_FILE"
}

STORAGE_BACKEND="${STORAGE_BACKEND:-$(read_env_value STORAGE_BACKEND)}"
STORAGE_BACKEND="${STORAGE_BACKEND:-standalone}"
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-$(read_env_value RABBITMQ_PASSWORD)}"
REDIS_PASSWORD="${REDIS_PASSWORD:-$(read_env_value REDIS_PASSWORD)}"
DATABASE_URL="${DATABASE_URL:-$(read_env_value DATABASE_URL)}"

profiles=()
case "$STORAGE_BACKEND" in
  standalone)
    [[ -n "$RABBITMQ_PASSWORD" ]] || {
      printf 'RABBITMQ_PASSWORD is required when STORAGE_BACKEND=standalone.\n' >&2
      exit 1
    }
    [[ -n "$REDIS_PASSWORD" ]] || {
      printf 'REDIS_PASSWORD is required when STORAGE_BACKEND=standalone.\n' >&2
      exit 1
    }
    profiles=(rabbitmq redis)
    ;;
  postgres_native|postgres_extensions)
    [[ -n "$DATABASE_URL" ]] || {
      printf 'DATABASE_URL is required for PostgreSQL storage backends.\n' >&2
      exit 1
    }
    ;;
  *)
    printf 'STORAGE_BACKEND must be standalone, postgres_native, or postgres_extensions.\n' >&2
    exit 2
    ;;
esac

if ((${#profiles[@]})); then
  COMPOSE_PROFILES="$(IFS=,; printf '%s' "${profiles[*]}")"
else
  COMPOSE_PROFILES=
fi
export COMPOSE_PROFILES

compose=(docker compose --project-directory "$PROJECT_DIR" --env-file "$ENV_FILE")
if [[ "${1:-}" == up && "$STORAGE_BACKEND" == postgres_extensions ]]; then
  "${compose[@]}" up --no-build --detach --wait db
  POSTGRES_USER="$(read_env_value POSTGRES_USER)"
  POSTGRES_DB="$(read_env_value POSTGRES_DB)"
  "${compose[@]}" exec -T db psql \
    --username "${POSTGRES_USER:-postgres}" \
    --dbname "${POSTGRES_DB:-flightdb}" \
    --file /opt/flight-tracker/database/extensions/001-install.sql
fi

if [[ "${1:-}" == up ]]; then
  exec "${compose[@]}" up --no-build "${@:2}"
fi
exec "${compose[@]}" "$@"
