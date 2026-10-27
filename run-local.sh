#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
PORT_OVERRIDE="${PORT-}"
FETCHER_PORT_OVERRIDE="${FETCHER_PORT-}"

if [[ -f "$PROJECT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/.env"
  set +a
fi

[[ -z "$PORT_OVERRIDE" ]] || PORT="$PORT_OVERRIDE"
[[ -z "$FETCHER_PORT_OVERRIDE" ]] || FETCHER_PORT="$FETCHER_PORT_OVERRIDE"
export PORT="${PORT:-8000}"
export FETCHER_PORT="${FETCHER_PORT:-8081}"

case "${1:-}" in
  fetcher)
    cd "$PROJECT_DIR/fetcher"
    exec go run .
    ;;
  history)
    exec "$PROJECT_DIR/history/.venv/bin/uvicorn" \
      history.app.main:app --host 0.0.0.0 --port "$PORT"
    ;;
  collector)
    exec "$PROJECT_DIR/history/.venv/bin/python" -m history.app.worker
    ;;
  migrate)
    exec "$PROJECT_DIR/history/.venv/bin/python" -m history.app.db.migrate
    ;;
  *)
    printf 'Usage: %s {fetcher|history|collector|migrate}\n' "$0" >&2
    exit 2
    ;;
esac
