#!/usr/bin/env bash
# stop.sh — Bash 版一键停止
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$PROJECT_ROOT/.runtime"
FORCE="${FORCE:-0}"

process_start_id() {
    local process_id="$1"
    if [ -r "/proc/$process_id/stat" ]; then
        awk '{print $22}' "/proc/$process_id/stat"
    else
        ps -p "$process_id" -o lstart= | sed 's/^[[:space:]]*//'
    fi
}

stop_one() {
    local name="$1" pid_file="$2" start_file="$3" marker="$4"
    if [ ! -f "$pid_file" ]; then
        echo "[skip] $name 未运行"
        return
    fi
    local pid
    pid="$(cat "$pid_file")"
    if ! [[ "$pid" =~ ^[0-9]+$ ]] || [ ! -f "$start_file" ]; then
        echo "[refuse] $name 跟踪文件无效；不终止任何进程"
        rm -f "$pid_file" "$start_file"
        return
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "[skip] $name PID $pid 不存在"
        rm -f "$pid_file" "$start_file"
        return
    fi
    local expected_start actual_start command_line
    expected_start="$(cat "$start_file")"
    actual_start="$(process_start_id "$pid")"
    command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [ "$expected_start" != "$actual_start" ] || [[ "$command_line" != *"$marker"* ]]; then
        echo "[refuse] $name PID $pid 身份不匹配；可能已被复用，不会终止"
        rm -f "$pid_file" "$start_file"
        return
    fi
    echo "[stop] $name pid=$pid ..."
    if [ "$FORCE" = "1" ]; then
        kill -9 "$pid" 2>/dev/null || true
        echo "[killed] $name (force)"
    else
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 10); do
            sleep 0.5
            if ! kill -0 "$pid" 2>/dev/null; then
                echo "[stopped] $name 优雅退出"
            rm -f "$pid_file" "$start_file"
            return
            fi
        done
        echo "[warn] $name 5s 内未响应,强杀"
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file" "$start_file"
}

stop_one backend "$RUNTIME_DIR/backend.pid" "$RUNTIME_DIR/backend.start" "app.main:app"
stop_one frontend "$RUNTIME_DIR/frontend.pid" "$RUNTIME_DIR/frontend.start" "vite"

echo "[done] 停止完成"
