#!/usr/bin/env bash
set -euo pipefail

VMS=(bastion database fetcher history ui)
machine_status="$(vagrant status --machine-readable)"

for vm in "${VMS[@]}"; do
  state="$(awk -F, -v target="$vm" '$2 == target && $3 == "state" { print $4; exit }' <<<"$machine_status")"
  printf '\n=== %s (%s) ===\n' "$vm" "${state:-unknown}"
  if [[ "$state" != running ]]; then
    continue
  fi

  if [[ "$vm" == bastion ]]; then
    vagrant ssh "$vm" -c 'sudo systemctl is-active ssh && ip -brief address'
    continue
  fi

  vagrant ssh "$vm" -c 'sudo /opt/flight-tracker/scripts/vagrant-runtime-status.sh'
done
