#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${LIFETRACE_REPO:-https://github.com/FreeU-group/FreeTodo.git}"
REF="${LIFETRACE_REF:-main}"
REPO_NAME="${REPO_URL##*/}"
REPO_NAME="${REPO_NAME%.git}"
TARGET_DIR="${LIFETRACE_DIR:-$REPO_NAME}"
MODE="${LIFETRACE_MODE:-tauri}"
VARIANT="${LIFETRACE_VARIANT:-web}"
FRONTEND_ACTION="${LIFETRACE_FRONTEND:-build}"
BACKEND_RUNTIME="${LIFETRACE_BACKEND:-script}"
RUN_AFTER_INSTALL="${LIFETRACE_RUN:-1}"

DIR_SET=0
if [ -n "${LIFETRACE_DIR:-}" ]; then
  DIR_SET=1
fi
FRONTEND_SET=0
if [ -n "${LIFETRACE_FRONTEND:-}" ]; then
  FRONTEND_SET=1
fi
VARIANT_SET=0
if [ -n "${LIFETRACE_VARIANT:-}" ]; then
  VARIANT_SET=1
fi
MODE_SET=0
if [ -n "${LIFETRACE_MODE:-}" ]; then
  MODE_SET=1
fi
BACKEND_SET=0
if [ -n "${LIFETRACE_BACKEND:-}" ]; then
  BACKEND_SET=1
fi

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Options:
  --ref, -r       Git branch or tag to clone
  --mode, -m      web | tauri | electron | island
  --variant       web | island
  --frontend      build | dev
  --backend       script | pyinstaller
  --repo          Git repo URL
  --dir           Target directory
  --run           1 to run after install, 0 to only install
  --help, -h      Show this help message

Env vars:
  LIFETRACE_REPO, LIFETRACE_REF, LIFETRACE_DIR
  LIFETRACE_MODE, LIFETRACE_VARIANT, LIFETRACE_FRONTEND, LIFETRACE_BACKEND, LIFETRACE_RUN

Defaults:
  mode=tauri, variant=web, frontend=build, backend=script, ref=main
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --ref|-r)
      if [ $# -lt 2 ]; then
        echo "Missing value for --ref." >&2
        exit 1
      fi
      REF="$2"
      shift 2
      ;;
    --mode|-m)
      if [ $# -lt 2 ]; then
        echo "Missing value for --mode." >&2
        exit 1
      fi
      MODE="$2"
      MODE_SET=1
      shift 2
      ;;
    --variant)
      if [ $# -lt 2 ]; then
        echo "Missing value for --variant." >&2
        exit 1
      fi
      VARIANT="$2"
      VARIANT_SET=1
      shift 2
      ;;
    --frontend)
      if [ $# -lt 2 ]; then
        echo "Missing value for --frontend." >&2
        exit 1
      fi
      FRONTEND_ACTION="$2"
      FRONTEND_SET=1
      shift 2
      ;;
    --backend)
      if [ $# -lt 2 ]; then
        echo "Missing value for --backend." >&2
        exit 1
      fi
      BACKEND_RUNTIME="$2"
      BACKEND_SET=1
      shift 2
      ;;
    --repo)
      if [ $# -lt 2 ]; then
        echo "Missing value for --repo." >&2
        exit 1
      fi
      REPO_URL="$2"
      REPO_NAME="${REPO_URL##*/}"
      REPO_NAME="${REPO_NAME%.git}"
      if [ "$DIR_SET" -eq 0 ]; then
        TARGET_DIR="$REPO_NAME"
      fi
      shift 2
      ;;
    --dir)
      if [ $# -lt 2 ]; then
        echo "Missing value for --dir." >&2
        exit 1
      fi
      TARGET_DIR="$2"
      DIR_SET=1
      shift 2
      ;;
    --run)
      if [ $# -lt 2 ]; then
        echo "Missing value for --run." >&2
        exit 1
      fi
      RUN_AFTER_INSTALL="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

prompt_choice() {
  local label="$1"
  local default="$2"
  shift 2
  local choices=("$@")
  if [ ! -t 0 ]; then
    echo "$default"
    return 0
  fi
  echo "$label" >&2
  local i=1
  for choice in "${choices[@]}"; do
    echo "  $i) $choice" >&2
    i=$((i + 1))
  done
  read -r -p "Select [default: $default]: " input
  if [ -z "${input}" ]; then
    echo "$default"
    return 0
  fi
  if [[ "$input" =~ ^[0-9]+$ ]]; then
    local index=$((input - 1))
    if [ "$index" -ge 0 ] && [ "$index" -lt "${#choices[@]}" ]; then
      echo "${choices[$index]}"
      return 0
    fi
  else
    for choice in "${choices[@]}"; do
      if [ "$choice" = "$input" ]; then
        echo "$choice"
        return 0
      fi
    done
  fi
  echo "Invalid choice. Using default: $default" >&2
  echo "$default"
}

if [ "$VARIANT_SET" -eq 0 ]; then
  VARIANT="$(prompt_choice "Select UI variant:" "web" "web" "island")"
fi
if [ "$BACKEND_SET" -eq 0 ]; then
  BACKEND_RUNTIME="$(prompt_choice "Select backend runtime:" "script" "script" "pyinstaller")"
fi
if [ "$MODE_SET" -eq 0 ]; then
  MODE="$(prompt_choice "Select app mode:" "tauri" "tauri" "electron" "web")"
fi

if [ "$MODE" = "island" ]; then
  MODE="tauri"
  VARIANT="island"
  VARIANT_SET=1
fi

if [ "$VARIANT" = "island" ] && [ "$MODE" = "web" ]; then
  echo "Variant 'island' is not supported in web mode. Switching mode to tauri."
  MODE="tauri"
fi

if [ "$MODE" = "web" ] && [ "$VARIANT" != "web" ]; then
  echo "Variant '$VARIANT' is not supported in web mode." >&2
  exit 1
fi

case "$MODE" in
  web|tauri|electron) ;;
  *)
    echo "Invalid mode: $MODE" >&2
    exit 1
    ;;
 esac

