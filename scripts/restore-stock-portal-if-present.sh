#!/usr/bin/env bash
set -Eeuo pipefail

PUBLIC_PORT="${PUBLIC_PORT:-8000}"
BAZI_API_PORT="${BAZI_API_PORT:-8101}"
STOCK_PORT="${STOCK_PORT:-8501}"
STOCK_BASE_PATH="${STOCK_BASE_PATH:-stock}"
STOCK_SERVICE="${STOCK_SERVICE:-as1455-dashboard}"
WEB_ROOT="${WEB_ROOT:-/var/www/dual-agents}"
NGINX_SITE_AVAILABLE="${NGINX_SITE_AVAILABLE:-/etc/nginx/sites-available/dual-agents-8000}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
NGINX_HELPER="$SCRIPT_DIR/as1455_portal_nginx.py"
PORTAL_FILE="$WEB_ROOT/index.html"

log() { printf '[stock-preserve] %s\n' "$*"; }
fail() { printf '[stock-preserve] ERROR: %s\n' "$*" >&2; exit 1; }

run_root() {
  if [[ "$EUID" -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

http_status() {
  curl --noproxy '*' --http1.1 --header 'Connection: close' \
    --silent --output /dev/null --write-out '%{http_code}' --max-time 10 "$1"
}

validate_port() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "$name must be numeric"
  (( value >= 1 && value <= 65535 )) || fail "$name must be between 1 and 65535"
}

validate_port PUBLIC_PORT "$PUBLIC_PORT"
validate_port BAZI_API_PORT "$BAZI_API_PORT"
validate_port STOCK_PORT "$STOCK_PORT"
[[ "$STOCK_BASE_PATH" =~ ^[A-Za-z0-9._-]+$ ]] || fail "invalid STOCK_BASE_PATH"
[[ "$STOCK_SERVICE" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "invalid STOCK_SERVICE"
[[ -f "$NGINX_HELPER" ]] || fail "missing Nginx helper: $NGINX_HELPER"

# Preserve the route whenever the dashboard unit is installed, even if it is
# temporarily stopped. Machines that never installed the dashboard stay dual-only.
if ! run_root systemctl cat "$STOCK_SERVICE.service" >/dev/null 2>&1; then
  log "$STOCK_SERVICE.service is not installed; stock portal preservation skipped"
  exit 0
fi

stock_active=0
if run_root systemctl is-active --quiet "$STOCK_SERVICE.service"; then
  stock_active=1
  health_url="http://127.0.0.1:$STOCK_PORT/$STOCK_BASE_PATH/_stcore/health"
  health_status=""
  for _ in $(seq 1 30); do
    health_status="$(http_status "$health_url" || true)"
    [[ "$health_status" == "200" ]] && break
    sleep 0.2
  done
  [[ "$health_status" == "200" ]] \
    || fail "installed stock service is active but unhealthy: HTTP ${health_status:-unknown} $health_url"
else
  log "$STOCK_SERVICE.service is installed but inactive; preserving gateway configuration without live health validation"
fi

[[ -f "$PORTAL_FILE" ]] || fail "portal is missing: $PORTAL_FILE"
[[ -f "$NGINX_SITE_AVAILABLE" ]] || fail "Nginx portal site is missing: $NGINX_SITE_AVAILABLE"

log "restoring /$STOCK_BASE_PATH/ portal card"
run_root env PORTAL_FILE="$PORTAL_FILE" STOCK_BASE_PATH="$STOCK_BASE_PATH" python3 - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["PORTAL_FILE"])
base = os.environ["STOCK_BASE_PATH"].strip("/")
html = path.read_text(encoding="utf-8")
card = (
    f'<a class="card" href="/{base}/"><strong>AS1455 策略看板</strong>'
    '<span>九模型历史回测、严格 OOS 与持仓分析</span></a>'
)
if f'href="/{base}/"' not in html:
    if "</section>" not in html:
        raise SystemExit("portal does not contain </section>")
    html = html.replace("</section>", card + "</section>", 1)
html = html.replace("width:min(760px,92vw)", "width:min(1080px,92vw)")
path.write_text(html, encoding="utf-8")
PY
run_root chmod 644 "$PORTAL_FILE"

log "restoring authenticated /$STOCK_BASE_PATH/ Nginx route"
run_root python3 "$NGINX_HELPER" patch \
  --file "$NGINX_SITE_AVAILABLE" \
  --port "$PUBLIC_PORT" \
  --web-root "$WEB_ROOT" \
  --bazi-port "$BAZI_API_PORT" \
  --stock-port "$STOCK_PORT" \
  --base "$STOCK_BASE_PATH"

run_root nginx -t
run_root systemctl reload nginx.service

readiness_url="http://127.0.0.1:$PUBLIC_PORT/_as1455_${STOCK_BASE_PATH}_gateway_ready"
readiness_status=""
for _ in $(seq 1 30); do
  readiness_status="$(http_status "$readiness_url" || true)"
  [[ "$readiness_status" == "204" ]] && break
  sleep 0.2
done
[[ "$readiness_status" == "204" ]] \
  || fail "restored Nginx generation did not become active"

grep -q "href=\"/$STOCK_BASE_PATH/\"" "$PORTAL_FILE" \
  || fail "stock portal card validation failed"

if [[ "$stock_active" == "1" ]]; then
  gateway_url="http://127.0.0.1:$PUBLIC_PORT/$STOCK_BASE_PATH/"
  gateway_status="$(http_status "$gateway_url" || true)"
  [[ "$gateway_status" == "200" || "$gateway_status" == "302" ]] \
    || fail "restored stock gateway returned HTTP $gateway_status: $gateway_url"
  log "stock portal preserved successfully (gateway HTTP $gateway_status)"
else
  log "stock portal configuration preserved; dashboard service remains inactive"
fi
