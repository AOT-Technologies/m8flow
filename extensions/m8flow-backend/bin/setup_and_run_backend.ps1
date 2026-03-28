#requires -Version 5.1

param(
  [Parameter(Position = 0)]
  [int]$Port
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
Set-Location $repoRoot

function Load-DotEnv {
  param([string]$EnvFilePath)

  if (-not (Test-Path $EnvFilePath)) {
    return
  }

  Get-Content $EnvFilePath | ForEach-Object {
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
      Set-Item -Path "Env:$key" -Value $value
    }
  }

  Write-Host 'Loaded .env'
}

if (-not (Test-Path '.venv')) {
  python -m venv .venv
}

. (Join-Path $repoRoot '.venv\Scripts\Activate.ps1')

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host 'uv not found; installing into the virtual environment...'
  python -m pip install uv
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw 'uv is required but could not be installed. Install it manually and re-run.'
}

Load-DotEnv -EnvFilePath (Join-Path $repoRoot '.env')

$pythonPathEntries = @(
  $repoRoot,
  (Join-Path $repoRoot 'extensions\m8flow-backend\src'),
  (Join-Path $repoRoot 'spiffworkflow-backend\src')
)
$env:PYTHONPATH = (($pythonPathEntries + @($env:PYTHONPATH)) | Where-Object { $_ }) -join [IO.Path]::PathSeparator

$env:SPIFFWORKFLOW_BACKEND_DATABASE_URI = $env:M8FLOW_BACKEND_DATABASE_URI
$env:SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR = $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR

$backendPort = if ($PSBoundParameters.ContainsKey('Port')) {
  $Port
} elseif ($env:M8FLOW_BACKEND_PORT) {
  [int]$env:M8FLOW_BACKEND_PORT
} else {
  7000
}

$env:UVICORN_LOG_LEVEL = if ($env:UVICORN_LOG_LEVEL) { $env:UVICORN_LOG_LEVEL } else { 'debug' }

Write-Host ':: Syncing backend dependencies (spiffworkflow-backend)...'
Push-Location (Join-Path $repoRoot 'spiffworkflow-backend')
uv sync
Pop-Location

if ($env:M8FLOW_BACKEND_UPGRADE_DB -eq 'true') {
  Write-Host ':: Running SpiffWorkflow DB migrations (flask db upgrade)...'
  Push-Location (Join-Path $repoRoot 'spiffworkflow-backend')
  uv run flask db upgrade
  Pop-Location
  Write-Host ':: M8Flow migrations run automatically when the app starts (extensions/app.py).'
}

Write-Host ":: Starting backend (extensions app) on port $backendPort..."
Push-Location (Join-Path $repoRoot 'spiffworkflow-backend')
try {
  uv run uvicorn extensions.app:app `
    --reload `
    --host '0.0.0.0' `
    --port $backendPort `
    --workers 1 `
    --log-level $env:UVICORN_LOG_LEVEL
} finally {
  Pop-Location
}