case "$VARIANT" in
  web|island) ;;
  *)
    echo "Invalid variant: $VARIANT" >&2
    exit 1
    ;;
esac

case "$FRONTEND_ACTION" in
  build|dev) ;;
  *)
    echo "Invalid frontend action: $FRONTEND_ACTION" >&2
    exit 1
    ;;
esac

case "$BACKEND_RUNTIME" in
  script|pyinstaller) ;;
  *)
    echo "Invalid backend runtime: $BACKEND_RUNTIME" >&2
    exit 1
    ;;
esac

if [ "$BACKEND_RUNTIME" = "pyinstaller" ] && [ "$FRONTEND_SET" -eq 0 ]; then
  FRONTEND_ACTION="build"
fi

if [ "$FRONTEND_ACTION" = "dev" ] && [ "$BACKEND_RUNTIME" = "pyinstaller" ]; then
  echo "backend=pyinstaller is only supported with frontend=build." >&2
  exit 1
fi

if [ "$MODE" = "tauri" ] && [ "$FRONTEND_ACTION" = "build" ] && [ "$VARIANT" = "island" ]; then
  echo "Island packaging is not supported yet. Switching variant to web for build."
  VARIANT="web"
fi

MISSING_DEPS=()
MISSING_HINTS=()

add_missing() {
  MISSING_DEPS+=("$1")
  MISSING_HINTS+=("$2")
}

OS_TYPE="$(uname -s)"

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

