#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="${APP_USER:-${SUDO_USER:-$(id -un)}}"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
BAZI_DIR="${BAZI_DIR:-$APP_HOME/bazi-agent-v2}"
STOCK_DIR="${STOCK_DIR:-$APP_HOME/stock_realtime_v021_full}"
PUBLIC_PORT="${PUBLIC_PORT:-8000}"
BAZI_API_PORT="${BAZI_API_PORT:-8101}"
ZHONGYI_PORT="${ZHONGYI_PORT:-8100}"
STOCK_PORT="${STOCK_PORT:-8501}"
STOCK_BASE_PATH="${STOCK_BASE_PATH:-stock}"
STOCK_SERVICE="${STOCK_SERVICE:-as1455-dashboard}"
MATRIX_ROOT="${MATRIX_ROOT:-$STOCK_DIR/saved_data/ashare_ml4t/ch17_as1455_global_fixed_signal_matrix/refresh_all_v1}"
WEB_ROOT="${WEB_ROOT:-/var/www/dual-agents}"
PORTAL_FILE="$WEB_ROOT/index.html"
STOCK_ENV_FILE="${STOCK_ENV_FILE:-/etc/as1455-dashboard.env}"
STOCK_UNIT_FILE="/etc/systemd/system/${STOCK_SERVICE}.service"
STOCK_PYTHON="$STOCK_DIR/.venv_as1455/bin/python"
NGINX_SITE_AVAILABLE="${NGINX_SITE_AVAILABLE:-/etc/nginx/sites-available/dual-agents-8000}"
NGINX_ACTIVE_SITE="${NGINX_ACTIVE_SITE:-}"
NGINX_HELPER="$BAZI_DIR/scripts/as1455_portal_nginx.py"

NPM_BIN=""
BACKUP_DIR=""
ROLLBACK_READY=0
UNIT_EXISTED=0
ENV_EXISTED=0
BAZI_WEB_EXISTED=0
SERVICE_WAS_ACTIVE=0
SERVICE_WAS_ENABLED=0
GENERATED_REFRESH_TOKEN=""

log() { printf '[stock-portal] %s\n' "$*"; }
fail() { printf '[stock-portal] ERROR: %s\n' "$*" >&2; return 1; }

run_root() {
  if [[ "$EUID" -eq 0 ]]; then "$@"; else sudo "$@"; fi
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

validate_port() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "$name must be numeric"
  (( value >= 1 && value <= 65535 )) || fail "$name must be between 1 and 65535"
}

validate_path() {
  local name="$1" value="$2"
  [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] || fail "$name contains unsupported characters: $value"
}

check_branch() {
  local repo="$1" expected="$2" current
  [[ "${SKIP_BRANCH_CHECK:-0}" == "1" ]] && return 0
  current="$(git -C "$repo" branch --show-current)"
  [[ "$current" == "$expected" ]] || fail "$repo is on branch '$current'; expected '$expected'"
}

http_status() {
  curl --noproxy '*' --http1.1 --header 'Connection: close' \
    --silent --output /dev/null --write-out '%{http_code}' --max-time 10 "$1"
}

wait_for_status() {
  local name="$1" url="$2" expected="$3" attempts="${4:-60}" status i
  for ((i = 1; i <= attempts; i++)); do
    status="$(http_status "$url" || true)"
    if [[ "$status" =~ $expected ]]; then
      log "$name responded with HTTP $status: $url"
      return 0
    fi
    sleep 1
  done
  fail "$name did not reach expected HTTP status ($expected); last=$status url=$url"
}

