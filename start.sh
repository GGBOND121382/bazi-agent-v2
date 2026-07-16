#!/usr/bin/env bash
# start.sh — Bash 版一键启动 (Git Bash / WSL / macOS / Linux)
# 与 start.ps1 行为一致;优先使用 PowerShell 版本
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
RUNTIME_DIR="$PROJECT_ROOT/.runtime"
BACKEND_PID="$RUNTIME_DIR/backend.pid"
FRONTEND_PID="$RUNTIME_DIR/frontend.pid"
BACKEND_LOG="$RUNTIME_DIR/backend.log"
FRONTEND_LOG="$RUNTIME_DIR/frontend.log"
if [ -n "${PYTHON:-}" ]; then
    PYTHON="$PYTHON"
elif [[ "$(uname -s)" =~ ^(MINGW|MSYS|CYGWIN) ]] && command -v py >/dev/null 2>&1; then
    PYTHON=py
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    PYTHON=python
fi
BACKEND_START="$RUNTIME_DIR/backend.start"
FRONTEND_START="$RUNTIME_DIR/frontend.start"

mkdir -p "$RUNTIME_DIR"

# 已有进程检测
check_alive() {
    local pid_file="$1"
    [ -f "$pid_file" ] || return 1
    local pid
    pid="$(cat "$pid_file")"
    kill -0 "$pid" 2>/dev/null
}

if check_alive "$BACKEND_PID"; then
    echo "[error] 后端已运行 (pid: $(cat "$BACKEND_PID")). 先运行 ./stop.sh" >&2
    exit 1
fi
if check_alive "$FRONTEND_PID"; then
    echo "[error] 前端已运行 (pid: $(cat "$FRONTEND_PID")). 先运行 ./stop.sh" >&2
    exit 1
fi

# 端口占用检测 (使用 lsof 或 ss)
port_in_use() {
    local port="$1"
    if command -v lsof >/dev/null 2>&1; then
        lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    elif command -v ss >/dev/null 2>&1; then
        ss -ltn "sport = :$port" | tail -n +2 | grep -q LISTEN
    else
        netstat -ltn 2>/dev/null | grep -qE "[:.]$port[[:space:]]"
    fi
}
if port_in_use "$BACKEND_PORT"; then
    echo "[error] 端口 $BACKEND_PORT 已被占用" >&2
    exit 1
fi
if port_in_use "$FRONTEND_PORT"; then
    echo "[error] 端口 $FRONTEND_PORT 已被占用" >&2
    exit 1
fi

command -v "$PYTHON" >/dev/null 2>&1 || { echo "[error] 未找到 $PYTHON" >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "[error] 未找到 node" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "[error] 未找到 npm" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "[error] 未找到 curl" >&2; exit 1; }

process_start_id() {
    local process_id="$1"
    if [ -r "/proc/$process_id/stat" ]; then
        awk '{print $22}' "/proc/$process_id/stat"
    else
        ps -p "$process_id" -o lstart= | sed 's/^[[:space:]]*//'
    fi
}

rollback() {
    local code=$?
    if [ "$code" -ne 0 ]; then
        echo "[rollback] 启动失败，停止本次已启动的服务..." >&2
        FORCE=1 bash "$PROJECT_ROOT/stop.sh" >/dev/null 2>&1 || true
    fi
    exit "$code"
}
trap rollback EXIT

# 后端依赖
cd "$PROJECT_ROOT/backend"
if ! "$PYTHON" -c 'import fastapi, uvicorn, app' >/dev/null 2>&1; then
    if [ "${SKIP_INSTALL:-}" = "1" ]; then
        echo "[error] 后端依赖缺失，不能与 SKIP_INSTALL=1 同时使用" >&2
        exit 1
    fi
    echo "[setup] 安装后端依赖..."
    "$PYTHON" -m pip install -e '.[dev]' --quiet >>"$BACKEND_LOG" 2>&1 \
        || { echo "[error] 后端依赖安装失败,见 $BACKEND_LOG" >&2; exit 1; }
