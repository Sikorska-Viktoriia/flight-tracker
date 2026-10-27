#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:?Application VM role is required}"
PROJECT_DIR="/opt/flight-tracker"
SCRIPT_DIR="$PROJECT_DIR/scripts"
COMPOSE_RUNNER="$SCRIPT_DIR/docker-compose-vagrant.sh"
source "$SCRIPT_DIR/provision/common.sh"

case "$ROLE" in
  fetcher)
    disable_services flight-tracker-fetcher.service nginx.service
    ;;
  history)
    disable_services \
      flight-tracker-migrate.service \
      flight-tracker-history.service \
      flight-tracker-collector.service
    ;;
  ui)
    disable_services nginx.service
    ;;
  *)
    printf 'Unknown application VM role: %s\n' "$ROLE" >&2
    exit 2
    ;;
esac

bash "$COMPOSE_RUNNER" --profile "$ROLE" up --detach --build
