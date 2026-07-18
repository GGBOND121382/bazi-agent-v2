#!/usr/bin/env bash
set -Eeuo pipefail

PUBLIC_PORT="${PUBLIC_PORT:-8000}"
ZHONGYI_PORT="${ZHONGYI_PORT:-8100}"
BAZI_API_PORT="${BAZI_API_PORT:-8101}"
APP_USER="${APP_USER:-${SUDO_USER:-$(id -un)}}"
BAZI_SERVICE="${BAZI_SERVICE:-bazi-agent-v2}"
ZHONGYI_SERVICE="${ZHONGYI_SERVICE:-zhongyi-diag}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BAZI_DIR="$SCRIPT_DIR"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
ZHONGYI_DIR="${ZHONGYI_DIR:-$APP_HOME/zhongyi-diag}"
BAZI_VENV="$BAZI_DIR/.venv"
BAZI_ENV_FILE="/etc/${BAZI_SERVICE}.env"
BAZI_UNIT_FILE="/etc/systemd/system/${BAZI_SERVICE}.service"
NGINX_SITE_NAME="dual-agents-8000"
NGINX_SITE_AVAILABLE="/etc/nginx/sites-available/$NGINX_SITE_NAME"
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/$NGINX_SITE_NAME"
WEB_ROOT="/var/www/dual-agents"

SECRET_TEMP=""
CONFIG_TEMP=""
DOWNLOAD_TEMP=""
GENERATED_ADMIN_PASSWORD=""
NPM_BIN=""

log() {
  printf '[dual-deploy] %s\n' "$*"
}

fail() {
  printf '[dual-deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  [[ -z "$SECRET_TEMP" || ! -f "$SECRET_TEMP" ]] || rm -f -- "$SECRET_TEMP"
  [[ -z "$CONFIG_TEMP" || ! -f "$CONFIG_TEMP" ]] || rm -f -- "$CONFIG_TEMP"
  if [[ -n "$DOWNLOAD_TEMP" && -d "$DOWNLOAD_TEMP" ]]; then
    rm -rf -- "$DOWNLOAD_TEMP"
  fi
}

on_error() {
  local code=$?
  printf '[dual-deploy] Deployment failed with exit code %s.\n' "$code" >&2
  if command -v systemctl >/dev/null 2>&1; then
    run_root systemctl status "$BAZI_SERVICE.service" --no-pager 2>/dev/null || true
    run_root systemctl status "$ZHONGYI_SERVICE.service" --no-pager 2>/dev/null || true
    run_root systemctl status nginx.service --no-pager 2>/dev/null || true
  fi
  exit "$code"
}

trap cleanup EXIT
trap on_error ERR

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
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "$name must be numeric"
  (( value >= 1 && value <= 65535 )) || fail "$name must be between 1 and 65535"
}

validate_path() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] \
    || fail "$name contains unsupported characters: $value"
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-45}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null 2>&1; then
      log "$name is healthy: $url"
      return 0
    fi
    sleep 1
  done
  fail "$name did not become healthy: $url"
}

ensure_node() {
  local major=0
  local architecture
  local node_arch
  local checksum_file
  local archive
  local expected

  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    major="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
  fi
  if [[ "$major" =~ ^[0-9]+$ ]] && (( major >= 18 )); then
    NPM_BIN="$(command -v npm)"
    log "Using Node.js $(node --version)"
    return 0
  fi

  architecture="$(uname -m)"
  case "$architecture" in
    x86_64) node_arch="x64" ;;
    aarch64|arm64) node_arch="arm64" ;;
    *) fail "Unsupported CPU architecture for Node.js: $architecture" ;;
  esac

  log "Installing the latest Node.js 22 release"
  DOWNLOAD_TEMP="$(mktemp -d)"
  checksum_file="$DOWNLOAD_TEMP/SHASUMS256.txt"
  curl --fail --silent --show-error --location \
    https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt -o "$checksum_file"
  archive="$(awk -v suffix="linux-${node_arch}.tar.xz" '$2 ~ suffix "$" {print $2; exit}' "$checksum_file")"
  [[ -n "$archive" ]] || fail "Could not resolve a Node.js archive for $node_arch"
  curl --fail --silent --show-error --location \
    "https://nodejs.org/dist/latest-v22.x/$archive" -o "$DOWNLOAD_TEMP/$archive"
  expected="$(awk -v file="$archive" '$2 == file {print $1}' "$checksum_file")"
  [[ -n "$expected" ]] || fail "Node.js checksum is missing"
  printf '%s  %s\n' "$expected" "$DOWNLOAD_TEMP/$archive" | sha256sum --check --status \
    || fail "Node.js archive checksum verification failed"

  run_root install -d -m 755 /opt/nodejs
  run_root tar -xJf "$DOWNLOAD_TEMP/$archive" -C /opt/nodejs --strip-components=1
  run_root ln -sfn /opt/nodejs/bin/node /usr/local/bin/node
  run_root ln -sfn /opt/nodejs/bin/npm /usr/local/bin/npm
  run_root ln -sfn /opt/nodejs/bin/npx /usr/local/bin/npx
  NPM_BIN=/usr/local/bin/npm
  log "Installed Node.js $(/usr/local/bin/node --version)"
}

