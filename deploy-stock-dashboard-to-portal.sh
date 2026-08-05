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
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-available/dual-agents-8000}"
WEB_ROOT="${WEB_ROOT:-/var/www/dual-agents}"
PORTAL_FILE="$WEB_ROOT/index.html"
STOCK_ENV_FILE="${STOCK_ENV_FILE:-/etc/as1455-dashboard.env}"
STOCK_UNIT_FILE="/etc/systemd/system/${STOCK_SERVICE}.service"
STOCK_PYTHON="$STOCK_DIR/.venv_as1455/bin/python"
NPM_BIN=""
BACKUP_DIR=""
UNIT_EXISTED=0
ENV_EXISTED=0
BAZI_WEB_EXISTED=0
SERVICE_WAS_ACTIVE=0
GENERATED_REFRESH_TOKEN=""

log() { printf '[stock-portal] %s\n' "$*"; }
fail() { printf '[stock-portal] ERROR: %s\n' "$*" >&2; exit 1; }

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

cleanup() {
  [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]] || run_root rm -rf -- "$BACKUP_DIR"
}

rollback() {
  local code="$1"
  set +e
  log "deployment failed; restoring portal and Nginx configuration"
  [[ ! -f "$BACKUP_DIR/portal.html" ]] || run_root cp -a "$BACKUP_DIR/portal.html" "$PORTAL_FILE"
  [[ ! -f "$BACKUP_DIR/nginx-site.conf" ]] || run_root cp -a "$BACKUP_DIR/nginx-site.conf" "$NGINX_SITE"
  if [[ "$BAZI_WEB_EXISTED" == "1" && -d "$BACKUP_DIR/bazi-web" ]]; then
    run_root find "$WEB_ROOT/bazi" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null || true
    run_root cp -a "$BACKUP_DIR/bazi-web/." "$WEB_ROOT/bazi/"
  fi

  if [[ "$UNIT_EXISTED" == "1" && -f "$BACKUP_DIR/service.unit" ]]; then
    run_root cp -a "$BACKUP_DIR/service.unit" "$STOCK_UNIT_FILE"
  else
    run_root systemctl disable --now "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    run_root rm -f -- "$STOCK_UNIT_FILE"
  fi

  if [[ "$ENV_EXISTED" == "1" && -f "$BACKUP_DIR/service.env" ]]; then
    run_root cp -a "$BACKUP_DIR/service.env" "$STOCK_ENV_FILE"
  elif [[ "$ENV_EXISTED" == "0" ]]; then
    run_root rm -f -- "$STOCK_ENV_FILE"
  fi

  run_root systemctl daemon-reload >/dev/null 2>&1 || true
  if [[ "$UNIT_EXISTED" == "1" ]]; then
    if [[ "$SERVICE_WAS_ACTIVE" == "1" ]]; then
      run_root systemctl restart "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    else
      run_root systemctl stop "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    fi
  fi
  run_root nginx -t >/dev/null 2>&1 && run_root systemctl reload nginx.service >/dev/null 2>&1 || true
  exit "$code"
}

on_error() { local code=$?; rollback "$code"; }
trap cleanup EXIT
trap on_error ERR

wait_for_url() {
  local name="$1" url="$2" attempts="${3:-60}" i
  for ((i = 1; i <= attempts; i++)); do
    if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null 2>&1; then
      log "$name is healthy: $url"
      return 0
    fi
    sleep 1
  done
  fail "$name did not become healthy: $url"
}

