#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s <database|fetcher|history|ui> [service] [--follow]\n' "$0" >&2
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

role="$1"
shift
case "$role" in
  database) allowed_services=(db rabbitmq redis) ;;
  fetcher)  allowed_services=(fetcher) ;;
  history)  allowed_services=(history collector migrate) ;;
  ui)       allowed_services=(ui) ;;
  *) usage; exit 2 ;;
esac

follow=false
requested_services=()
for argument in "$@"; do
  if [[ "$argument" == "--follow" ]]; then
    follow=true
  else
    requested_services+=("$argument")
  fi
done

if [[ ${#requested_services[@]} -gt 1 ]]; then
  usage
  exit 2
fi

services=("${allowed_services[@]}")
if [[ ${#requested_services[@]} -eq 1 ]]; then
  service="${requested_services[0]}"
  service_found=false
  for item in "${allowed_services[@]}"; do
    if [[ "$item" == "$service" ]]; then
      service_found=true
      break
    fi
  done

  if [[ "$service_found" != true ]]; then
    printf 'Service %q does not belong to the %s VM.\n' "$service" "$role" >&2
    exit 2
  fi
  services=("$service")
fi

state="$(vagrant status "$role" --machine-readable | awk -F, '$3 == "state" { print $4; exit }')"
if [[ "$state" != "running" ]]; then
  printf 'The %s VM is not running (state: %s).\n' "$role" "${state:-unknown}" >&2
  exit 1
fi

follow_option=""
if [[ "$follow" == true ]]; then
  follow_option="--follow"
fi
service_arguments="${services[*]}"
vagrant ssh "$role" -c \
  "sudo /opt/flight-tracker/scripts/docker-compose-vagrant.sh --profile $role logs --timestamps --tail=100 $follow_option $service_arguments"