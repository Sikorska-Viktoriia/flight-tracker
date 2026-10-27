#!/usr/bin/env bash
set -euo pipefail

COMPOSE_RUNNER="/opt/flight-tracker/scripts/docker-compose-vagrant.sh"
RUNTIME_STATUS="/opt/flight-tracker/scripts/vagrant-runtime-status.sh"

if [[ -z "${SSH_ORIGINAL_COMMAND:-}" ]]; then
  printf 'Interactive SSH access is disabled for the logger key.\n' >&2
  exit 2
fi


current_hostname="$(hostname -s 2>/dev/null || printf '%s' "${HOSTNAME:-}")"
vm_role="${current_hostname#flight-tracker-}"

case "$vm_role" in
  fetcher|history|ui) ;;
  *)
    printf 'This VM is not configured as a logger client.\n' >&2
    exit 2
    ;;
esac


read -r -a arguments <<<"$SSH_ORIGINAL_COMMAND"
action="${arguments[0]:-}"

if [[ ${#arguments[@]} -eq 2 && "$action" == "status" ]]; then
  target_role="${arguments[1]}"
  if [[ "$target_role" == "$vm_role" ]]; then
    exec bash "$RUNTIME_STATUS"
  fi
elif [[ ${#arguments[@]} -eq 4 && "$action" == "logs" ]]; then
  role="${arguments[1]}"
  service="${arguments[2]}"
  since="${arguments[3]}"

  if [[ ! "$since" =~ ^([0-9]+(s|m|h|d)|[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([+-][0-9]{2}:[0-9]{2}|Z))$ ]]; then
    printf 'Invalid log window format: %s\n' "$since" >&2
    exit 2
  fi

  if [[ "$role" == "$vm_role" ]]; then
    case "$role:$service" in
      fetcher:fetcher|history:history|history:collector|history:migrate|ui:ui)
        exec bash "$COMPOSE_RUNNER" --no-env --profile "$role" logs "$service" \
          --no-color --timestamps --since "$since"
        ;;
    esac
  fi
fi

printf 'Logger command is not allowed.\n' >&2
exit 2