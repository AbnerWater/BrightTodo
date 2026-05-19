param(
    [switch]$SkipInstall,
    [switch]$InstallOnly,
    [int]$StartupTimeoutSec = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FrontendDir = Join-Path $RepoRoot "frontend"
$ConfigFile = Join-Path $RepoRoot "lifetrace\config\config.yaml"
$DefaultConfigFile = Join-Path $RepoRoot "lifetrace\config\default_config.yaml"
$DevLogDir = Join-Path $RepoRoot "lifetrace\logs\dev"
$BackendOutLogFile = Join-Path $DevLogDir "backend.out.log"
$BackendErrLogFile = Join-Path $DevLogDir "backend.err.log"
$FrontendOutLogFile = Join-Path $DevLogDir "frontend.out.log"
$FrontendErrLogFile = Join-Path $DevLogDir "frontend.err.log"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Refresh-Path {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath;$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin"
}

function Ensure-Node {
    if (Test-Command "node") {
        $versionText = (& node --version).TrimStart("v")
        $major = [int]($versionText.Split(".")[0])
        if ($major -lt 20) {
            throw "Node.js 20+ is required. Current version: v$versionText"
        }
        return
    }

    if (Test-Command "winget") {
        Write-Step "Installing Node.js LTS with winget"
        winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements
        Refresh-Path
    }

    if (-not (Test-Command "node")) {
        throw "Node.js 20+ was not found. Install Node.js LTS and rerun this script."
    }
}

function Ensure-Uv {
    if (Test-Command "uv") {
        return
    }

    Write-Step "Installing uv"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    Refresh-Path

    if (-not (Test-Command "uv")) {
        throw "uv was installed but is not available on PATH. Reopen the terminal and rerun this script."
    }
}

function Ensure-Pnpm {
    if (Test-Command "pnpm") {
        return
    }

    Write-Step "Installing pnpm"
    $installed = $false
    if (Test-Command "corepack") {
        try {
            corepack enable
            corepack prepare pnpm@latest --activate
            $installed = Test-Command "pnpm"
        } catch {
            Write-Host "corepack could not activate pnpm; trying npm."
        }
    }

    if (-not $installed -and (Test-Command "npm")) {
        npm install -g pnpm
        Refresh-Path
        $installed = Test-Command "pnpm"
    }

    if (-not $installed) {
        throw "pnpm was not found. Install pnpm and rerun this script."
    }
}

function Ensure-Config {
    if ((Test-Path $ConfigFile) -or (-not (Test-Path $DefaultConfigFile))) {
        return
    }

    Write-Step "Creating local config.yaml from default_config.yaml"
    Copy-Item -LiteralPath $DefaultConfigFile -Destination $ConfigFile
}

function Sync-Dependencies {
    Write-Step "Checking backend dependencies"
    Push-Location $RepoRoot
    try {
        uv python install 3.12 | Out-Host
        uv sync
    } finally {
        Pop-Location
    }

    Write-Step "Checking frontend dependencies"
    Push-Location $FrontendDir
    try {
        pnpm install
    } finally {
        Pop-Location
    }
}

function Test-HttpOk {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Test-TcpPort {
    param([int]$Port)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(200)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Find-BackendPort {
    foreach ($port in 8001..8100) {
        if (-not (Test-TcpPort $port)) {
            continue
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/health" -TimeoutSec 1
            $json = $response.Content | ConvertFrom-Json
            if ($json.app -eq "lifetrace") {
                return $port
            }
        } catch {
        }
    }
    return $null
}

function Find-FrontendPort {
    foreach ($port in 3001..3100) {
        if (-not (Test-TcpPort $port)) {
            continue
        }
        if (Test-HttpOk "http://127.0.0.1:$port") {
            return $port
        }
    }
    return $null
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId $child.ProcessId
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-DevProcess {
    param([System.Diagnostics.Process]$Process)
    if (-not $Process) {
        return
    }
    try {
        if (-not $Process.HasExited) {
            Stop-ProcessTree -ProcessId $Process.Id
        }
    } catch {
    }
}

if (-not (Test-Path $FrontendDir)) {
    throw "Frontend directory not found: $FrontendDir"
}

Write-Step "BrightToDo environment check"
Ensure-Node
Ensure-Uv
Ensure-Pnpm
Ensure-Config

if (-not $SkipInstall) {
    Sync-Dependencies
} else {
    Write-Host "Skipping dependency install because -SkipInstall was set."
}

if ($InstallOnly) {
    Write-Host ""
    Write-Host "Environment is ready."
    exit 0
}

$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Backend virtualenv is missing. Rerun without -SkipInstall."
}
if (-not (Test-Path $DevLogDir)) {
    New-Item -ItemType Directory -Force -Path $DevLogDir | Out-Null
}
Set-Content -Path $BackendOutLogFile -Value ""
Set-Content -Path $BackendErrLogFile -Value ""
Set-Content -Path $FrontendOutLogFile -Value ""
Set-Content -Path $FrontendErrLogFile -Value ""

Write-Step "Starting backend"
$backendProcess = Start-Process -FilePath $PythonExe `
    -ArgumentList @("-m", "lifetrace.server") `
    -WorkingDirectory $RepoRoot `
    -PassThru `
    -RedirectStandardOutput $BackendOutLogFile `
    -RedirectStandardError $BackendErrLogFile `
    -WindowStyle Hidden

$backendPort = $null
$frontendPort = $null
$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
$frontendProcess = $null

try {
    while ((Get-Date) -lt $deadline) {
        if ($backendProcess.HasExited) {
            throw "Backend process exited early with code $($backendProcess.ExitCode)."
        }

        if (-not $backendPort) {
            $backendPort = Find-BackendPort
        }
        if ($backendPort) {
            break
        }

        Start-Sleep -Seconds 2
    }

    if (-not $backendPort) {
        Write-Host "Backend logs:  $BackendOutLogFile / $BackendErrLogFile"
        throw "Timed out waiting for BrightToDo backend to start."
    }

    Write-Step "Starting frontend"
    $frontendProcess = Start-Process -FilePath "cmd.exe" `
        -ArgumentList @("/c", "pnpm", "dev") `
        -WorkingDirectory $FrontendDir `
        -PassThru `
        -RedirectStandardOutput $FrontendOutLogFile `
        -RedirectStandardError $FrontendErrLogFile `
        -WindowStyle Hidden

    while ((Get-Date) -lt $deadline) {
        if ($backendProcess.HasExited) {
            throw "Backend process exited early with code $($backendProcess.ExitCode)."
        }
        if ($frontendProcess.HasExited) {
            Write-Host "Frontend logs: $FrontendOutLogFile / $FrontendErrLogFile"
            throw "Frontend process exited early with code $($frontendProcess.ExitCode)."
        }

        if (-not $frontendPort) {
            $frontendPort = Find-FrontendPort
        }
        if ($frontendPort) {
            break
        }

        Start-Sleep -Seconds 2
    }

    if (-not $frontendPort) {
        Write-Host "Frontend logs: $FrontendOutLogFile / $FrontendErrLogFile"
        throw "Timed out waiting for BrightToDo frontend to start."
    }

    Write-Host ""
    Write-Host "BrightToDo is running." -ForegroundColor Green
    Write-Host "Frontend: http://localhost:$frontendPort"
    Write-Host "Backend:  http://127.0.0.1:$backendPort"
    Write-Host "Logs:     $DevLogDir"
    Write-Host ""
    Write-Host "Press Ctrl+C to stop both services."

    while ($true) {
        if ($backendProcess.HasExited) {
            throw "Backend process stopped with code $($backendProcess.ExitCode)."
        }
        if ($frontendProcess.HasExited) {
            throw "Frontend process stopped with code $($frontendProcess.ExitCode)."
        }
        Start-Sleep -Seconds 2
    }
} finally {
    Write-Host ""
    Write-Host "Stopping BrightToDo services..."
    Stop-DevProcess -Process $frontendProcess
    Stop-DevProcess -Process $backendProcess
}
