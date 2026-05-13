#requires -Version 5.1

param(
  [Parameter(Position = 0)]
  [int]$Port,

  [switch]$Reload
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
Set-Location $repoRoot
$script:LauncherStartedAt = Get-Date

function Test-CommandAvailable {
  param([string]$Name)

  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Format-Duration {
  param([TimeSpan]$Duration)

  return '{0:00}m{1:00}s' -f [int]$Duration.TotalMinutes, $Duration.Seconds
}

function Write-LauncherStatus {
  param([string]$Message)

  $elapsed = (Get-Date) - $script:LauncherStartedAt
  Write-Host ("m8flow-backend: [{0}] {1}" -f (Format-Duration $elapsed), $Message)
}

function Invoke-TimedStep {
  param(
    [string]$Label,
    [scriptblock]$Action
  )

  $startedAt = Get-Date
  Write-LauncherStatus "$Label..."
  & $Action
  Write-LauncherStatus ("{0} complete in {1}" -f $Label, (Format-Duration ((Get-Date) - $startedAt)))
}

function Test-IsRunningInContainer {
  if (Test-Path '/.dockerenv') {
    return $true
  }

  if (Test-Path '/proc/1/cgroup') {
    try {
      return Select-String -Path '/proc/1/cgroup' -Pattern 'docker|containerd|kubepods' -Quiet
    } catch {
      return $false
    }
  }

  return $false
}

function Resolve-RepoRelativePath {
  param([string]$PathValue)

  if (-not $PathValue) {
    return $PathValue
  }

  if ([System.IO.Path]::IsPathRooted($PathValue)) {
    return $PathValue
  }

  return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PathValue))
}

function Ensure-LocalUvEnvironment {
  $venvDir = Join-Path $repoRoot '.venv'
  if (-not (Test-Path $venvDir)) {
    python -m venv $venvDir
  }

$activateScript = @(
  (Join-Path $venvDir 'Scripts/Activate.ps1'),
  (Join-Path $venvDir 'bin/Activate.ps1')
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $activateScript) {
  throw "No PowerShell venv activation script found in $venvDir"
}

. $activateScript

  if (-not (Test-CommandAvailable uv)) {
    Write-Host 'uv not found; installing into the virtual environment...'
    python -m pip install uv
  }

  if (-not (Test-CommandAvailable uv)) {
    throw 'uv is required but could not be installed. Install it manually and re-run.'
  }
}

function Get-UvPythonCommand {
  $uvArgs = @('run')
  if ($env:VIRTUAL_ENV) {
    $uvArgs += '--active'
  }
  $uvArgs += 'python'
  return $uvArgs
}

function Invoke-UvPython {
  param([string[]]$Arguments)

  $uvArgs = Get-UvPythonCommand
  $uvArgs += $Arguments
  & uv @uvArgs
}

function Invoke-BackendPython {
  param([string[]]$Arguments)

  if ($script:UseUvRunner) {
    Push-Location (Join-Path $repoRoot 'spiffworkflow-backend')
    try {
      Invoke-UvPython $Arguments
    } finally {
      Pop-Location
    }
    return
  }

  & python @Arguments
}

function Invoke-BackendPythonInBackendDir {
  param([string[]]$Arguments)

  Push-Location (Join-Path $repoRoot 'spiffworkflow-backend')
  try {
    Invoke-BackendPython $Arguments
  } finally {
    Pop-Location
  }
}

function Test-HasM8FlowBackendRuntimeDependencies {
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    Invoke-UvPython @('-c', 'import nats') 2>&1 > $null
    if ($LASTEXITCODE -ne 0) {
      return $false
    }
    return $true
  } finally {
    $ErrorActionPreference = $oldPreference
  }
}

function Sync-LocalBackendEnvironment {
  Push-Location (Join-Path $repoRoot 'spiffworkflow-backend')
  try {
    $uvSyncArgs = @('sync', '--all-groups', '--inexact')
    if ($env:VIRTUAL_ENV) {
      $uvSyncArgs += '--active'
    }
    & uv @uvSyncArgs

    if (-not (Test-HasM8FlowBackendRuntimeDependencies)) {
      $uvPipArgs = @('pip', 'install', 'nats-py>=2.6.0')
      & uv @uvPipArgs
    }
  } finally {
    Pop-Location
  }
}

function Invoke-SpiffDbUpgrade {
  Invoke-BackendPythonInBackendDir @('-m', 'flask', 'db', 'upgrade')
}

function Invoke-M8FlowDbUpgrade {
  $alembicIni = Join-Path $repoRoot 'm8flow-backend\migrations\alembic.ini'
  Invoke-BackendPython @('-m', 'alembic', '-c', $alembicIni, 'upgrade', 'head')
}

function Invoke-BackendBootstrap {
  Push-Location (Join-Path $repoRoot 'spiffworkflow-backend')
  try {
    if ($script:UseUvRunner) {
      Invoke-UvPython @('bin/bootstrap.py')
    } else {
      & python 'bin/bootstrap.py'
    }
  } finally {
    Pop-Location
  }
}

# --- .env loading (reload-friendly) ------------------------------------------
if (-not $script:LoadedEnvKeys) { $script:LoadedEnvKeys = @() }

foreach ($k in $script:LoadedEnvKeys) {
  Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue
}
$script:LoadedEnvKeys = @()

