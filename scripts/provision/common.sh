disable_services() {
  local service
  for service in "$@"; do
    if systemctl cat "$service" >/dev/null 2>&1; then
      systemctl disable --now "$service"
    fi
  done
}