ensure_uv() {
  local installer
  if [[ -x /usr/local/bin/uv ]]; then
    log "Using uv $(/usr/local/bin/uv --version)"
    return 0
  fi
  log "Installing uv for managed Python 3.12"
  installer="$(mktemp)"
  curl --fail --silent --show-error --location \
    https://astral.sh/uv/0.11.29/install.sh -o "$installer"
  run_root env UV_UNMANAGED_INSTALL=/usr/local/bin UV_NO_MODIFY_PATH=1 sh "$installer"
  rm -f -- "$installer"
}

create_bazi_config() {
  local admin_password
  local demo_password
  local line

  if [[ -s "$BAZI_DIR/config.local.env" ]]; then
    log "Using existing bazi config.local.env"
    return 0
  fi

  admin_password="$(openssl rand -hex 16)"
  demo_password="$(openssl rand -hex 16)"
  CONFIG_TEMP="$(mktemp)"
  chmod 600 "$CONFIG_TEMP"
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      INITIAL_ADMIN_PASSWORD=*) printf 'INITIAL_ADMIN_PASSWORD=%s\n' "$admin_password" ;;
      DEFAULT_USER_PASSWORD=*) printf 'DEFAULT_USER_PASSWORD=%s\n' "$demo_password" ;;
      INITIAL_DEMO_PASSWORD=*) printf 'INITIAL_DEMO_PASSWORD=%s\n' "$demo_password" ;;
      *) printf '%s\n' "$line" ;;
    esac
  done < "$BAZI_DIR/config.local.env.example" > "$CONFIG_TEMP"

  run_root install -o "$APP_USER" -g "$(id -gn "$APP_USER")" -m 600 \
    "$CONFIG_TEMP" "$BAZI_DIR/config.local.env"
  rm -f -- "$CONFIG_TEMP"
  CONFIG_TEMP=""
  GENERATED_ADMIN_PASSWORD="$admin_password"
  unset admin_password demo_password
  log "Created bazi config.local.env with generated passwords"
}

install_bazi_secret() {
  local api_key
  api_key="$(tr -d '\r\n' < "$ZHONGYI_DIR/deepseek-apikey")"
  [[ -n "$api_key" ]] || fail "$ZHONGYI_DIR/deepseek-apikey is empty"
  [[ "$api_key" =~ ^[A-Za-z0-9._-]+$ ]] || fail "DeepSeek API key contains unsupported characters"

  SECRET_TEMP="$(mktemp)"
  chmod 600 "$SECRET_TEMP"
  printf 'DEEPSEEK_API_KEY=%s\n' "$api_key" > "$SECRET_TEMP"
  run_root install -o root -g root -m 600 "$SECRET_TEMP" "$BAZI_ENV_FILE"
  rm -f -- "$SECRET_TEMP"
  SECRET_TEMP=""
  unset api_key
}

install_bazi_backend() {
  if [[ ! -x "$BAZI_VENV/bin/python" ]] \
    || ! "$BAZI_VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    log "Creating bazi Python 3.12 virtual environment"
    if [[ -e "$BAZI_VENV" ]]; then
      run_as_app /usr/local/bin/uv venv --clear --python 3.12 "$BAZI_VENV"
    else
      run_as_app /usr/local/bin/uv venv --python 3.12 "$BAZI_VENV"
    fi
  fi
  log "Installing bazi backend dependencies"
  run_as_app /usr/local/bin/uv pip install --python "$BAZI_VENV/bin/python" \
    --editable "$BAZI_DIR/backend"
  run_root install -d -o "$APP_USER" -g "$(id -gn "$APP_USER")" -m 700 "$BAZI_DIR/runtime"
}

build_bazi_frontend() {
  log "Installing and building bazi frontend"
  run_as_app env npm_config_audit=false npm_config_fund=false \
    "$NPM_BIN" --prefix "$BAZI_DIR/frontend" ci
  run_as_app env VITE_BASE_PATH=/bazi/ \
    "$NPM_BIN" --prefix "$BAZI_DIR/frontend" run build

  run_root install -d -o root -g root -m 755 "$WEB_ROOT/bazi"
  run_root cp -a "$BAZI_DIR/frontend/dist/." "$WEB_ROOT/bazi/"
  run_root chmod -R a+rX "$WEB_ROOT/bazi"
}

