#!/usr/bin/env bash
set -Eeuo pipefail

BAZI_SERVICE="${BAZI_SERVICE:-bazi-agent-v2}"
ZHONGYI_SERVICE="${ZHONGYI_SERVICE:-zhongyi-diag}"
PUBLIC_PORT="${PUBLIC_PORT:-8000}"
ZHONGYI_PORT="${ZHONGYI_PORT:-8100}"
BAZI_API_PORT="${BAZI_API_PORT:-8101}"
STOCK_PORT="${STOCK_PORT:-8501}"
STOCK_BASE_PATH="${STOCK_BASE_PATH:-stock}"
STOCK_SERVICE="${STOCK_SERVICE:-as1455-dashboard}"
APP_USER="${APP_USER:-${SUDO_USER:-$(id -un)}}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BAZI_DIR="$SCRIPT_DIR"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
ZHONGYI_DIR="${ZHONGYI_DIR:-$APP_HOME/zhongyi-diag}"
STOCK_PRESERVE_SCRIPT="$BAZI_DIR/scripts/restore-stock-portal-if-present.sh"

log() {
  printf '[dual-manage] %s\n' "$*"
}

fail() {
  printf '[dual-manage] ERROR: %s\n' "$*" >&2
  exit 1
}

run_root() {
  if [[ "$EUID" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

run_as_app() {
  if [[ "$(id -un)" == "$APP_USER" ]]; then
    "$@"
  elif [[ "$EUID" -eq 0 ]]; then
    runuser -u "$APP_USER" -- env HOME="$APP_HOME" "$@"
  else
    sudo -u "$APP_USER" -- env HOME="$APP_HOME" "$@"
  fi
}

usage() {
  cat <<'EOF'
Usage: ./manage-dual-services.sh COMMAND

Commands:
  start            Start both applications and Nginx
  stop             Stop Nginx and both applications
  restart          Restart both applications and Nginx
  status           Show service status
  logs             Follow logs for both applications
  update-zhongyi   Pull zhongyi-diag and redeploy only that service
  update-all       Pull both repositories and run the full deployment; preserve an existing stock portal
EOF
}

validate_repo() {
  local directory="$1"
  [[ -d "$directory/.git" ]] || fail "Git repository not found: $directory"
  if [[ -n "$(run_as_app git -C "$directory" status --porcelain --untracked-files=no)" ]]; then
    fail "Tracked local changes found in $directory; commit or stash them before updating"
  fi
}

pull_repo() {
  local name="$1"
  local directory="$2"
  validate_repo "$directory"
  log "Updating $name"
  run_as_app git -C "$directory" pull --ff-only
}

update_zhongyi() {
  [[ -f "$ZHONGYI_DIR/deploy.sh" ]] || fail "deploy.sh not found in $ZHONGYI_DIR"
  pull_repo "zhongyi-diag" "$ZHONGYI_DIR"
  log "Installing dependencies and restarting $ZHONGYI_SERVICE"
  run_as_app env \
    APP_USER="$APP_USER" \
    SERVICE_NAME="$ZHONGYI_SERVICE" \
    BIND_HOST=127.0.0.1 \
    PORT="$ZHONGYI_PORT" \
    SKIP_APT=1 \
    REBUILD_RAG=1 \
    bash "$ZHONGYI_DIR/deploy.sh"
  run_root systemctl enable --now nginx.service
  curl --fail --silent --show-error --max-time 10 \
    "http://127.0.0.1:$PUBLIC_PORT/zhongyi/" >/dev/null
  log "zhongyi-diag update succeeded"
}

restore_stock_portal_if_present() {
  [[ -f "$STOCK_PRESERVE_SCRIPT" ]] || {
    log "stock preservation helper is absent; skipping"
    return 0
  }
  env \
    PUBLIC_PORT="$PUBLIC_PORT" \
    BAZI_API_PORT="$BAZI_API_PORT" \
    STOCK_PORT="$STOCK_PORT" \
    STOCK_BASE_PATH="$STOCK_BASE_PATH" \
    STOCK_SERVICE="$STOCK_SERVICE" \
    bash "$STOCK_PRESERVE_SCRIPT"
}

[[ -n "$APP_HOME" ]] || fail "Could not resolve home directory for $APP_USER"
id "$APP_USER" >/dev/null 2>&1 || fail "Application user does not exist: $APP_USER"
command -v systemctl >/dev/null 2>&1 || fail "systemd is required"

case "${1:-}" in
  start)
    run_root systemctl start "$BAZI_SERVICE.service" "$ZHONGYI_SERVICE.service" nginx.service
    ;;
  stop)
    run_root systemctl stop nginx.service "$BAZI_SERVICE.service" "$ZHONGYI_SERVICE.service"
    ;;
  restart)
    run_root systemctl restart "$BAZI_SERVICE.service" "$ZHONGYI_SERVICE.service" nginx.service
    ;;
  status)
    run_root systemctl status "$BAZI_SERVICE.service" "$ZHONGYI_SERVICE.service" nginx.service --no-pager || true
    ;;
  logs)
    run_root journalctl -u "$BAZI_SERVICE.service" -u "$ZHONGYI_SERVICE.service" -f
    ;;
  update-zhongyi)
    update_zhongyi
    ;;
  update-all)
    pull_repo "bazi-agent-v2" "$BAZI_DIR"
    pull_repo "zhongyi-diag" "$ZHONGYI_DIR"
    log "Running the full dual-service deployment"
    env APP_USER="$APP_USER" ZHONGYI_DIR="$ZHONGYI_DIR" \
      PUBLIC_PORT="$PUBLIC_PORT" ZHONGYI_PORT="$ZHONGYI_PORT" BAZI_API_PORT="$BAZI_API_PORT" \
      bash "$BAZI_DIR/deploy-dual-services.sh"
    restore_stock_portal_if_present
    log "Full update succeeded"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