check_branch() {
  local repo="$1" expected="$2" current
  [[ "${SKIP_BRANCH_CHECK:-0}" == "1" ]] && return 0
  current="$(git -C "$repo" branch --show-current)"
  [[ "$current" == "$expected" ]] \
    || fail "$repo is on branch '$current'; expected '$expected'"
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

install_dashboard_dependency() {
  log "installing Streamlit dashboard dependency into .venv_as1455"
  run_as_app "$STOCK_PYTHON" -m pip install -r "$STOCK_DIR/requirements-dashboard.txt"
}

build_bazi_frontend() {
  if [[ "${SKIP_BAZI_FRONTEND_BUILD:-0}" == "1" ]]; then
    log "skipping bazi frontend build"
    return 0
  fi
  resolve_npm
  log "rebuilding bazi frontend for external post-login redirect support"
  run_as_app env npm_config_audit=false npm_config_fund=false \
    "$NPM_BIN" --prefix "$BAZI_DIR/frontend" ci
  run_as_app env VITE_BASE_PATH=/bazi/ \
    "$NPM_BIN" --prefix "$BAZI_DIR/frontend" run build
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
  [[ "$token" =~ ^[A-Za-z0-9._-]+$ ]] || fail "refresh token may contain only letters, numbers, dot, underscore and hyphen"
  temporary="$(mktemp)"
  chmod 600 "$temporary"
  printf 'AS1455_DASHBOARD_REFRESH_TOKEN=%s\n' "$token" > "$temporary"
  run_root install -o root -g root -m 600 "$temporary" "$STOCK_ENV_FILE"
  rm -f -- "$temporary"
}

install_dashboard_service() {
  log "installing systemd service: $STOCK_SERVICE"
  run_root tee "$STOCK_UNIT_FILE" >/dev/null <<EOF
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
EOF
  run_root systemctl daemon-reload
  run_root systemctl enable "$STOCK_SERVICE.service"
  run_root systemctl restart "$STOCK_SERVICE.service"
  wait_for_url "AS1455 dashboard" "http://127.0.0.1:$STOCK_PORT/$STOCK_BASE_PATH/_stcore/health"
}

patch_portal() {
  log "adding AS1455 card to $PORTAL_FILE"
  run_root env PORTAL_FILE="$PORTAL_FILE" STOCK_BASE_PATH="$STOCK_BASE_PATH" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["PORTAL_FILE"])
html = path.read_text(encoding="utf-8")
base = os.environ["STOCK_BASE_PATH"].strip("/")
card = (
    f'<a class="card" href="/{base}/"><strong>AS1455 策略看板</strong>'
    '<span>九模型历史回测、严格 OOS 与持仓分析</span></a>'
)
if f'href="/{base}/"' not in html:
    marker = "</section>"
    if marker not in html:
        raise SystemExit("portal does not contain </section>")
    html = html.replace(marker, card + marker, 1)
html = html.replace("width:min(760px,92vw)", "width:min(1080px,92vw)")
path.write_text(html, encoding="utf-8")
PY
  run_root chmod 644 "$PORTAL_FILE"
}

patch_nginx() {
  log "adding authenticated /$STOCK_BASE_PATH/ proxy to $NGINX_SITE"
  run_root env NGINX_SITE="$NGINX_SITE" BAZI_API_PORT="$BAZI_API_PORT" \
    STOCK_PORT="$STOCK_PORT" STOCK_BASE_PATH="$STOCK_BASE_PATH" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["NGINX_SITE"])
text = path.read_text(encoding="utf-8")
base = os.environ["STOCK_BASE_PATH"].strip("/")
bazi_port = int(os.environ["BAZI_API_PORT"])
stock_port = int(os.environ["STOCK_PORT"])
begin = "    # BEGIN AS1455 DASHBOARD"
end = "    # END AS1455 DASHBOARD"
block = f"""    # BEGIN AS1455 DASHBOARD
    location = /_portal_auth {{
        internal;
        proxy_pass http://127.0.0.1:{bazi_port}/api/v1/auth/me;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Cookie $http_cookie;
        proxy_set_header Host $host;
        proxy_set_header X-Original-URI $request_uri;
    }}

    location = /{base} {{
        return 301 /{base}/;
    }}

    location ^~ /{base}/ {{
        auth_request /_portal_auth;
        error_page 401 403 =302 /bazi/login?external_redirect=/{base}/;

        proxy_pass http://127.0.0.1:{stock_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /{base};
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }}
    # END AS1455 DASHBOARD"""
if begin in text:
    start = text.index(begin)
    finish = text.index(end, start) + len(end)
    text = text[:start] + block + text[finish:]
else:
    closing = text.rfind("\n}")
    if closing < 0:
        raise SystemExit("Nginx site does not contain a final server closing brace")
    text = text[:closing] + "\n\n" + block + text[closing:]
path.write_text(text, encoding="utf-8")
PY
}

validate_port PUBLIC_PORT "$PUBLIC_PORT"
validate_port BAZI_API_PORT "$BAZI_API_PORT"
validate_port ZHONGYI_PORT "$ZHONGYI_PORT"
validate_port STOCK_PORT "$STOCK_PORT"
[[ "$PUBLIC_PORT" != "$BAZI_API_PORT" && "$PUBLIC_PORT" != "$ZHONGYI_PORT" \
   && "$PUBLIC_PORT" != "$STOCK_PORT" && "$BAZI_API_PORT" != "$ZHONGYI_PORT" \
   && "$BAZI_API_PORT" != "$STOCK_PORT" && "$ZHONGYI_PORT" != "$STOCK_PORT" ]] \
  || fail "PUBLIC_PORT, BAZI_API_PORT, ZHONGYI_PORT and STOCK_PORT must differ"