install_bazi_service() {
  log "Installing systemd service: $BAZI_SERVICE"
  run_root tee "$BAZI_UNIT_FILE" >/dev/null <<EOF
[Unit]
Description=Bazi Agent v2 API
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$(id -gn "$APP_USER")
WorkingDirectory=$BAZI_DIR/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$BAZI_ENV_FILE
ExecStart="$BAZI_VENV/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port $BAZI_API_PORT --workers 1
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
  run_root systemctl enable --now "$BAZI_SERVICE.service"
  run_root systemctl restart "$BAZI_SERVICE.service"
  wait_for_url "bazi backend" "http://127.0.0.1:$BAZI_API_PORT/api/v1/health"
}

move_zhongyi_service() {
  log "Moving $ZHONGYI_SERVICE from public port $PUBLIC_PORT to 127.0.0.1:$ZHONGYI_PORT"
  run_as_app env \
    APP_USER="$APP_USER" \
    SERVICE_NAME="$ZHONGYI_SERVICE" \
    BIND_HOST=127.0.0.1 \
    PORT="$ZHONGYI_PORT" \
    SKIP_APT=1 \
    bash "$ZHONGYI_DIR/deploy.sh"
  wait_for_url "zhongyi backend" "http://127.0.0.1:$ZHONGYI_PORT/"
}

install_portal() {
  run_root install -d -o root -g root -m 755 "$WEB_ROOT"
  run_root tee "$WEB_ROOT/index.html" >/dev/null <<'EOF'
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>智能体服务入口</title>
  <style>
    *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f1ea;color:#24231f;font-family:system-ui,"PingFang SC",sans-serif}.wrap{width:min(760px,92vw)}h1{font-size:clamp(28px,5vw,46px);margin:0 0 12px}p{color:#666;margin:0 0 30px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}.card{display:block;padding:26px;border-radius:18px;background:#fff;color:inherit;text-decoration:none;box-shadow:0 10px 35px #302b2015;border:1px solid #ddd7ca;transition:.18s}.card:hover{transform:translateY(-3px);box-shadow:0 15px 40px #302b2025}.card strong{display:block;font-size:22px;margin-bottom:9px}.card span{color:#706b61;line-height:1.6}
  </style>
</head>
<body><main class="wrap"><h1>智能体服务入口</h1><p>请选择要访问的服务</p><section class="grid"><a class="card" href="/bazi/"><strong>八字命理智能体</strong><span>排盘、结构化分析、报告与问答</span></a><a class="card" href="/zhongyi/"><strong>中医问诊智能体</strong><span>多轮问诊与结构化诊断报告</span></a></section></main></body>
</html>
EOF
  run_root chmod 644 "$WEB_ROOT/index.html"
}

install_nginx_site() {
  log "Installing Nginx gateway on port $PUBLIC_PORT"
  run_root tee "$NGINX_SITE_AVAILABLE" >/dev/null <<EOF
server {
    listen $PUBLIC_PORT default_server;
    listen [::]:$PUBLIC_PORT default_server;
    server_name _;
    root $WEB_ROOT;
    client_max_body_size 10m;

    location = / {
        try_files /index.html =404;
    }

    location = /bazi {
        return 301 /bazi/;
    }

    location ^~ /bazi/api/ {
        proxy_pass http://127.0.0.1:$BAZI_API_PORT/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Prefix /bazi;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 650s;
        proxy_send_timeout 650s;
    }

    location ^~ /bazi/ {
        try_files \$uri \$uri/ /bazi/index.html;
    }

    location = /zhongyi {
        return 301 /zhongyi/;
    }

    location ^~ /zhongyi/ {
        proxy_pass http://127.0.0.1:$ZHONGYI_PORT/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 650s;
        proxy_send_timeout 650s;
    }

    location ^~ /api/ {
        proxy_pass http://127.0.0.1:$ZHONGYI_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 650s;
        proxy_send_timeout 650s;
    }

    location ^~ /static/ {
        proxy_pass http://127.0.0.1:$ZHONGYI_PORT;
        proxy_set_header Host \$host;
    }

    location ^~ /report/ {
        proxy_pass http://127.0.0.1:$ZHONGYI_PORT;
        proxy_set_header Host \$host;
    }
}
EOF

  run_root ln -sfn "$NGINX_SITE_AVAILABLE" "$NGINX_SITE_ENABLED"
  run_root nginx -t
  run_root systemctl enable --now nginx.service
  run_root systemctl restart nginx.service
}

