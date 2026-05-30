#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"
DEFAULT_CONFIG_FILE="$REPO_ROOT/lifetrace/config/default_config.yaml"
if [ -z "${LIFETRACE_DATA_DIR:-}" ]; then
  LIFETRACE_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/BrightToDo"
fi
export LIFETRACE_DATA_DIR
USER_CONFIG_DIR="$LIFETRACE_DATA_DIR/config"
CONFIG_FILE="$USER_CONFIG_DIR/config.yaml"
USER_DEFAULT_CONFIG_FILE="$USER_CONFIG_DIR/default_config.yaml"
SKIP_INSTALL=0
INSTALL_ONLY=0
STARTUP_TIMEOUT=180

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --install-only)
      INSTALL_ONLY=1
      shift
      ;;
    --timeout)
      STARTUP_TIMEOUT="$2"
      shift 2
      ;;
    --help|-h)
      cat <<'EOF'
Usage: scripts/start_dev.sh [options]

Options:
  --skip-install   Skip dependency sync/install.
  --install-only   Check and install dependencies, then exit.
  --timeout SEC    Startup timeout in seconds. Default: 180.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

step() {
  printf "\n==> %s\n" "$1"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_node() {
  if ! need_cmd node; then
    echo "Node.js 20+ is required. Install Node.js LTS and rerun this script." >&2
    exit 1
  fi
  local major
  major="$(node --version | sed 's/^v//' | cut -d. -f1)"
  if [ "$major" -lt 20 ]; then
    echo "Node.js 20+ is required. Current version: $(node --version)" >&2
    exit 1
  fi
}

ensure_uv() {
  if need_cmd uv; then
    return
  fi
  step "Installing uv"
  if need_cmd curl; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif need_cmd wget; then
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    echo "curl or wget is required to install uv." >&2
    exit 1
  fi
  export PATH="$HOME/.local/bin:$PATH"
  if ! need_cmd uv; then
    echo "uv was installed but is not on PATH. Reopen the terminal and rerun this script." >&2
    exit 1
  fi
}

ensure_pnpm() {
  if need_cmd pnpm; then
    return
  fi
  step "Installing pnpm"
  if need_cmd corepack && corepack enable && corepack prepare pnpm@latest --activate; then
    need_cmd pnpm && return
  fi
  if need_cmd npm && npm install -g pnpm; then
    need_cmd pnpm && return
  fi
  echo "pnpm is required. Install pnpm and rerun this script." >&2
  exit 1
}

http_get() {
  local url="$1"
  if need_cmd curl; then
    curl -fsS "$url"
    return $?
  fi
  if need_cmd wget; then
    wget -qO- "$url"
    return $?
  fi
  return 1
}

ensure_http_client() {
  if need_cmd curl || need_cmd wget; then
    return
  fi
  echo "curl or wget is required for startup health checks." >&2
  exit 1
}

ensure_config() {
  mkdir -p "$USER_CONFIG_DIR"
  if [ ! -f "$USER_DEFAULT_CONFIG_FILE" ] && [ -f "$DEFAULT_CONFIG_FILE" ]; then
    cp "$DEFAULT_CONFIG_FILE" "$USER_DEFAULT_CONFIG_FILE"
  fi
  if [ ! -f "$CONFIG_FILE" ] && [ -f "$DEFAULT_CONFIG_FILE" ]; then
    step "Creating user config.yaml from default_config.yaml"
    cp "$DEFAULT_CONFIG_FILE" "$CONFIG_FILE"
  fi
}

sync_dependencies() {
  step "Checking backend dependencies"
  cd "$REPO_ROOT"
  uv python install 3.12
  uv sync

  step "Checking frontend dependencies"
  cd "$FRONTEND_DIR"
  pnpm install
}

find_backend_port() {
  local port
  for port in $(seq 8001 8100); do
    if http_get "http://127.0.0.1:$port/health" 2>/dev/null | grep -q '"app":"lifetrace"'; then
      echo "$port"
      return 0
    fi
  done
  return 1
}

find_frontend_port() {
  local port
  for port in $(seq 3001 3100); do
    if http_get "http://127.0.0.1:$port" >/dev/null 2>&1; then
      echo "$port"
      return 0
    fi
  done
  return 1
}

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "Frontend directory not found: $FRONTEND_DIR" >&2
  exit 1
fi

step "BrightToDo environment check"
echo "Data dir: $LIFETRACE_DATA_DIR"
echo "Config:   $CONFIG_FILE"
ensure_node
ensure_uv
ensure_pnpm
ensure_http_client
ensure_config

if [ "$SKIP_INSTALL" -eq 0 ]; then
  sync_dependencies
else
  echo "Skipping dependency install because --skip-install was set."
fi

if [ "$INSTALL_ONLY" -eq 1 ]; then
  echo "Environment is ready."
  exit 0
fi

PYTHON_EXE="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PYTHON_EXE" ]; then
  echo "Backend virtualenv is missing. Rerun without --skip-install." >&2
  exit 1
fi

cleanup() {
  echo
  echo "Stopping BrightToDo services..."
  if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

step "Starting backend"
cd "$REPO_ROOT"
"$PYTHON_EXE" -m lifetrace.server &
BACKEND_PID=$!

backend_port=""
frontend_port=""
deadline=$((SECONDS + STARTUP_TIMEOUT))

while [ "$SECONDS" -lt "$deadline" ]; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo "Backend exited early." >&2
    exit 1
  fi
  if [ -z "$backend_port" ]; then
    backend_port="$(find_backend_port || true)"
  fi
  if [ -n "$backend_port" ]; then
    break
  fi
  sleep 2
done

if [ -z "$backend_port" ]; then
  echo "Timed out waiting for BrightToDo backend to start." >&2
  exit 1
fi

step "Starting frontend"
cd "$FRONTEND_DIR"
pnpm dev &
FRONTEND_PID=$!

while [ "$SECONDS" -lt "$deadline" ]; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo "Backend exited early." >&2
    exit 1
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "Frontend exited early." >&2
    exit 1
  fi
  if [ -z "$frontend_port" ]; then
    frontend_port="$(find_frontend_port || true)"
  fi
  if [ -n "$frontend_port" ]; then
    break
  fi
  sleep 2
done

if [ -z "$frontend_port" ]; then
  echo "Timed out waiting for BrightToDo frontend to start." >&2
  exit 1
fi

echo
echo "BrightToDo is running."
echo "Frontend: http://localhost:$frontend_port"
echo "Backend:  http://127.0.0.1:$backend_port"
echo
echo "Press Ctrl+C to stop both services."

wait
