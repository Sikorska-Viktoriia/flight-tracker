#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="$PROJECT_DIR/compose/vagrant"
ENV_FILE="$PROJECT_DIR/.env"
no_env=false

if [[ "${1:-}" == --no-env ]]; then
  no_env=true
  shift
fi

compose=(
  docker compose
  --project-name flight-tracker
  --project-directory "$PROJECT_DIR"
)

if [[ "$no_env" == true ]]; then
  compose+=(--env-file /dev/null)
elif [[ -r "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
  compose+=(--env-file "$ENV_FILE")
elif [[ -e "$ENV_FILE" ]]; then
  printf 'Cannot read Compose environment file: %s\n' "$ENV_FILE" >&2
  exit 1
fi

for service_file in \
  db.yml \
  rabbitmq.yml \
  redis.yml \
  fetcher.yml \
  migrate.yml \
  history.yml \
  collector.yml \
  ui.yml
do
  compose+=(--file "$COMPOSE_DIR/services/$service_file")
done
compose+=(--file "$COMPOSE_DIR/volumes.yml")

exec "${compose[@]}" "$@"