wait_for_nginx_gateway_generation() {
  local readiness_path="/_as1455_${STOCK_BASE_PATH}_gateway_ready"
  local url="http://127.0.0.1:$PUBLIC_PORT$readiness_path"
  local headers status marker i consecutive=0

  # systemctl reload returns after signalling the Nginx master, before the new
  # workers necessarily accept requests. Require three fresh connections to
  # observe the marker from the new configuration before validating /stock/.
  for ((i = 1; i <= 100; i++)); do
    headers="$(
      curl --noproxy '*' --http1.1 --header 'Connection: close' \
        --silent --show-error --dump-header - --output /dev/null \
        --max-time 3 "$url" 2>/dev/null || true
    )"
    status="$(printf '%s\n' "$headers" | awk 'toupper($1) ~ /^HTTP\// {code=$2} END {print code}')"
    marker="$(
      printf '%s\n' "$headers" \
        | awk 'BEGIN{IGNORECASE=1} /^X-AS1455-Gateway:/ {sub(/\r$/,""); sub(/^[^:]*:[[:space:]]*/,""); print; exit}'
    )"
    if [[ "$status" == "204" && "$marker" == "$STOCK_BASE_PATH" ]]; then
      consecutive=$((consecutive + 1))
      if (( consecutive >= 3 )); then
        log "new Nginx gateway generation is active: $url"
        return 0
      fi
    else
      consecutive=0
    fi
    sleep 0.1
  done

  fail "new Nginx gateway generation did not become active: status=${status:-unknown} marker=${marker:-missing} url=$url"
}

resolve_npm() {
  if command -v npm >/dev/null 2>&1; then
    NPM_BIN="$(command -v npm)"
  elif [[ -x /usr/local/bin/npm ]]; then
    NPM_BIN=/usr/local/bin/npm
  else
    fail "npm is missing; run deploy-dual-services.sh once or install Node.js 18+"
  fi
}

resolve_nginx_site() {
  if [[ -n "$NGINX_ACTIVE_SITE" ]]; then
    validate_path NGINX_ACTIVE_SITE "$NGINX_ACTIVE_SITE"
    [[ -f "$NGINX_ACTIVE_SITE" ]] || fail "Nginx file is missing: $NGINX_ACTIVE_SITE"
  else
    NGINX_ACTIVE_SITE="$(
      run_root python3 "$NGINX_HELPER" resolve \
        --port "$PUBLIC_PORT" \
        --web-root "$WEB_ROOT" \
        --preferred "$NGINX_SITE_AVAILABLE"
    )"
  fi
  [[ -f "$NGINX_ACTIVE_SITE" ]] || fail "could not resolve active Nginx portal file"
  validate_path NGINX_ACTIVE_SITE "$NGINX_ACTIVE_SITE"
  log "active Nginx portal file: $NGINX_ACTIVE_SITE"
}

cleanup() {
  [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]] || run_root rm -rf -- "$BACKUP_DIR" || true
}

rollback() {
  local code="$1"
  trap - ERR
  set +e
  if [[ "$ROLLBACK_READY" != "1" ]]; then exit "$code"; fi
  log "deployment failed; restoring the previous portal deployment"
  [[ ! -f "$BACKUP_DIR/portal.html" ]] || run_root cp -a "$BACKUP_DIR/portal.html" "$PORTAL_FILE"
  [[ ! -f "$BACKUP_DIR/nginx.conf" ]] || run_root cp -a "$BACKUP_DIR/nginx.conf" "$NGINX_ACTIVE_SITE"
  if [[ "$BAZI_WEB_EXISTED" == "1" ]]; then
    run_root find "$WEB_ROOT/bazi" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null || true
    run_root cp -a "$BACKUP_DIR/bazi-web/." "$WEB_ROOT/bazi/"
  fi
  if [[ "$UNIT_EXISTED" == "1" ]]; then
    run_root cp -a "$BACKUP_DIR/service.unit" "$STOCK_UNIT_FILE"
  else
    run_root systemctl disable --now "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    run_root rm -f -- "$STOCK_UNIT_FILE"
  fi
  if [[ "$ENV_EXISTED" == "1" ]]; then
    run_root cp -a "$BACKUP_DIR/service.env" "$STOCK_ENV_FILE"
  else
    run_root rm -f -- "$STOCK_ENV_FILE"
  fi
  run_root systemctl daemon-reload >/dev/null 2>&1 || true
  if [[ "$UNIT_EXISTED" == "1" ]]; then
    [[ "$SERVICE_WAS_ENABLED" == "1" ]] \
      && run_root systemctl enable "$STOCK_SERVICE.service" >/dev/null 2>&1 \
      || run_root systemctl disable "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    [[ "$SERVICE_WAS_ACTIVE" == "1" ]] \
      && run_root systemctl restart "$STOCK_SERVICE.service" >/dev/null 2>&1 \
      || run_root systemctl stop "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
  fi
  run_root nginx -t >/dev/null 2>&1 && run_root systemctl reload nginx.service >/dev/null 2>&1 || true
  exit "$code"
}