ensure_brew() {
  if command -v brew >/dev/null 2>&1; then
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required to install Homebrew." >&2
    return 1
  fi
  echo "Installing Homebrew..."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

install_packages() {
  if [ "$#" -eq 0 ]; then
    return 0
  fi
  if [ "$OS_TYPE" = "Darwin" ]; then
    ensure_brew || return 1
    brew install "$@"
    return $?
  fi
  if [ "$OS_TYPE" = "Linux" ]; then
    if command -v apt-get >/dev/null 2>&1; then
      as_root apt-get update
      as_root apt-get install -y "$@"
      return $?
    fi
    if command -v dnf >/dev/null 2>&1; then
      as_root dnf install -y "$@"
      return $?
    fi
    if command -v yum >/dev/null 2>&1; then
      as_root yum install -y "$@"
      return $?
    fi
    if command -v pacman >/dev/null 2>&1; then
      as_root pacman -Sy --noconfirm "$@"
      return $?
    fi
  fi
  echo "No supported package manager found to install: $*" >&2
  return 1
}

install_rustup() {
  if command -v cargo >/dev/null 2>&1; then
    return 0
  fi
  echo "Installing Rust (rustup)..."
  if command -v curl >/dev/null 2>&1; then
    curl -sSf https://sh.rustup.rs | sh -s -- -y
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://sh.rustup.rs | sh -s -- -y
  else
    return 1
  fi
  export PATH="$HOME/.cargo/bin:$PATH"
}

install_missing_deps() {
  if [ "${#MISSING_DEPS[@]}" -eq 0 ]; then
    return 0
  fi

  local packages=()
  local need_rustup=0
  local dep
  for dep in "${MISSING_DEPS[@]}"; do
    case "$dep" in
      python)
        if [ "$OS_TYPE" = "Darwin" ]; then
          packages+=("python@3.12")
        elif [ "$OS_TYPE" = "Linux" ]; then
          if command -v pacman >/dev/null 2>&1; then
            packages+=("python" "python-pip")
          else
            packages+=("python3" "python3-pip" "python3-venv")
          fi
        fi
        ;;
      git)
        packages+=("git")
        ;;
      node)
        if [ "$OS_TYPE" = "Darwin" ]; then
          packages+=("node")
        elif [ "$OS_TYPE" = "Linux" ]; then
          if command -v pacman >/dev/null 2>&1; then
            packages+=("nodejs" "npm")
          else
            packages+=("nodejs" "npm")
          fi
        fi
        ;;
      cargo)
        need_rustup=1
        ;;
      curl/wget)
        if [ "$OS_TYPE" = "Darwin" ]; then
          packages+=("curl" "wget")
        elif [ "$OS_TYPE" = "Linux" ]; then
          packages+=("curl" "wget")
        fi
        ;;
    esac
  done

  if [ "${#packages[@]}" -gt 0 ]; then
    install_packages "${packages[@]}" || return 1
  fi
  if [ "$need_rustup" -eq 1 ]; then
    install_rustup || return 1
  fi
}

filter_missing_deps() {
  local remaining_deps=()
  local remaining_hints=()
  local dep
  local hint
  for i in "${!MISSING_DEPS[@]}"; do
    dep="${MISSING_DEPS[$i]}"
    hint="${MISSING_HINTS[$i]}"
    if [ "$dep" = "python" ]; then
      if command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
        continue
      fi
    fi
    if [ "$dep" = "curl/wget" ]; then
      if command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1; then
        continue
      fi
    fi
    if ! command -v "$dep" >/dev/null 2>&1; then
      remaining_deps+=("$dep")
      remaining_hints+=("$hint")
    fi
  done
  MISSING_DEPS=("${remaining_deps[@]}")
  MISSING_HINTS=("${remaining_hints[@]}")
}

find_latest_path() {
  local base="$1"
  local pattern="$2"
  local type="${3:-f}"
  if [ ! -d "$base" ]; then
    return 0
  fi
  if [ "$type" = "d" ]; then
    find "$base" -type d -name "$pattern" -print0 2>/dev/null | xargs -0 ls -td 2>/dev/null | head -n1
  else
    find "$base" -type f -name "$pattern" -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -n1
  fi
}

