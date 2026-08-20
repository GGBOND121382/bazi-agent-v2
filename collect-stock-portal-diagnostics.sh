#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APP_USER="${APP_USER:-${SUDO_USER:-$(id -un)}}"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
BAZI_DIR="${BAZI_DIR:-$APP_HOME/bazi-agent-v2}"
STOCK_DIR="${STOCK_DIR:-$APP_HOME/stock_realtime_v021_full}"
PUBLIC_PORT="${PUBLIC_PORT:-8000}"
BAZI_API_PORT="${BAZI_API_PORT:-8101}"
STOCK_PORT="${STOCK_PORT:-8501}"
PUBLIC_HOST="${PUBLIC_HOST:-}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_ROOT="${OUT_ROOT:-$APP_HOME/as1455_portal_diag_$STAMP}"
ARCHIVE="${ARCHIVE:-$OUT_ROOT.tar.gz}"

mkdir -p "$OUT_ROOT"

log() {
  printf '[diag] %s\n' "$*"
}

capture() {
  local name="$1"
  shift
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n\n'
    set +e
    "$@"
    local rc=$?
    set -e
    printf '\n[exit_code]=%s\n' "$rc"
  } >"$OUT_ROOT/$name" 2>&1
}

capture_shell() {
  local name="$1"
  local command="$2"
  {
    printf '$ %s\n\n' "$command"
    set +e
    bash -lc "$command"
    local rc=$?
    set -e
    printf '\n[exit_code]=%s\n' "$rc"
  } >"$OUT_ROOT/$name" 2>&1
}

redact_file() {
  local source="$1"
  local target="$2"
  if [[ ! -f "$source" ]]; then
    printf 'missing: %s\n' "$source" >"$target"
    return 0
  fi
  sed -E \
    -e 's/^([A-Za-z0-9_]*(TOKEN|PASSWORD|SECRET|API_KEY|PRIVATE_KEY)[A-Za-z0-9_]*)=.*/\1=<redacted>/I' \
    -e 's/(Authorization:[[:space:]]*)([^[:space:]]+)/\1<redacted>/Ig' \
    "$source" >"$target"
}

http_probe() {
  local name="$1"
  local connect_port="$2"
  local host_header="$3"
  local path="$4"
  local output="$OUT_ROOT/http_${name}.txt"
  local body="$OUT_ROOT/http_${name}.body"
  {
    printf 'connect=http://127.0.0.1:%s%s\n' "$connect_port" "$path"
    printf 'Host: %s\n\n' "$host_header"
    set +e
    curl --noproxy '*' --silent --show-error --max-time 12 \
      --dump-header - \
      --output "$body" \
      --header "Host: $host_header" \
      "http://127.0.0.1:$connect_port$path"
    local rc=$?
    set -e
    printf '\n[curl_exit_code]=%s\n' "$rc"
    printf '\n--- body first 4096 bytes ---\n'
    head -c 4096 "$body" 2>/dev/null || true
    printf '\n'
  } >"$output" 2>&1
  rm -f "$body"
}

log "collecting system metadata"
{
  printf 'collected_at=%s\n' "$(date -Is)"
  printf 'app_user=%s\n' "$APP_USER"
  printf 'app_home=%s\n' "$APP_HOME"
  printf 'bazi_dir=%s\n' "$BAZI_DIR"
  printf 'stock_dir=%s\n' "$STOCK_DIR"
  printf 'public_port=%s\n' "$PUBLIC_PORT"
  printf 'bazi_api_port=%s\n' "$BAZI_API_PORT"
  printf 'stock_port=%s\n' "$STOCK_PORT"
  printf 'public_host=%s\n' "$PUBLIC_HOST"
  printf '\n'
  uname -a || true
  printf '\n'
  id || true
  printf '\n'
  hostnamectl 2>/dev/null || true
  printf '\nhostname -f: '
  hostname -f 2>/dev/null || true
  printf '\nhostname -I: '
  hostname -I 2>/dev/null || true
  printf '\n\n/etc/os-release:\n'
  cat /etc/os-release 2>/dev/null || true
} >"$OUT_ROOT/00_system.txt" 2>&1

