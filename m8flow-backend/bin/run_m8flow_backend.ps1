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

function Test-CommandAvailable {
  param([string]$Name)

  return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
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

  . (Join-Path $venvDir 'Scripts\Activate.ps1')

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

$env:SPIFFWORKFLOW_BACKEND_DATABASE_URI = $env:M8FLOW_BACKEND_DATABASE_URI
$env:SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR = $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR

if (-not $env:UVICORN_LOG_LEVEL -and -not $runningInContainer) {
  $env:UVICORN_LOG_LEVEL = 'debug'
}

if ($script:UseUvRunner -and $env:M8FLOW_BACKEND_SYNC_DEPS -ne 'false') {
  Push-Location (Join-Path $repoRoot 'spiffworkflow-backend')
  try {
    $uvSyncArgs = @('sync', '--all-groups')
    if ($env:VIRTUAL_ENV) {
      $uvSyncArgs += '--active'
    }
    & uv @uvSyncArgs
  } finally {
    Pop-Location
  }
}

if ($env:M8FLOW_BACKEND_SW_UPGRADE_DB -ne 'false') {
  Invoke-BackendPythonInBackendDir @('-m', 'flask', 'db', 'upgrade')
}

if ($env:M8FLOW_BACKEND_UPGRADE_DB -ne 'false') {
  $alembicIni = Join-Path $repoRoot 'm8flow-backend\migrations\alembic.ini'
  Invoke-BackendPython @('-m', 'alembic', '-c', $alembicIni, 'upgrade', 'head')
}

if ($env:M8FLOW_BACKEND_RUN_BOOTSTRAP -ne 'false') {
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

$logConfig = Join-Path $repoRoot 'uvicorn-log.yaml'
$defaultBackendPort = 7000
$backendPort = if ($PSBoundParameters.ContainsKey('Port')) {
  $Port
} elseif ($env:M8FLOW_BACKEND_PORT) {
  [int]$env:M8FLOW_BACKEND_PORT
} else {
  $defaultBackendPort
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
  $uvicornArgs += @('--reload', '--workers', '1')
  $uvicornArgs += @('--reload-exclude', 'm8flow-frontend/**')
  $uvicornArgs += @('--reload-exclude', '**/node_modules/**')
  $uvicornArgs += @('--reload-exclude', '**/.vite/**')
  $uvicornArgs += @('--reload-exclude', '**/.vite-temp/**')
  $uvicornArgs += @('--reload-exclude', '.venv/**')
  $uvicornArgs += @('--reload-exclude', '.git/**')
}

Invoke-BackendPython $uvicornArgs
