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
NGINX_SITE_NAME="${NGINX_SITE_NAME:-dual-agents-8000}"
NGINX_SITE_AVAILABLE="${NGINX_SITE_AVAILABLE:-/etc/nginx/sites-available/$NGINX_SITE_NAME}"
NGINX_SITE_ENABLED="${NGINX_SITE_ENABLED:-/etc/nginx/sites-enabled/$NGINX_SITE_NAME}"
NGINX_ACTIVE_SITE="${NGINX_ACTIVE_SITE:-}"

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

validate_port() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "$name must be numeric"
  (( value >= 1 && value <= 65535 )) || fail "$name must be between 1 and 65535"
}

validate_path() {
  local name="$1" value="$2"
  [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] \
    || fail "$name contains unsupported characters: $value"
}

check_branch() {
  local repo="$1" expected="$2" current
  [[ "${SKIP_BRANCH_CHECK:-0}" == "1" ]] && return 0
  current="$(git -C "$repo" branch --show-current)"
  [[ "$current" == "$expected" ]] \
    || fail "$repo is on branch '$current'; expected '$expected'"
}

resolve_active_nginx_site() {
  if [[ -n "$NGINX_ACTIVE_SITE" ]]; then
    validate_path NGINX_ACTIVE_SITE "$NGINX_ACTIVE_SITE"
    [[ -f "$NGINX_ACTIVE_SITE" ]] || fail "active Nginx site is missing: $NGINX_ACTIVE_SITE"
    return 0
  fi

  if [[ -L "$NGINX_SITE_ENABLED" ]]; then
    NGINX_ACTIVE_SITE="$(readlink -f "$NGINX_SITE_ENABLED")"
  elif [[ -f "$NGINX_SITE_ENABLED" ]]; then
    NGINX_ACTIVE_SITE="$NGINX_SITE_ENABLED"
  else
    fail "enabled Nginx site is missing: $NGINX_SITE_ENABLED"
  fi

  [[ -n "$NGINX_ACTIVE_SITE" && -f "$NGINX_ACTIVE_SITE" ]] \
    || fail "could not resolve the active Nginx site from $NGINX_SITE_ENABLED"
  validate_path NGINX_ACTIVE_SITE "$NGINX_ACTIVE_SITE"
  log "active Nginx site: $NGINX_ACTIVE_SITE"
  if [[ -f "$NGINX_SITE_AVAILABLE" && "$NGINX_ACTIVE_SITE" != "$NGINX_SITE_AVAILABLE" ]]; then
    log "notice: enabled site does not target $NGINX_SITE_AVAILABLE; patching the active file"
  fi
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

http_status() {
  curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 "$1"
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

cleanup() {
  if [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]]; then
    run_root rm -rf -- "$BACKUP_DIR" || true
  fi
}

rollback() {
  local code="$1"
  trap - ERR
  set +e
  if [[ "$ROLLBACK_READY" != "1" ]]; then
    exit "$code"
  fi

  log "deployment failed; restoring the previous portal deployment"
  [[ ! -f "$BACKUP_DIR/portal.html" ]] \
    || run_root cp -a "$BACKUP_DIR/portal.html" "$PORTAL_FILE"
  [[ ! -f "$BACKUP_DIR/nginx-active.conf" ]] \
    || run_root cp -a "$BACKUP_DIR/nginx-active.conf" "$NGINX_ACTIVE_SITE"

  if [[ "$BAZI_WEB_EXISTED" == "1" && -d "$BACKUP_DIR/bazi-web" ]]; then
    run_root find "$WEB_ROOT/bazi" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + \
      2>/dev/null || true
    run_root cp -a "$BACKUP_DIR/bazi-web/." "$WEB_ROOT/bazi/"
  elif [[ "$BAZI_WEB_EXISTED" == "0" ]]; then
    run_root rm -rf -- "$WEB_ROOT/bazi"
  fi

  if [[ "$UNIT_EXISTED" == "1" && -f "$BACKUP_DIR/service.unit" ]]; then
    run_root cp -a "$BACKUP_DIR/service.unit" "$STOCK_UNIT_FILE"
  else
    run_root systemctl disable --now "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    run_root rm -f -- "$STOCK_UNIT_FILE"
  fi

  if [[ "$ENV_EXISTED" == "1" && -f "$BACKUP_DIR/service.env" ]]; then
    run_root cp -a "$BACKUP_DIR/service.env" "$STOCK_ENV_FILE"
  else
    run_root rm -f -- "$STOCK_ENV_FILE"
  fi

  run_root systemctl daemon-reload >/dev/null 2>&1 || true
  if [[ "$UNIT_EXISTED" == "1" ]]; then
    if [[ "$SERVICE_WAS_ENABLED" == "1" ]]; then
      run_root systemctl enable "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    else
      run_root systemctl disable "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    fi
    if [[ "$SERVICE_WAS_ACTIVE" == "1" ]]; then
      run_root systemctl restart "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    else
      run_root systemctl stop "$STOCK_SERVICE.service" >/dev/null 2>&1 || true
    fi
  fi

  run_root nginx -t >/dev/null 2>&1 \
    && run_root systemctl reload nginx.service >/dev/null 2>&1 || true
  exit "$code"
}

on_error() { local code=$?; rollback "$code"; }
trap cleanup EXIT

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
  [[ "$token" =~ ^[A-Za-z0-9._-]+$ ]] \
    || fail "refresh token may contain only letters, numbers, dot, underscore and hyphen"
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
  log "adding authenticated /$STOCK_BASE_PATH/ proxy to $NGINX_ACTIVE_SITE"
  run_root env NGINX_SITE="$NGINX_ACTIVE_SITE" PUBLIC_PORT="$PUBLIC_PORT" \
    BAZI_API_PORT="$BAZI_API_PORT" STOCK_PORT="$STOCK_PORT" \
    STOCK_BASE_PATH="$STOCK_BASE_PATH" python3 - <<'PY'
import os
import re
from pathlib import Path

path = Path(os.environ["NGINX_SITE"])
text = path.read_text(encoding="utf-8")
public_port = int(os.environ["PUBLIC_PORT"])
base = os.environ["STOCK_BASE_PATH"].strip("/")
bazi_port = int(os.environ["BAZI_API_PORT"])
stock_port = int(os.environ["STOCK_PORT"])
begin = "    # BEGIN AS1455 DASHBOARD"
end = "    # END AS1455 DASHBOARD"
auth_uri = "_as1455_portal_auth"
login_location = "@as1455_stock_login"
block = f"""    # BEGIN AS1455 DASHBOARD
    location = /{auth_uri} {{
        internal;
        proxy_pass http://127.0.0.1:{bazi_port}/api/v1/auth/me;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Cookie $http_cookie;
        proxy_set_header Host $host;
        proxy_set_header X-Original-URI $request_uri;
    }}

    location {login_location} {{
        return 302 /bazi/login?external_redirect=/{base}/;
    }}

    location = /{base} {{
        return 301 /{base}/;
    }}

    location ^~ /{base}/ {{
        auth_request /{auth_uri};
        error_page 401 403 = {login_location};

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
    listen_pattern = re.compile(rf"\blisten\s+(?:\[[^]]+\]:)?{public_port}\b")
    listen_match = listen_pattern.search(text)
    if not listen_match:
        raise SystemExit(f"active Nginx file has no server listening on {public_port}")
    server_start = text.rfind("server", 0, listen_match.start())
    brace_start = text.find("{", server_start, listen_match.start())
    if server_start < 0 or brace_start < 0:
        raise SystemExit("could not locate the target server block")
    depth = 0
    server_end = None
    for index in range(brace_start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                server_end = index
                break
    if server_end is None:
        raise SystemExit("target server block has unbalanced braces")
    text = text[:server_end] + "\n\n" + block + "\n" + text[server_end:]

path.write_text(text, encoding="utf-8")
PY
}

validate_auth_backend() {
  local url="http://127.0.0.1:$BAZI_API_PORT/api/v1/auth/me" status
  status="$(http_status "$url" || true)"
  case "$status" in
    200|401) log "bazi auth endpoint responded with HTTP $status: $url" ;;
    *) fail "bazi auth endpoint returned HTTP $status: $url" ;;
  esac
}

validate_gateway_route() {
  local url="http://127.0.0.1:$PUBLIC_PORT/$STOCK_BASE_PATH/" headers status location
  headers="$(curl --silent --show-error --dump-header - --output /dev/null --max-time 10 "$url")"
  status="$(printf '%s\n' "$headers" | awk 'toupper($1) ~ /^HTTP\// {code=$2} END {print code}')"
  location="$(printf '%s\n' "$headers" | awk 'BEGIN{IGNORECASE=1} /^Location:/ {sub(/\r$/,""); sub(/^[^:]*:[[:space:]]*/,""); print; exit}')"
  case "$status" in
    200)
      log "gateway route is directly accessible: $url"
      ;;
    302)
      [[ "$location" == "/bazi/login?external_redirect=/$STOCK_BASE_PATH/" ]] \
        || fail "gateway redirect target is unexpected: ${location:-<missing>}"
      log "gateway route correctly redirects unauthenticated users: $location"
      ;;
    *)
      printf '%s\n' "$headers" >&2
      fail "gateway route returned HTTP ${status:-unknown}: $url"
      ;;
  esac
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
validate_path WEB_ROOT "$WEB_ROOT"
validate_path STOCK_ENV_FILE "$STOCK_ENV_FILE"
validate_path NGINX_SITE_AVAILABLE "$NGINX_SITE_AVAILABLE"
validate_path NGINX_SITE_ENABLED "$NGINX_SITE_ENABLED"

id "$APP_USER" >/dev/null 2>&1 || fail "application user does not exist: $APP_USER"
[[ "$EUID" -ne 0 || "$(id -un)" == "$APP_USER" ]] \
  || command -v runuser >/dev/null 2>&1 || fail "runuser is required"
command -v sudo >/dev/null 2>&1 || [[ "$EUID" -eq 0 ]] || fail "sudo is required"
for command_name in systemctl nginx curl python3 openssl git; do
  command -v "$command_name" >/dev/null 2>&1 || fail "$command_name is required"
done

[[ -f "$BAZI_DIR/frontend/package-lock.json" ]] \
  || fail "bazi frontend not found at $BAZI_DIR/frontend"
[[ -f "$BAZI_DIR/frontend/src/pages/LoginPage.vue" ]] || fail "bazi LoginPage.vue is missing"
[[ -x "$STOCK_PYTHON" ]] || fail "stock virtual environment is missing: $STOCK_PYTHON"
[[ -f "$STOCK_DIR/requirements-dashboard.txt" ]] || fail "requirements-dashboard.txt is missing"
[[ -f "$STOCK_DIR/scripts/run_as1455_backtest_dashboard.sh" ]] \
  || fail "dashboard launcher is missing"
[[ -f "$PORTAL_FILE" ]] || fail "portal is not deployed: $PORTAL_FILE"
grep -q 'external_redirect' "$BAZI_DIR/frontend/src/pages/LoginPage.vue" \
  || fail "bazi branch is missing external login redirect support; pull the latest branch"
grep -q 'server.baseUrlPath' "$STOCK_DIR/scripts/run_as1455_backtest_dashboard.sh" \
  || fail "stock branch is missing Streamlit baseUrlPath support; pull the latest branch"
check_branch "$BAZI_DIR" "${EXPECTED_BAZI_BRANCH:-agent/mobile-ui-deterministic-chat}"
check_branch "$STOCK_DIR" "${EXPECTED_STOCK_BRANCH:-agent/ch17-as1455-clean}"
resolve_active_nginx_site
validate_auth_backend

install_dashboard_dependency

BACKUP_DIR="$(mktemp -d)"
run_root cp -a "$PORTAL_FILE" "$BACKUP_DIR/portal.html"
run_root cp -a "$NGINX_ACTIVE_SITE" "$BACKUP_DIR/nginx-active.conf"
if [[ -d "$WEB_ROOT/bazi" ]]; then
  BAZI_WEB_EXISTED=1
  run_root mkdir -p "$BACKUP_DIR/bazi-web"
  run_root cp -a "$WEB_ROOT/bazi/." "$BACKUP_DIR/bazi-web/"
fi
if run_root systemctl is-active --quiet "$STOCK_SERVICE.service"; then
  SERVICE_WAS_ACTIVE=1
fi
if run_root systemctl is-enabled --quiet "$STOCK_SERVICE.service"; then
  SERVICE_WAS_ENABLED=1
fi
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
wait_for_status "portal" "http://127.0.0.1:$PUBLIC_PORT/" '^200$'
wait_for_status "bazi login page" "http://127.0.0.1:$PUBLIC_PORT/bazi/login" '^200$'
validate_gateway_route
grep -q "href=\"/$STOCK_BASE_PATH/\"" "$PORTAL_FILE" \
  || fail "portal card validation failed"

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
