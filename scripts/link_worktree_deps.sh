#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/link_worktree_deps.sh --main <main-root> --worktree <worktree-root> [--force]

Example:
  scripts/link_worktree_deps.sh --main /path/to/LifeTrace \
    --worktree /path/to/_worktrees/LifeTrace/chat-tool-ui
EOF
}

main_root=""
worktree_root=""
force=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --main)
      main_root="$2"
      shift 2
      ;;
    --worktree)
      worktree_root="$2"
      shift 2
      ;;
    --force)
      force=1
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$main_root" || -z "$worktree_root" ]]; then
  usage
  exit 1
fi

main_root="$(cd "$main_root" && pwd)"
worktree_root="$(cd "$worktree_root" && pwd)"

link_item() {
  local name="$1"
  local src="$2"
  local dest="$3"

  if [[ ! -e "$src" ]]; then
    echo "Skip: $name source not found: $src"
    return 0
  fi

  mkdir -p "$(dirname "$dest")"

  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ $force -eq 0 ]]; then
      echo "Skip: $name destination exists: $dest (use --force to replace)"
      return 0
    fi
    rm -rf "$dest"
  fi

  ln -s "$src" "$dest"
  echo "Linked $name: $dest -> $src"
}

link_item "frontend node_modules" \
  "$main_root/free-todo-frontend/node_modules" \
  "$worktree_root/free-todo-frontend/node_modules"

link_item "python .venv" \
  "$main_root/.venv" \
  "$worktree_root/.venv"

echo "Done."