[[ "$STOCK_BASE_PATH" =~ ^[A-Za-z0-9._-]+$ ]] || fail "invalid STOCK_BASE_PATH"
[[ "$STOCK_SERVICE" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "invalid STOCK_SERVICE"
[[ -n "$APP_HOME" ]] || fail "could not resolve home directory for $APP_USER"
validate_path BAZI_DIR "$BAZI_DIR"
validate_path STOCK_DIR "$STOCK_DIR"
validate_path MATRIX_ROOT "$MATRIX_ROOT"
validate_path NGINX_SITE "$NGINX_SITE"
validate_path WEB_ROOT "$WEB_ROOT"
validate_path STOCK_ENV_FILE "$STOCK_ENV_FILE"

id "$APP_USER" >/dev/null 2>&1 || fail "application user does not exist: $APP_USER"
[[ "$EUID" -ne 0 || "$(id -un)" == "$APP_USER" ]] || command -v runuser >/dev/null 2>&1 \
  || fail "runuser is required"
command -v sudo >/dev/null 2>&1 || [[ "$EUID" -eq 0 ]] || fail "sudo is required"
command -v systemctl >/dev/null 2>&1 || fail "systemd is required"
command -v nginx >/dev/null 2>&1 || fail "nginx is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v openssl >/dev/null 2>&1 || fail "openssl is required"
command -v git >/dev/null 2>&1 || fail "git is required"

[[ -f "$BAZI_DIR/frontend/package-lock.json" ]] || fail "bazi frontend not found at $BAZI_DIR/frontend"
[[ -f "$BAZI_DIR/frontend/src/pages/LoginPage.vue" ]] || fail "bazi LoginPage.vue is missing"
[[ -x "$STOCK_PYTHON" ]] || fail "stock virtual environment is missing: $STOCK_PYTHON"
[[ -f "$STOCK_DIR/requirements-dashboard.txt" ]] || fail "requirements-dashboard.txt is missing"
[[ -f "$STOCK_DIR/scripts/run_as1455_backtest_dashboard.sh" ]] || fail "dashboard launcher is missing"
[[ -f "$PORTAL_FILE" ]] || fail "portal is not deployed: $PORTAL_FILE"
[[ -f "$NGINX_SITE" ]] || fail "Nginx portal site is missing: $NGINX_SITE"
grep -q 'external_redirect' "$BAZI_DIR/frontend/src/pages/LoginPage.vue" \
  || fail "bazi branch is missing external login redirect support; pull the latest branch"
grep -q 'server.baseUrlPath' "$STOCK_DIR/scripts/run_as1455_backtest_dashboard.sh" \
  || fail "stock branch is missing Streamlit baseUrlPath support; pull the latest branch"
check_branch "$BAZI_DIR" "${EXPECTED_BAZI_BRANCH:-agent/mobile-ui-deterministic-chat}"
check_branch "$STOCK_DIR" "${EXPECTED_STOCK_BRANCH:-agent/ch17-as1455-clean}"

BACKUP_DIR="$(mktemp -d)"
run_root cp -a "$PORTAL_FILE" "$BACKUP_DIR/portal.html"
run_root cp -a "$NGINX_SITE" "$BACKUP_DIR/nginx-site.conf"
if [[ -d "$WEB_ROOT/bazi" ]]; then
  BAZI_WEB_EXISTED=1
  run_root mkdir -p "$BACKUP_DIR/bazi-web"
  run_root cp -a "$WEB_ROOT/bazi/." "$BACKUP_DIR/bazi-web/"
fi
if run_root systemctl is-active --quiet "$STOCK_SERVICE.service"; then
  SERVICE_WAS_ACTIVE=1
fi
if [[ -f "$STOCK_UNIT_FILE" ]]; then
  UNIT_EXISTED=1
  run_root cp -a "$STOCK_UNIT_FILE" "$BACKUP_DIR/service.unit"
fi
if [[ -f "$STOCK_ENV_FILE" ]]; then
  ENV_EXISTED=1
  run_root cp -a "$STOCK_ENV_FILE" "$BACKUP_DIR/service.env"
fi

install_dashboard_dependency
build_bazi_frontend
install_dashboard_environment
install_dashboard_service
patch_portal
patch_nginx
run_root nginx -t
run_root systemctl reload nginx.service
wait_for_url "portal" "http://127.0.0.1:$PUBLIC_PORT/"

trap - ERR
log "AS1455 dashboard portal integration succeeded"
printf '\nAccess URL:\n'
printf '  http://<server-ip>:%s/%s/\n' "$PUBLIC_PORT" "$STOCK_BASE_PATH"
printf '\nService status:\n'
printf '  sudo systemctl status %s nginx\n' "$STOCK_SERVICE"
printf '  sudo journalctl -u %s -f\n' "$STOCK_SERVICE"
if [[ -n "$GENERATED_REFRESH_TOKEN" ]]; then
  printf '\nGenerated dashboard refresh token:\n'
  printf '  %s\n' "$GENERATED_REFRESH_TOKEN"
  printf '  Save it now; it is stored root-only in %s.\n' "$STOCK_ENV_FILE"
fi