find_tauri_artifact() {
  local frontend_dir="$1"
  local variant="$2"
  local runtime="$3"
  local artifact_base="$frontend_dir/dist-artifacts/tauri/$variant/$runtime"
  local bundle_dir="$frontend_dir/src-tauri/target/release/bundle"

  if [ "$OS_TYPE" = "Darwin" ]; then
    local app
    app="$(find_latest_path "$artifact_base" "*.app" "d")"
    if [ -n "$app" ]; then
      echo "$app"
      return 0
    fi
    app="$(find_latest_path "$bundle_dir/macos" "*.app" "d")"
    if [ -n "$app" ]; then
      echo "$app"
      return 0
    fi
    find_latest_path "$bundle_dir/macos" "*.dmg" "f" || true
    return 0
  fi

  if [ "$OS_TYPE" = "Linux" ]; then
    local appimage
    appimage="$(find_latest_path "$artifact_base" "*.AppImage" "f")"
    if [ -n "$appimage" ]; then
      echo "$appimage"
      return 0
    fi
    appimage="$(find_latest_path "$bundle_dir" "*.AppImage" "f")"
    if [ -n "$appimage" ]; then
      echo "$appimage"
      return 0
    fi
    local deb
    deb="$(find_latest_path "$artifact_base" "*.deb" "f")"
    if [ -n "$deb" ]; then
      echo "$deb"
      return 0
    fi
    find_latest_path "$bundle_dir" "*.deb" "f" || true
    return 0
  fi

  find_latest_path "$artifact_base" "*.exe" "f" || true
  find_latest_path "$bundle_dir" "*.exe" "f" || true
  find_latest_path "$artifact_base" "*.msi" "f" || true
  find_latest_path "$bundle_dir" "*.msi" "f" || true
}

find_electron_artifact() {
  local frontend_dir="$1"
  local variant="$2"
  local runtime="$3"
  local artifact_base="$frontend_dir/dist-artifacts/electron/$variant/$runtime"

  if [ "$OS_TYPE" = "Darwin" ]; then
    local app
    app="$(find_latest_path "$artifact_base" "*.app" "d")"
    if [ -n "$app" ]; then
      echo "$app"
      return 0
    fi
    find_latest_path "$artifact_base" "*.dmg" "f" || true
    return 0
  fi

  if [ "$OS_TYPE" = "Linux" ]; then
    local unpacked
    unpacked="$(find_latest_path "$artifact_base" "linux-unpacked" "d")"
    if [ -n "$unpacked" ]; then
      find "$unpacked" -maxdepth 1 -type f -perm -111 ! -name "chrome-sandbox" ! -name "chrome_crashpad_handler" 2>/dev/null | head -n1
      return 0
    fi
    local appimage
    appimage="$(find_latest_path "$artifact_base" "*.AppImage" "f")"
    if [ -n "$appimage" ]; then
      echo "$appimage"
      return 0
    fi
    find_latest_path "$artifact_base" "*.deb" "f" || true
    return 0
  fi

  find_latest_path "$artifact_base" "*.exe" "f" || true
  find_latest_path "$artifact_base" "*.msi" "f" || true
}

run_artifact() {
  local artifact="$1"
  if [ -z "$artifact" ]; then
    return 1
  fi
  echo "Launching built app: $artifact"
  if [ "$OS_TYPE" = "Darwin" ]; then
    open "$artifact"
    return 0
  fi
  if [ "$OS_TYPE" = "Linux" ]; then
    if [[ "$artifact" == *.AppImage ]]; then
      chmod +x "$artifact"
      "$artifact" &
      return 0
    fi
    if command -v xdg-open >/dev/null 2>&1; then
      xdg-open "$artifact"
      return 0
    fi
    "$artifact" &
    return 0
  fi
  return 1
}

report_missing() {
  if [ "${#MISSING_DEPS[@]}" -eq 0 ]; then
    return 0
  fi

  echo "Missing required dependencies:" >&2
  for i in "${!MISSING_DEPS[@]}"; do
    echo "- ${MISSING_DEPS[$i]}: ${MISSING_HINTS[$i]}" >&2
  done
  echo "Install the missing dependencies and retry." >&2
  exit 1
}

download() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf "$url"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO- "$url"
    return 0
  fi
  echo "Missing required command: curl or wget." >&2
  exit 1
}

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    add_missing "python" "Python 3.12+ not found. Install Python and retry."
  fi
elif ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  add_missing "python" "Python 3.12+ not found. Install Python and retry."
fi

