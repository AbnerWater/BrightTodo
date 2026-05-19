param(
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-FullPath {
    param([string]$Path)
    return (Resolve-Path -LiteralPath $Path).Path
}

function Get-RepoRoot {
    $result = & git rev-parse --show-toplevel 2>$null
    if (-not $result) {
        throw "Failed to locate git repo root. Run from inside a git worktree."
    }
    return $result.Trim()
}

function Get-MainWorktree {
    $lines = & git worktree list --porcelain
    if (-not $lines) {
        throw "Failed to read git worktree list."
    }

    $paths = @()
    foreach ($line in $lines) {
        if ($line -like "worktree *") {
            $paths += $line.Substring(9).Trim()
        }
    }

    foreach ($path in $paths) {
        $gitDir = Join-Path $path ".git"
        if (Test-Path -LiteralPath $gitDir -PathType Container) {
            return $path
        }
    }

    throw "Could not determine main worktree. Please pass -Main to scripts/link_worktree_deps.ps1."
}

$worktreeRoot = Resolve-FullPath (Get-RepoRoot)
$mainRoot = Resolve-FullPath (Get-MainWorktree)

$scriptPath = Join-Path $worktreeRoot "scripts\link_worktree_deps.ps1"
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Missing script: $scriptPath"
}

if ($Force) {
    & powershell -ExecutionPolicy Bypass -File $scriptPath -Main $mainRoot -Worktree $worktreeRoot -Force
} else {
    & powershell -ExecutionPolicy Bypass -File $scriptPath -Main $mainRoot -Worktree $worktreeRoot
}