on_error() { local code=$?; rollback "$code"; }
trap cleanup EXIT

install_dashboard_dependency() {
  log "installing Streamlit dashboard dependency into .venv_as1455"
  run_as_app "$STOCK_PYTHON" -m pip install -r "$STOCK_DIR/requirements-dashboard.txt"
}

build_bazi_frontend() {
  [[ "${SKIP_BAZI_FRONTEND_BUILD:-0}" == "1" ]] && { log "skipping bazi frontend build"; return 0; }
  resolve_npm
  log "rebuilding bazi frontend for external post-login redirect support"
  run_as_app env npm_config_audit=false npm_config_fund=false \
    "$NPM_BIN" --prefix "$BAZI_DIR/frontend" ci
  run_as_app env VITE_BASE_PATH=/bazi/ "$NPM_BIN" --prefix "$BAZI_DIR/frontend" run build
  run_root install -d -o root -g root -m 755 "$WEB_ROOT/bazi"
  run_root find "$WEB_ROOT/bazi" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  run_root cp -a "$BAZI_DIR/frontend/dist/." "$WEB_ROOT/bazi/"
  run_root chmod -R a+rX "$WEB_ROOT/bazi"
}

install_dashboard_environment() {
  if [[ -s "$STOCK_ENV_FILE" && -z "${AS1455_DASHBOARD_REFRESH_TOKEN:-}" ]]; then
    log "preserving existing $STOCK_ENV_FILE"
    return 0
  fi
  local token="${AS1455_DASHBOARD_REFRESH_TOKEN:-}" temporary
  if [[ -z "$token" ]]; then
    token="$(openssl rand -hex 24)"
    GENERATED_REFRESH_TOKEN="$token"
  fi
  [[ "$token" =~ ^[A-Za-z0-9._-]+$ ]] || fail "refresh token contains unsupported characters"
  temporary="$(mktemp)"
  chmod 600 "$temporary"
  printf 'AS1455_DASHBOARD_REFRESH_TOKEN=%s\n' "$token" > "$temporary"
  run_root install -o root -g root -m 600 "$temporary" "$STOCK_ENV_FILE"
  rm -f -- "$temporary"
}

install_dashboard_service() {
  log "installing systemd service: $STOCK_SERVICE"
  run_root tee "$STOCK_UNIT_FILE" >/dev/null <<UNIT
[Unit]
Description=AS1455 Backtest Dashboard
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$(id -gn "$APP_USER")
WorkingDirectory=$STOCK_DIR
Environment=PYTHONUNBUFFERED=1
Environment=PYTHON_BIN=$STOCK_PYTHON
Environment=HOST=127.0.0.1
Environment=PORT=$STOCK_PORT
Environment=BASE_URL_PATH=$STOCK_BASE_PATH
Environment=MATRIX_ROOT=$MATRIX_ROOT
EnvironmentFile=-$STOCK_ENV_FILE
ExecStart=/bin/bash $STOCK_DIR/scripts/run_as1455_backtest_dashboard.sh
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
  run_root systemctl daemon-reload
  run_root systemctl enable "$STOCK_SERVICE.service"
  run_root systemctl restart "$STOCK_SERVICE.service"
  wait_for_status "AS1455 health endpoint" \
    "http://127.0.0.1:$STOCK_PORT/$STOCK_BASE_PATH/_stcore/health" '^200$'
  wait_for_status "AS1455 root page" \
    "http://127.0.0.1:$STOCK_PORT/$STOCK_BASE_PATH/" '^200$'
}

patch_portal() {
  log "adding AS1455 card to $PORTAL_FILE"
  run_root env PORTAL_FILE="$PORTAL_FILE" STOCK_BASE_PATH="$STOCK_BASE_PATH" python3 - <<'PY'
import os
from pathlib import Path
path = Path(os.environ["PORTAL_FILE"])
html = path.read_text(encoding="utf-8")
base = os.environ["STOCK_BASE_PATH"].strip("/")
card = f'<a class="card" href="/{base}/"><strong>AS1455 策略看板</strong><span>九模型历史回测、严格 OOS 与持仓分析</span></a>'
if f'href="/{base}/"' not in html:
    if "</section>" not in html:
        raise SystemExit("portal does not contain </section>")
    html = html.replace("</section>", card + "</section>", 1)
html = html.replace("width:min(760px,92vw)", "width:min(1080px,92vw)")
path.write_text(html, encoding="utf-8")
PY
  run_root chmod 644 "$PORTAL_FILE"
}