capture_shell "01_ports_processes.txt" \
  "ss -ltnp; echo; ps -eo pid,ppid,user,group,lstart,args --sort=pid | grep -E '[n]ginx|[u]vicorn|[s]treamlit|[p]ython.*8101|[p]ython.*8501'"

capture_shell "02_nginx_version.txt" "nginx -V"
capture_shell "03_nginx_test.txt" "nginx -t"
capture_shell "04_nginx_dump.txt" "nginx -T"
capture_shell "05_nginx_tree.txt" \
  "find /etc/nginx -maxdepth 4 -printf '%M %u:%g %p -> %l\n' | sort"
capture_shell "06_nginx_systemd.txt" \
  "systemctl cat nginx.service; echo; systemctl status nginx.service --no-pager -l; echo; systemctl show nginx.service"
capture_shell "07_nginx_journal.txt" \
  "journalctl -u nginx.service -n 400 --no-pager -o short-iso"
capture_shell "08_nginx_logs.txt" \
  "for f in /var/log/nginx/access.log /var/log/nginx/error.log; do echo ====== \$f; tail -n 300 \$f 2>&1; done"

log "collecting Nginx master and listener ownership"
capture_shell "09_nginx_proc.txt" '
for pid in $(pgrep -x nginx 2>/dev/null || true); do
  echo "===== PID $pid ====="
  printf "cmdline: "; tr "\0" " " < /proc/$pid/cmdline 2>/dev/null; echo
  printf "exe: "; readlink -f /proc/$pid/exe 2>/dev/null || true
  printf "cwd: "; readlink -f /proc/$pid/cwd 2>/dev/null || true
  printf "root: "; readlink -f /proc/$pid/root 2>/dev/null || true
  printf "cgroup:\n"; cat /proc/$pid/cgroup 2>/dev/null || true
  printf "status:\n"; sed -n "1,40p" /proc/$pid/status 2>/dev/null || true
  printf "netns: "; readlink /proc/$pid/ns/net 2>/dev/null || true
  echo
done
printf "pid files:\n"
for f in /run/nginx.pid /var/run/nginx.pid; do
  echo "--- $f"; cat "$f" 2>/dev/null || true
done
printf "\nlistener owners:\n"
command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:8000 -sTCP:LISTEN || true
command -v fuser >/dev/null 2>&1 && fuser -v 8000/tcp || true
'

capture_shell "10_service_as1455.txt" \
  "systemctl cat as1455-dashboard.service; echo; systemctl status as1455-dashboard.service --no-pager -l; echo; systemctl show as1455-dashboard.service"
capture_shell "11_service_bazi.txt" \
  "systemctl cat bazi-agent-v2.service; echo; systemctl status bazi-agent-v2.service --no-pager -l; echo; systemctl show bazi-agent-v2.service"
capture_shell "12_service_journals.txt" \
  "journalctl -u as1455-dashboard.service -u bazi-agent-v2.service -n 400 --no-pager -o short-iso"

redact_file "/etc/as1455-dashboard.env" "$OUT_ROOT/13_as1455_dashboard_env_redacted.txt"
redact_file "/etc/bazi-agent-v2.env" "$OUT_ROOT/14_bazi_env_redacted.txt"

log "collecting repository state"
for repo_name in bazi stock; do
  if [[ "$repo_name" == "bazi" ]]; then
    repo="$BAZI_DIR"
  else
    repo="$STOCK_DIR"
  fi
  capture_shell "20_git_${repo_name}.txt" \
    "git -C '$repo' status -sb; echo; git -C '$repo' branch --show-current; git -C '$repo' rev-parse HEAD; echo; git -C '$repo' log -8 --oneline --decorate; echo; git -C '$repo' remote -v; echo; git -C '$repo' diff --stat; echo; git -C '$repo' diff"
done

capture_shell "21_relevant_files_hashes.txt" \
  "sha256sum \
    '$BAZI_DIR/deploy-stock-dashboard-to-portal.sh' \
    '$BAZI_DIR/collect-stock-portal-diagnostics.sh' \
    '$BAZI_DIR/scripts/as1455_portal_nginx.py' \
    '$BAZI_DIR/frontend/src/pages/LoginPage.vue' \
    '$STOCK_DIR/scripts/run_as1455_backtest_dashboard.sh' \
    '$STOCK_DIR/dashboard/as1455_backtest_dashboard.py' 2>&1"