fi

# API key
KEY_FILE="$(cd "$PROJECT_ROOT/.." && pwd)/deepseek-apikey"
if [ -f "$KEY_FILE" ]; then
    DEEPSEEK_KEY="$(tr -d '\r\n' < "$KEY_FILE")"
    [ -n "$DEEPSEEK_KEY" ] || { echo "[error] DeepSeek key 文件为空" >&2; exit 1; }
    echo "[env] DeepSeek key 已安全注入后端子进程"
elif [ "${MOCK:-}" = "1" ]; then
    DEEPSEEK_KEY=""
else
    echo "[error] 未找到 $KEY_FILE；使用 MOCK=1 可只启动设计模式" >&2
    exit 1
fi

if [ "${MOCK:-}" != "1" ] && [ ! -f "$PROJECT_ROOT/data/bazi_rag_dataset_v2_1/import/sqlite/bazi_rag.sqlite" ]; then
    echo "[error] 正式 RAG SQLite 数据不存在" >&2
    exit 1
fi

# 启动后端
echo "[start] 后端 uvicorn (port $BACKEND_PORT)..."
DEEPSEEK_API_KEY="$DEEPSEEK_KEY" nohup "$PYTHON" -m uvicorn app.main:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" --log-level info \
    >>"$BACKEND_LOG" 2>&1 &
echo $! >"$BACKEND_PID"
process_start_id "$(cat "$BACKEND_PID")" >"$BACKEND_START"
unset DEEPSEEK_KEY

# 前端依赖
cd "$PROJECT_ROOT/frontend"
if [ ! -f node_modules/vite/bin/vite.js ]; then
    if [ "${SKIP_INSTALL:-}" = "1" ]; then
        echo "[error] 前端依赖缺失，不能与 SKIP_INSTALL=1 同时使用" >&2
        exit 1
    fi
    echo "[setup] 安装前端依赖..."
    npm install --prefer-offline --no-audit --no-fund --no-progress >>"$FRONTEND_LOG" 2>&1 \
        || { echo "[error] 前端依赖安装失败,见 $FRONTEND_LOG" >&2; exit 1; }
fi

echo "[start] 前端 vite dev (port $FRONTEND_PORT)..."
if [ "${MOCK:-}" = "1" ]; then
    VITE_USE_MOCKS=true VITE_API_TARGET="http://127.0.0.1:$BACKEND_PORT" \
        nohup node node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$FRONTEND_PORT" >>"$FRONTEND_LOG" 2>&1 &
else
    VITE_API_TARGET="http://127.0.0.1:$BACKEND_PORT" \
        nohup node node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$FRONTEND_PORT" >>"$FRONTEND_LOG" 2>&1 &
fi
echo $! >"$FRONTEND_PID"
process_start_id "$(cat "$FRONTEND_PID")" >"$FRONTEND_START"

# 健康检查
echo "[health] 等待服务就绪..."
for i in $(seq 1 20); do
    sleep 0.5
    if curl -sf "http://127.0.0.1:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1 \
        && curl -sf "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1 \
        && curl -sf "http://127.0.0.1:$FRONTEND_PORT/api/v1/health" >/dev/null 2>&1; then
        echo "[ok]    后端 http://127.0.0.1:$BACKEND_PORT (pid $(cat "$BACKEND_PID"))"
        echo "[ok]    前端 http://127.0.0.1:$FRONTEND_PORT (pid $(cat "$FRONTEND_PID"))"
        echo ""
        echo "停止:  ./stop.sh"
        echo "日志:  $BACKEND_LOG"
        echo "       $FRONTEND_LOG"
        trap - EXIT
        exit 0
    fi
done
echo "[error] 后端 10s 内未响应,见 $BACKEND_LOG" >&2
bash "$PROJECT_ROOT/stop.sh"
exit 1