$envFile = Join-Path $repoRoot '.env'
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    if ($line.StartsWith('export ')) { $line = $line.Substring(7).Trim() }

    $idx = $line.IndexOf('=')
    if ($idx -lt 1) { return }

    $key = $line.Substring(0, $idx).Trim()
    $value = $line.Substring($idx + 1).Trim()

    if ($value.StartsWith("'") -and $value.EndsWith("'")) {
      $value = $value.Substring(1, $value.Length - 2)
    } elseif ($value.StartsWith('"') -and $value.EndsWith('"')) {
      $value = $value.Substring(1, $value.Length - 2)
    } else {
      $commentIdx = $value.IndexOf(' #')
      if ($commentIdx -lt 0) { $commentIdx = $value.IndexOf("`t#") }
      if ($commentIdx -ge 0) { $value = $value.Substring(0, $commentIdx).TrimEnd() }
    }

    if ($key) {
      $existingItem = Get-Item -Path "Env:$key" -ErrorAction SilentlyContinue
      if (-not $existingItem) {
        Set-Item -Path "Env:$key" -Value $value
        $script:LoadedEnvKeys += $key
      }
    }
  }
}
# -----------------------------------------------------------------------------

$runningInContainer = Test-IsRunningInContainer
$useUvSetting = if ($env:M8FLOW_BACKEND_USE_UV) { $env:M8FLOW_BACKEND_USE_UV } else { 'auto' }
$script:UseUvRunner = $false

if (-not $runningInContainer -and $useUvSetting -ne 'false') {
  Ensure-LocalUvEnvironment
  $script:UseUvRunner = $true
}

if ($useUvSetting -eq 'true' -and -not $script:UseUvRunner) {
  throw "M8FLOW_BACKEND_USE_UV=true was requested but 'uv' is not available."
}

$extraPaths = @(
  $repoRoot,
  (Join-Path $repoRoot 'spiffworkflow-backend'),
  (Join-Path $repoRoot 'spiffworkflow-backend\src'),
  (Join-Path $repoRoot 'm8flow-backend\src')
)
$existing = $env:PYTHONPATH
$allPaths = @()
$allPaths += $extraPaths
if ($existing) { $allPaths += $existing }
$env:PYTHONPATH = ($allPaths | Where-Object { $_ }) -join [IO.Path]::PathSeparator

$resolvedBpmnSpecDir = Resolve-RepoRelativePath -PathValue $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR
if ($resolvedBpmnSpecDir) {
  $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR = $resolvedBpmnSpecDir
}

# Bridge: upstream spiffworkflow-backend reads SPIFFWORKFLOW_BACKEND_* env vars — map from M8FLOW_ names.
$env:SPIFFWORKFLOW_BACKEND_DATABASE_URI = $env:M8FLOW_BACKEND_DATABASE_URI
$env:SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR = $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR

if (-not $env:UVICORN_LOG_LEVEL -and -not $runningInContainer) {
  $env:UVICORN_LOG_LEVEL = 'debug'
}

if ($script:UseUvRunner -and $env:M8FLOW_BACKEND_SYNC_DEPS -ne 'false') {
  Invoke-TimedStep 'Syncing local Python environment' { Sync-LocalBackendEnvironment }
}

if ($env:M8FLOW_BACKEND_SW_UPGRADE_DB -ne 'false') {
  Invoke-TimedStep 'Running upstream backend migrations' { Invoke-SpiffDbUpgrade }
}

if ($env:M8FLOW_BACKEND_UPGRADE_DB -ne 'false') {
  Invoke-TimedStep 'Running M8Flow migrations' { Invoke-M8FlowDbUpgrade }
}

if ($env:M8FLOW_BACKEND_RUN_BOOTSTRAP -ne 'false') {
  Invoke-TimedStep 'Running backend bootstrap' { Invoke-BackendBootstrap }
}

$logConfig = Join-Path $repoRoot 'uvicorn-log.yaml'
$defaultBackendPort = 6840
$backendPort = if ($PSBoundParameters.ContainsKey('Port')) {
  $Port
} elseif ($env:M8FLOW_BACKEND_PORT) {
  [int]$env:M8FLOW_BACKEND_PORT
} else {
  $defaultBackendPort
}

Write-LauncherStatus ("Preparing backend startup (port={0}, reload={1}, uv_runner={2})" -f $backendPort, [bool]$Reload, $script:UseUvRunner)
if ($Reload) {
  Write-LauncherStatus "Reload mode starts a reloader first, then a worker. A short quiet pause after 'Uvicorn running' is normal on first startup."
}

$uvicornArgs = @(
  '-m'; 'uvicorn'
  'm8flow_backend.app:app'
  '--host'; '0.0.0.0'
  '--port'; $backendPort.ToString()
  '--app-dir'; $repoRoot
  '--log-config'; $logConfig
)
if ($env:UVICORN_LOG_LEVEL) {
  $uvicornArgs += @('--log-level', $env:UVICORN_LOG_LEVEL)
}
if ($Reload) {
  $uvicornArgs += @('--reload')
  $uvicornArgs += @('--reload-dir', (Join-Path $repoRoot 'm8flow-backend\src'))
  $uvicornArgs += @('--reload-dir', (Join-Path $repoRoot 'm8flow-backend\migrations'))
  $uvicornArgs += @('--reload-exclude', 'm8flow-frontend/**')
  $uvicornArgs += @('--reload-exclude', '**/node_modules/**')
  $uvicornArgs += @('--reload-exclude', '**/.vite/**')
  $uvicornArgs += @('--reload-exclude', '**/.vite-temp/**')
  $uvicornArgs += @('--reload-exclude', '.venv/**')
  $uvicornArgs += @('--reload-exclude', '.git/**')
}

Write-LauncherStatus "Starting Uvicorn. The backend is ready once '/v1.0/status' returns 200."
Invoke-BackendPython $uvicornArgs