if ! command -v git >/dev/null 2>&1; then
  add_missing "git" "Install Git and retry."
fi
if ! command -v node >/dev/null 2>&1; then
  add_missing "node" "Install Node.js 20+ and retry."
fi

if [ "$MODE" = "tauri" ]; then
  if ! command -v cargo >/dev/null 2>&1; then
    add_missing "cargo" "Install Rust (rustup) and retry, or set LIFETRACE_MODE=web."
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
      add_missing "curl/wget" "curl or wget is required to install Rust."
    fi
  fi
fi

if ! command -v uv >/dev/null 2>&1; then
  if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    add_missing "curl/wget" "curl or wget is required to download uv."
  fi
fi

if ! command -v pnpm >/dev/null 2>&1; then
  if ! command -v corepack >/dev/null 2>&1 && ! command -v npm >/dev/null 2>&1; then
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
      add_missing "curl/wget" "curl or wget is required to install pnpm."
    fi
  fi
fi

install_missing_deps
filter_missing_deps
report_missing

if [ -z "$PYTHON_BIN" ] || ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "Python 3.12+ not found after installation. Reopen your terminal and retry." >&2
    exit 1
  fi
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  download "https://astral.sh/uv/install.sh" | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v pnpm >/dev/null 2>&1; then
  install_pnpm() {
    if command -v corepack >/dev/null 2>&1; then
      if corepack enable >/dev/null 2>&1 && corepack prepare pnpm@latest --activate >/dev/null 2>&1; then
        command -v pnpm >/dev/null 2>&1 && return 0
      fi
      echo "corepack activation failed. Falling back to pnpm install script." >&2
    fi
    if command -v npm >/dev/null 2>&1; then
      if npm install -g pnpm >/dev/null 2>&1; then
        command -v pnpm >/dev/null 2>&1 && return 0
      fi
      echo "npm global install failed. Falling back to pnpm install script." >&2
    fi
    if command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1; then
      echo "Installing pnpm via install script..."
      export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
      mkdir -p "$PNPM_HOME"
      export PATH="$PNPM_HOME:$PATH"
      if command -v curl >/dev/null 2>&1; then
        curl -fsSL https://get.pnpm.io/install.sh | sh -s --
      else
        wget -qO- https://get.pnpm.io/install.sh | sh -s --
      fi
      command -v pnpm >/dev/null 2>&1 && return 0
    fi
    return 1
  }

  if ! install_pnpm; then
    echo "pnpm not found after installation. Reopen your terminal and retry." >&2
    exit 1
  fi
fi

REPO_READY=0
DEPS_READY=0
if [ -e "$TARGET_DIR" ] && [ ! -d "$TARGET_DIR/.git" ]; then
  echo "Target path '$TARGET_DIR' exists and is not a git repo." >&2
  echo "Set LIFETRACE_DIR to a new folder and retry." >&2
  exit 1
fi

if [ -d "$TARGET_DIR/.git" ]; then
  cd "$TARGET_DIR"
  if [ -n "$(git status --porcelain)" ]; then
    echo "Repository has local changes. Commit or stash and retry." >&2
    exit 1
  fi
  git fetch --depth 1 "$REPO_URL" "$REF"
  HEAD_SHA="$(git rev-parse HEAD)"
  REMOTE_SHA="$(git rev-parse FETCH_HEAD)"
  if [ "$HEAD_SHA" = "$REMOTE_SHA" ]; then
    REPO_READY=1
  fi
else
  git clone --depth 1 --branch "$REF" "$REPO_URL" "$TARGET_DIR"
  cd "$TARGET_DIR"
fi

if [ -d ".venv" ] && [ -d "free-todo-frontend/node_modules" ]; then
  DEPS_READY=1
fi

if [ "$REPO_READY" -eq 0 ] || [ "$DEPS_READY" -eq 0 ]; then
  if [ -n "$(git status --porcelain)" ]; then
    echo "Repository has local changes. Commit or stash and retry." >&2
    exit 1
  fi
  git fetch --depth 1 "$REPO_URL" "$REF"
  git checkout -q -B "$REF" FETCH_HEAD
  uv sync
  if [ -d ".venv" ] && [ -d "free-todo-frontend/node_modules" ]; then
    DEPS_READY=1
  fi
