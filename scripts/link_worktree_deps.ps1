param(
    [Parameter(Mandatory = $true)]
    [string]$Main,
    [Parameter(Mandatory = $true)]
    [string]$Worktree,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-FullPath {
    param([string]$Path)
    return (Resolve-Path -LiteralPath $Path).Path
}

function Ensure-Junction {
    param(
        [string]$Name,
        [string]$Source,
        [string]$Dest
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        Write-Warning "$Name source not found: $Source (skipped)"
        return
    }

    $destParent = Split-Path -Parent $Dest
    if (-not (Test-Path -LiteralPath $destParent)) {
        New-Item -ItemType Directory -Path $destParent | Out-Null
    }

    if (Test-Path -LiteralPath $Dest) {
        $item = Get-Item -LiteralPath $Dest -Force
        $isReparse = ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
        if ($isReparse) {
            $target = $item.Target
            if ($target) {
                $targetFull = Resolve-FullPath $target
                $sourceFull = Resolve-FullPath $Source
                if ($targetFull -eq $sourceFull) {
                    Write-Host "$Name already linked: $Dest -> $targetFull"
                    return
                }
            }
        }

        if (-not $Force) {
            Write-Warning "$Name destination exists: $Dest (use -Force to replace)"
            return
        }

        Remove-Item -LiteralPath $Dest -Recurse -Force
    }

    New-Item -ItemType Junction -Path $Dest -Target $Source | Out-Null
    Write-Host "Linked ${Name}: $Dest -> $Source"
}

$mainRoot = Resolve-FullPath $Main
$worktreeRoot = Resolve-FullPath $Worktree

Ensure-Junction `
    -Name "frontend node_modules" `
    -Source (Join-Path $mainRoot "free-todo-frontend\node_modules") `
    -Dest (Join-Path $worktreeRoot "free-todo-frontend\node_modules")

Ensure-Junction `
    -Name "python .venv" `
    -Source (Join-Path $mainRoot ".venv") `
    -Dest (Join-Path $worktreeRoot ".venv")

Write-Host "Done."
