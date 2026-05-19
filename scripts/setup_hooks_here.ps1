Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $result = & git rev-parse --show-toplevel 2>$null
    if (-not $result) {
        throw "Failed to locate git repo root. Run from inside a git worktree."
    }
    return $result.Trim()
}

$repoRoot = Get-RepoRoot
$hooksDir = Join-Path $repoRoot ".githooks"

if (-not (Test-Path -LiteralPath $hooksDir -PathType Container)) {
    throw "Missing hooks directory: $hooksDir"
}

& git -C $repoRoot config core.hooksPath .githooks

foreach ($hook in @("pre-commit", "post-checkout")) {
    $hookPath = Join-Path $hooksDir $hook
    if (-not (Test-Path -LiteralPath $hookPath)) {
        Write-Warning "Missing hook file: $hookPath"
    }
}

Write-Host "Configured core.hooksPath=.githooks for $repoRoot"