for file in \
  "$BAZI_DIR/deploy-stock-dashboard-to-portal.sh" \
  "$BAZI_DIR/scripts/as1455_portal_nginx.py" \
  "$BAZI_DIR/frontend/src/pages/LoginPage.vue" \
  "$STOCK_DIR/scripts/run_as1455_backtest_dashboard.sh" \
  "/var/www/dual-agents/index.html"; do
  safe_name="$(printf '%s' "$file" | sed 's#^/##; s#[^A-Za-z0-9._-]#_#g')"
  if [[ -f "$file" ]]; then
    cp -a "$file" "$OUT_ROOT/file_$safe_name"
  else
    printf 'missing: %s\n' "$file" >"$OUT_ROOT/file_${safe_name}.missing"
  fi
done

log "extracting configured server names"
python3 - "$OUT_ROOT/04_nginx_dump.txt" "$OUT_ROOT/server_names.txt" <<'PY'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
result = ["127.0.0.1", "localhost"]
for match in re.finditer(r"(?m)^\s*server_name\s+([^;]+);", source):
    for value in match.group(1).split():
        if value in {"_", ""} or value.startswith("~") or "$" in value:
            continue
        value = value.strip()
        if value and value not in result:
            result.append(value)
Path(sys.argv[2]).write_text("\n".join(result) + "\n", encoding="utf-8")
PY
if [[ -n "$PUBLIC_HOST" ]] && ! grep -Fxq "$PUBLIC_HOST" "$OUT_ROOT/server_names.txt"; then
  printf '%s\n' "$PUBLIC_HOST" >>"$OUT_ROOT/server_names.txt"
fi

log "probing HTTP routes without following redirects"
probe_index=0
while IFS= read -r host; do
  [[ -n "$host" ]] || continue
  probe_index=$((probe_index + 1))
  safe_host="$(printf '%s' "$host" | sed 's#[^A-Za-z0-9._-]#_#g')"
  http_probe "${probe_index}_${safe_host}_portal_root" "$PUBLIC_PORT" "$host" "/"
  http_probe "${probe_index}_${safe_host}_bazi_login" "$PUBLIC_PORT" "$host" "/bazi/login"
  http_probe "${probe_index}_${safe_host}_stock_root" "$PUBLIC_PORT" "$host" "/stock/"
  http_probe "${probe_index}_${safe_host}_stock_health" "$PUBLIC_PORT" "$host" "/stock/_stcore/health"
done <"$OUT_ROOT/server_names.txt"

http_probe "direct_bazi_auth" "$BAZI_API_PORT" "127.0.0.1" "/api/v1/auth/me"
http_probe "direct_stock_root" "$STOCK_PORT" "127.0.0.1" "/stock/"
http_probe "direct_stock_health" "$STOCK_PORT" "127.0.0.1" "/stock/_stcore/health"

log "collecting routing and firewall context"
capture_shell "30_routes_firewall.txt" \
  "ip address; echo; ip route; echo; nft list ruleset 2>&1 || true; echo; iptables-save 2>&1 || true; echo; ufw status verbose 2>&1 || true"
capture_shell "31_hosts_resolver.txt" \
  "cat /etc/hosts; echo; cat /etc/resolv.conf; echo; getent hosts localhost; getent ahosts \$(hostname -f 2>/dev/null || hostname) 2>&1 || true"

cat >"$OUT_ROOT/README.txt" <<EOF
This archive was generated by collect-stock-portal-diagnostics.sh.
The script is read-only: it does not edit Nginx, reload services, or run deployment.
Potential secrets in known environment files were redacted.
Collected at: $(date -Is)
EOF

log "creating archive"
tar -C "$(dirname "$OUT_ROOT")" -czf "$ARCHIVE" "$(basename "$OUT_ROOT")"
sha256sum "$ARCHIVE" | tee "$ARCHIVE.sha256"

printf '\n[diag] complete\n'
printf '[diag] archive: %s\n' "$ARCHIVE"
printf '[diag] checksum: %s.sha256\n' "$ARCHIVE"
printf '[diag] upload the .tar.gz file to the chat; do not paste individual outputs.\n'
