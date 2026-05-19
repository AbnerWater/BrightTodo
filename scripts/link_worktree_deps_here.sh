#!/usr/bin/env bash
set -euo pipefail

force=0
if [[ "${1:-}" == "--force" ]]; then
  force=1
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${repo_root}" ]]; then
  echo "Failed to locate git repo root. Run from inside a git worktree." >&2
  exit 1
fi

main_root=""
while IFS= read -r line; do
  if [[ "$line" == worktree\ * ]]; then
    path="${line#worktree }"
    if [[ -d "${path}/.git" ]]; then
      main_root="${path}"
      break
    fi
  fi
done < <(git worktree list --porcelain)

if [[ -z "${main_root}" ]]; then
  echo "Could not determine main worktree. Please pass --main to scripts/link_worktree_deps.sh." >&2
  exit 1
fi

script_path="${repo_root}/scripts/link_worktree_deps.sh"
if [[ ! -f "${script_path}" ]]; then
  echo "Missing script: ${script_path}" >&2
  exit 1
fi

if [[ "${force}" -eq 1 ]]; then
  bash "${script_path}" --main "${main_root}" --worktree "${repo_root}" --force
else
  bash "${script_path}" --main "${main_root}" --worktree "${repo_root}"
fi
