#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
current_hostname="$(hostname -s 2>/dev/null || printf '%s' "${HOSTNAME:-}")"
vm_role="${current_hostname#flight-tracker-}"

case "$vm_role" in
  database|fetcher|history|ui) ;;
  *)
    printf 'Cannot determine Flight Tracker VM role from hostname: %s\n' "$current_hostname" >&2
    exit 1
    ;;
esac

printf '\n--- Compose service state ---\n'
"$SCRIPT_DIR/docker-compose-vagrant.sh" --no-env --profile "$vm_role" ps

printf '\n--- Container resource usage ---\n'
mapfile -t container_ids < <(docker ps --filter label=com.docker.compose.project=flight-tracker --format '{{.ID}}')
if [[ ${#container_ids[@]} -gt 0 ]]; then
  docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' "${container_ids[@]}"
else
  printf 'No running Flight Tracker containers.\n'
fi

printf '\n--- VM memory ---\n'
free -h

printf '\n--- VM disk ---\n'
df -h /