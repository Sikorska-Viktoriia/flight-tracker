#!/usr/bin/env bash
set -euo pipefail
umask 027

KEY_FILE="/var/lib/flight-tracker-logger/id_ed25519"
KNOWN_HOSTS="/var/lib/flight-tracker-logger/known_hosts"
METRICS_LOG_FILE="/var/log/flight-tracker/metrics.log"
CONTAINER_LOG_DIR="/var/log/flight-tracker/containers"
CURSOR_DIR="/var/lib/flight-tracker-logger/cursors"
RUNTIME_STATUS="/opt/flight-tracker/scripts/vagrant-runtime-status.sh"
COMPOSE_RUNNER="/opt/flight-tracker/scripts/docker-compose-vagrant.sh"
INITIAL_LOG_WINDOW="${FLIGHT_TRACKER_LOG_INITIAL_WINDOW:-16m}"


SSH_OPTS=(
  -i "$KEY_FILE"
  -o BatchMode=yes
  -o ConnectTimeout=5
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=accept-new
  -o UserKnownHostsFile="$KNOWN_HOSTS"
  -o LogLevel=ERROR
)

collect_service_logs() {
  local vm="$1"
  local address="$2"
  local profile="$3"
  local service="$4"
  local log_file="$CONTAINER_LOG_DIR/$vm/$service.log"
  local cursor_file="$CURSOR_DIR/$vm-$service"
  local since="$INITIAL_LOG_WINDOW"
  local collected_at

  mkdir -p "$(dirname "$log_file")" "$CURSOR_DIR"
  if [[ -s "$cursor_file" ]]; then
    IFS= read -r since < "$cursor_file"
  fi

  if [[ ! "$since" =~ ^([0-9]+(s|m|h|d)|[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([+-][0-9]{2}:[0-9]{2}|Z))$ ]]; then
    printf 'Invalid log cursor for %s/%s: %s\n' "$vm" "$service" "$since" >>"$log_file"
    return 1
  fi

  collected_at="$(date --iso-8601=seconds)"
  printf '\n--- collection started=%s vm=%s service=%s since=%s ---\n' \
    "$collected_at" "$vm" "$service" "$since" >>"$log_file"


  if [[ "$vm" == "database" ]]; then
    if ! bash "$COMPOSE_RUNNER" --no-env --profile "$profile" logs "$service" \
      --no-color --timestamps --since "$since" >>"$log_file" 2>&1
    then
      printf 'ERROR: log collection failed at %s.\n' "$(date --iso-8601=seconds)" >>"$log_file"
      return 1
    fi
  else
    if ! ssh "${SSH_OPTS[@]}" "vagrant@$address" "logs $profile $service $since" >>"$log_file" 2>&1; then
      printf 'ERROR: log collection failed at %s.\n' "$(date --iso-8601=seconds)" >>"$log_file"
      return 1
    fi
  fi


  local next_cursor
  next_cursor="$(date --utc --iso-8601=seconds)"
  printf '%s\n' "$next_cursor" > "$cursor_file.tmp"
  chmod 600 "$cursor_file.tmp"
  mv -f "$cursor_file.tmp" "$cursor_file"
}

targets=(
  "database 10.20.0.10 database db rabbitmq redis"
  "fetcher 10.20.0.11 fetcher fetcher"
  "history 10.20.0.12 history history collector migrate"
  "ui 10.20.0.13 ui ui"
)
failed=0


mkdir -p "$(dirname "$METRICS_LOG_FILE")"

for target in "${targets[@]}"; do
  read -r name address profile services <<<"$target"
  read -r -a service_names <<<"$services"
  timestamp="$(date --iso-8601=seconds)"

  printf '\n[%s] vm=%s type=metrics\n' "$timestamp" "$name" | tee -a "$METRICS_LOG_FILE"

  if [[ "$name" == "database" ]]; then
    if ! bash "$RUNTIME_STATUS" 2>&1 | tee -a "$METRICS_LOG_FILE"; then
      printf 'ERROR: local status collection failed for %s.\n' "$name" | tee -a "$METRICS_LOG_FILE" >&2
      failed=1
    fi
  else
    if ! ssh "${SSH_OPTS[@]}" "vagrant@$address" "status $name" 2>&1 | tee -a "$METRICS_LOG_FILE"; then
      printf 'ERROR: could not collect status from %s (%s).\n' "$name" "$address" | tee -a "$METRICS_LOG_FILE" >&2
      failed=1
    fi
  fi

  for service in "${service_names[@]}"; do
    if ! collect_service_logs "$name" "$address" "$profile" "$service"; then
      printf 'ERROR: could not collect %s logs from %s (%s).\n' "$service" "$name" "$address" \
        | tee -a "$METRICS_LOG_FILE" >&2
      failed=1
    fi
  done
done

exit "$failed"