else
  echo "Repository is up to date. Skipping install steps."
fi

if [ "$RUN_AFTER_INSTALL" != "1" ]; then
  echo "Install complete."
  exit 0
fi

case "$MODE" in
  web)
    echo "Starting backend..."
    uv run "$PYTHON_BIN" -m lifetrace.server &
    BACKEND_PID=$!
    cleanup() {
      if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
        kill "$BACKEND_PID" >/dev/null 2>&1 || true
      fi
    }
    trap cleanup EXIT

    cd free-todo-frontend
    if [ ! -d "node_modules" ]; then
      pnpm install
    fi

    if [ "$FRONTEND_ACTION" = "build" ]; then
      if [ "$REPO_READY" -eq 1 ] && [ "$DEPS_READY" -eq 1 ] && [ -d ".next" ]; then
        echo "Next.js build is up to date. Skipping build step."
      else
        echo "Building frontend..."
        pnpm build
      fi
      echo "Starting frontend (production)..."
      pnpm start
    else
      echo "Starting frontend (dev)..."
      WINDOW_MODE="$VARIANT" pnpm dev
    fi
    ;;
  tauri)
    cd free-todo-frontend
    if [ ! -d "node_modules" ]; then
      pnpm install
    fi

    if [ "$FRONTEND_ACTION" = "build" ]; then
      artifact="$(find_tauri_artifact "$(pwd)" "$VARIANT" "$BACKEND_RUNTIME")"
      if [ -z "$artifact" ] || [ "$REPO_READY" -eq 0 ] || [ "$DEPS_READY" -eq 0 ]; then
        echo "Building Tauri app ($VARIANT, $BACKEND_RUNTIME)..."
        pnpm "build:tauri:${VARIANT}:${BACKEND_RUNTIME}:full"
        artifact="$(find_tauri_artifact "$(pwd)" "$VARIANT" "$BACKEND_RUNTIME")"
      else
        echo "Tauri build is up to date. Skipping build step."
      fi
      if ! run_artifact "$artifact"; then
        echo "Build complete. Open the artifact under src-tauri/target/release/bundle/."
      fi
    else
      echo "Starting backend..."
      uv run "$PYTHON_BIN" -m lifetrace.server &
      BACKEND_PID=$!
      cleanup() {
        if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
          kill "$FRONTEND_PID" >/dev/null 2>&1 || true
        fi
        if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
          kill "$BACKEND_PID" >/dev/null 2>&1 || true
        fi
      }
      trap cleanup EXIT

      echo "Starting frontend dev server..."
      WINDOW_MODE="$VARIANT" pnpm dev &
      FRONTEND_PID=$!
      echo "Starting Tauri app..."
      pnpm tauri:dev
    fi
    ;;
  electron)
    cd free-todo-frontend
    if [ ! -d "node_modules" ]; then
      pnpm install
    fi

    if [ "$FRONTEND_ACTION" = "build" ]; then
      artifact="$(find_electron_artifact "$(pwd)" "$VARIANT" "$BACKEND_RUNTIME")"
      if [ -z "$artifact" ] || [ "$REPO_READY" -eq 0 ] || [ "$DEPS_READY" -eq 0 ]; then
        echo "Building Electron app ($VARIANT, $BACKEND_RUNTIME)..."
        pnpm "build:electron:${VARIANT}:${BACKEND_RUNTIME}:full:dir"
        artifact="$(find_electron_artifact "$(pwd)" "$VARIANT" "$BACKEND_RUNTIME")"
      else
        echo "Electron build is up to date. Skipping build step."
      fi
      if ! run_artifact "$artifact"; then
        echo "Build complete. Open the artifact under dist-artifacts/electron/."
      fi
    else
      if [ "$VARIANT" = "island" ]; then
        pnpm electron:dev:island
      else
        pnpm electron:dev
      fi
    fi
    ;;
esac