validate_port PUBLIC_PORT "$PUBLIC_PORT"
validate_port ZHONGYI_PORT "$ZHONGYI_PORT"
validate_port BAZI_API_PORT "$BAZI_API_PORT"
[[ "$PUBLIC_PORT" != "$ZHONGYI_PORT" && "$PUBLIC_PORT" != "$BAZI_API_PORT" \
   && "$ZHONGYI_PORT" != "$BAZI_API_PORT" ]] || fail "All three ports must be different"
[[ "$BAZI_SERVICE" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "Invalid BAZI_SERVICE"
[[ "$ZHONGYI_SERVICE" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "Invalid ZHONGYI_SERVICE"
[[ -n "$APP_HOME" ]] || fail "Could not resolve home directory for $APP_USER"
validate_path BAZI_DIR "$BAZI_DIR"
validate_path ZHONGYI_DIR "$ZHONGYI_DIR"

command -v sudo >/dev/null 2>&1 || [[ "$EUID" -eq 0 ]] || fail "sudo is required"
id "$APP_USER" >/dev/null 2>&1 || fail "Application user does not exist: $APP_USER"
[[ "$EUID" -ne 0 || "$(id -un)" == "$APP_USER" ]] \
  || command -v runuser >/dev/null 2>&1 || fail "runuser is required"

[[ -r /etc/os-release ]] || fail "Cannot identify the operating system"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || fail "This script supports Ubuntu only"
command -v systemctl >/dev/null 2>&1 || fail "systemd is required"

[[ -f "$BAZI_DIR/backend/pyproject.toml" ]] || fail "Run this script from the bazi-agent-v2 repository"
[[ -f "$BAZI_DIR/frontend/package-lock.json" ]] || fail "Bazi frontend package-lock.json is missing"
[[ -f "$BAZI_DIR/config.local.env.example" ]] || fail "Bazi config template is missing"
[[ -f "$BAZI_DIR/data/bazi_rag_dataset_v2_1/import/sqlite/bazi_rag.sqlite" ]] \
  || fail "Bazi RAG SQLite dataset is missing"
[[ -x "$ZHONGYI_DIR/deploy.sh" || -f "$ZHONGYI_DIR/deploy.sh" ]] \
  || fail "Existing zhongyi deployment not found at $ZHONGYI_DIR"
[[ -s "$ZHONGYI_DIR/deepseek-apikey" ]] \
  || fail "Existing DeepSeek key not found at $ZHONGYI_DIR/deepseek-apikey"

log "Installing Ubuntu packages"
run_root env DEBIAN_FRONTEND=noninteractive apt-get update
run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl git nginx openssl xz-utils build-essential

ensure_node
ensure_uv
create_bazi_config
install_bazi_secret
install_bazi_backend
build_bazi_frontend
install_bazi_service
move_zhongyi_service
install_portal
install_nginx_site

wait_for_url "gateway" "http://127.0.0.1:$PUBLIC_PORT/"
wait_for_url "bazi frontend" "http://127.0.0.1:$PUBLIC_PORT/bazi/"
wait_for_url "bazi API through gateway" "http://127.0.0.1:$PUBLIC_PORT/bazi/api/v1/health"
wait_for_url "zhongyi frontend" "http://127.0.0.1:$PUBLIC_PORT/zhongyi/"

if command -v ufw >/dev/null 2>&1 && run_root ufw status | grep -q '^Status: active'; then
  run_root ufw allow "$PUBLIC_PORT/tcp"
fi

trap - ERR
log "Dual-service deployment succeeded"
printf '\nAccess URLs:\n'
printf '  Portal:   http://<server-ip>:%s/\n' "$PUBLIC_PORT"
printf '  Bazi:     http://<server-ip>:%s/bazi/\n' "$PUBLIC_PORT"
printf '  Zhongyi:  http://<server-ip>:%s/zhongyi/\n' "$PUBLIC_PORT"
printf '\nService status:\n'
printf '  sudo systemctl status %s %s nginx\n' "$BAZI_SERVICE" "$ZHONGYI_SERVICE"
if [[ -n "$GENERATED_ADMIN_PASSWORD" ]]; then
  printf '\nBazi initial administrator:\n'
  printf '  Username: admin\n'
  printf '  Password: %s\n' "$GENERATED_ADMIN_PASSWORD"
  printf '  Save this password now and change it after the first login.\n'
fi
printf '\nProduction note: configure HTTPS before entering real personal or medical data.\n'
