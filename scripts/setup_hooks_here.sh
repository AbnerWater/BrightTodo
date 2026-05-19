#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${repo_root}" ]]; then
  echo "Failed to locate git repo root. Run from inside a git worktree." >&2
  exit 1
fi

hooks_dir="${repo_root}/.githooks"
if [[ ! -d "${hooks_dir}" ]]; then
  echo "Missing hooks directory: ${hooks_dir}" >&2
  exit 1
fi

git -C "${repo_root}" config core.hooksPath .githooks

for hook in pre-commit post-checkout; do
  if [[ ! -f "${hooks_dir}/${hook}" ]]; then
    echo "Warning: missing hook file: ${hooks_dir}/${hook}" >&2
  fi
done

if command -v chmod >/dev/null 2>&1; then
  chmod +x "${hooks_dir}/pre-commit" "${hooks_dir}/post-checkout" 2>/dev/null || true
fi

echo "Configured core.hooksPath=.githooks for ${repo_root}"