patch_nginx() {
  log "adding authenticated /$STOCK_BASE_PATH/ proxy to $NGINX_ACTIVE_SITE"
  run_root python3 "$NGINX_HELPER" patch \
    --file "$NGINX_ACTIVE_SITE" \
    --port "$PUBLIC_PORT" \
    --web-root "$WEB_ROOT" \
    --bazi-port "$BAZI_API_PORT" \
    --stock-port "$STOCK_PORT" \
    --base "$STOCK_BASE_PATH"
}

validate_auth_backend() {
  local url="http://127.0.0.1:$BAZI_API_PORT/api/v1/auth/me" status
  status="$(http_status "$url" || true)"
  [[ "$status" == "200" || "$status" == "401" ]] \
    || fail "bazi auth endpoint returned HTTP $status: $url"
  log "bazi auth endpoint responded with HTTP $status: $url"
}

validate_gateway_route() {
  local url="http://127.0.0.1:$PUBLIC_PORT/$STOCK_BASE_PATH/" headers status location location_path
  headers="$(
    curl --noproxy '*' --http1.1 --header 'Connection: close' \
      --silent --show-error --dump-header - --output /dev/null --max-time 10 "$url"
  )"
  status="$(printf '%s\n' "$headers" | awk 'toupper($1) ~ /^HTTP\// {code=$2} END {print code}')"
  location="$(printf '%s\n' "$headers" | awk 'BEGIN{IGNORECASE=1} /^Location:/ {sub(/\r$/,""); sub(/^[^:]*:[[:space:]]*/,""); print; exit}')"
  location_path="$location"
  if [[ "$location" =~ ^https?://[^/]+(/.*)$ ]]; then
    location_path="${BASH_REMATCH[1]}"
  fi
  if [[ "$status" == "200" ]]; then
    log "gateway route is directly accessible: $url"
  elif [[ "$status" == "302" && "$location_path" == "/bazi/login?external_redirect=/$STOCK_BASE_PATH/" ]]; then
    log "gateway route correctly redirects unauthenticated users: $location"
  else
    printf '%s\n' "$headers" >&2
    run_root nginx -T 2>&1 | grep -n -A45 -B8 "BEGIN AS1455 DASHBOARD" >&2 || true
    fail "gateway route returned HTTP ${status:-unknown}: $url"
  fi
}

validate_port PUBLIC_PORT "$PUBLIC_PORT"
validate_port BAZI_API_PORT "$BAZI_API_PORT"
validate_port ZHONGYI_PORT "$ZHONGYI_PORT"
validate_port STOCK_PORT "$STOCK_PORT"
[[ "$PUBLIC_PORT" != "$BAZI_API_PORT" && "$PUBLIC_PORT" != "$ZHONGYI_PORT" \
   && "$PUBLIC_PORT" != "$STOCK_PORT" && "$BAZI_API_PORT" != "$ZHONGYI_PORT" \
   && "$BAZI_API_PORT" != "$STOCK_PORT" && "$ZHONGYI_PORT" != "$STOCK_PORT" ]] \
  || fail "all four ports must differ"
[[ "$STOCK_BASE_PATH" =~ ^[A-Za-z0-9._-]+$ ]] || fail "invalid STOCK_BASE_PATH"
[[ "$STOCK_SERVICE" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "invalid STOCK_SERVICE"
[[ -n "$APP_HOME" ]] || fail "could not resolve home directory for $APP_USER"
for item in BAZI_DIR STOCK_DIR MATRIX_ROOT WEB_ROOT STOCK_ENV_FILE NGINX_SITE_AVAILABLE; do
  validate_path "$item" "${!item}"
done
id "$APP_USER" >/dev/null 2>&1 || fail "application user does not exist: $APP_USER"
[[ "$EUID" -ne 0 || "$(id -un)" == "$APP_USER" ]] || command -v runuser >/dev/null 2>&1 || fail "runuser is required"
command -v sudo >/dev/null 2>&1 || [[ "$EUID" -eq 0 ]] || fail "sudo is required"
for command_name in systemctl nginx curl python3 openssl git; do
  command -v "$command_name" >/dev/null 2>&1 || fail "$command_name is required"
done
[[ -f "$NGINX_HELPER" ]] || fail "Nginx helper is missing: $NGINX_HELPER"
[[ -f "$BAZI_DIR/frontend/package-lock.json" ]] || fail "bazi frontend is missing"
[[ -f "$BAZI_DIR/frontend/src/pages/LoginPage.vue" ]] || fail "bazi LoginPage.vue is missing"
[[ -x "$STOCK_PYTHON" ]] || fail "stock virtual environment is missing: $STOCK_PYTHON"
[[ -f "$STOCK_DIR/requirements-dashboard.txt" ]] || fail "requirements-dashboard.txt is missing"
[[ -f "$STOCK_DIR/scripts/run_as1455_backtest_dashboard.sh" ]] || fail "dashboard launcher is missing"
[[ -f "$PORTAL_FILE" ]] || fail "portal is not deployed: $PORTAL_FILE"
grep -q 'external_redirect' "$BAZI_DIR/frontend/src/pages/LoginPage.vue" || fail "bazi branch lacks external redirect support"
grep -q 'server.baseUrlPath' "$STOCK_DIR/scripts/run_as1455_backtest_dashboard.sh" || fail "stock branch lacks baseUrlPath support"
check_branch "$BAZI_DIR" "${EXPECTED_BAZI_BRANCH:-agent/mobile-ui-deterministic-chat}"
check_branch "$STOCK_DIR" "${EXPECTED_STOCK_BRANCH:-agent/ch17-as1455-clean}"
resolve_nginx_site
validate_auth_backend
install_dashboard_dependency

BACKUP_DIR="$(mktemp -d)"
run_root cp -a "$PORTAL_FILE" "$BACKUP_DIR/portal.html"
run_root cp -a "$NGINX_ACTIVE_SITE" "$BACKUP_DIR/nginx.conf"
if [[ -d "$WEB_ROOT/bazi" ]]; then
  BAZI_WEB_EXISTED=1
  run_root mkdir -p "$BACKUP_DIR/bazi-web"
  run_root cp -a "$WEB_ROOT/bazi/." "$BACKUP_DIR/bazi-web/"
fi
if run_root systemctl is-active --quiet "$STOCK_SERVICE.service"; then SERVICE_WAS_ACTIVE=1; fi
if run_root systemctl is-enabled --quiet "$STOCK_SERVICE.service"; then SERVICE_WAS_ENABLED=1; fi
if [[ -f "$STOCK_UNIT_FILE" ]]; then
  UNIT_EXISTED=1
  run_root cp -a "$STOCK_UNIT_FILE" "$BACKUP_DIR/service.unit"
fi
if [[ -f "$STOCK_ENV_FILE" ]]; then
  ENV_EXISTED=1
  run_root cp -a "$STOCK_ENV_FILE" "$BACKUP_DIR/service.env"
fi
ROLLBACK_READY=1
trap on_error ERR

build_bazi_frontend
install_dashboard_environment
install_dashboard_service
patch_portal
patch_nginx
run_root nginx -t
run_root systemctl reload nginx.service
wait_for_nginx_gateway_generation
wait_for_status "portal" "http://127.0.0.1:$PUBLIC_PORT/" '^200$'
wait_for_status "bazi login page" "http://127.0.0.1:$PUBLIC_PORT/bazi/login" '^200$'
validate_gateway_route
grep -q "href=\"/$STOCK_BASE_PATH/\"" "$PORTAL_FILE" || fail "portal card validation failed"

trap - ERR
log "AS1455 dashboard portal integration succeeded"
printf '\nAccess URL:\n  http://<server-ip>:%s/%s/\n' "$PUBLIC_PORT" "$STOCK_BASE_PATH"
printf '\nService status:\n  sudo systemctl status %s nginx\n' "$STOCK_SERVICE"
if [[ -n "$GENERATED_REFRESH_TOKEN" ]]; then
  printf '\nGenerated dashboard refresh token:\n  %s\n' "$GENERATED_REFRESH_TOKEN"
  printf 'Save it now; it is stored root-only in %s.\n' "$STOCK_ENV_FILE"
fi
