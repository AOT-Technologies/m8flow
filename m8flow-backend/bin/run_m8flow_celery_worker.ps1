#requires -Version 5.1

param(
  [ValidateSet("worker", "flower")]
  [string]$Mode = "worker",
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$PassthroughArgs
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
Set-Location $repoRoot

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

if (-not (Test-Path ".venv")) { python -m venv .venv }

. (Join-Path $repoRoot ".venv\Scripts\Activate.ps1")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "uv not found; installing into the virtual environment..."
  python -m pip install uv
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Error "uv is required but could not be installed. Install it manually and re-run."
  exit 1
}

$extraPaths = @(
  (Join-Path $repoRoot "spiffworkflow-backend"),
  (Join-Path $repoRoot "spiffworkflow-backend\src"),
  (Join-Path $repoRoot "m8flow-backend\src")
)
$existing = $env:PYTHONPATH
$allPaths = @()
$allPaths += $extraPaths
if ($existing) { $allPaths += $existing }
$env:PYTHONPATH = ($allPaths | Where-Object { $_ }) -join [IO.Path]::PathSeparator

if (-not $script:LoadedEnvKeys) { $script:LoadedEnvKeys = @() }
foreach ($k in $script:LoadedEnvKeys) {
  Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue
}
$script:LoadedEnvKeys = @()

$envFile = Join-Path $repoRoot ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    if ($line.StartsWith("export ")) { $line = $line.Substring(7).Trim() }

    $idx = $line.IndexOf("=")
    if ($idx -lt 1) { return }

    $key = $line.Substring(0, $idx).Trim()
    $value = $line.Substring($idx + 1).Trim()

    if ($value.StartsWith("'") -and $value.EndsWith("'")) {
      $value = $value.Substring(1, $value.Length - 2)
    } elseif ($value.StartsWith('"') -and $value.EndsWith('"')) {
      $value = $value.Substring(1, $value.Length - 2)
    } else {
      $commentIdx = $value.IndexOf(" #")
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

$resolvedBpmnSpecDir = Resolve-RepoRelativePath -PathValue $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR
if ($resolvedBpmnSpecDir) {
  $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR = $resolvedBpmnSpecDir
}

# Bridge: upstream spiffworkflow-backend reads SPIFFWORKFLOW_BACKEND_* env vars — map from M8FLOW_ names.
$env:SPIFFWORKFLOW_BACKEND_DATABASE_URI = $env:M8FLOW_BACKEND_DATABASE_URI
$env:SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR = $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR

$env:M8FLOW_BACKEND_CELERY_ENABLED = "true"
$env:SPIFFWORKFLOW_BACKEND_CELERY_ENABLED = "true"
$env:M8FLOW_BACKEND_RUN_BACKGROUND_SCHEDULER_IN_CREATE_APP = "false"
$env:SPIFFWORKFLOW_BACKEND_RUN_BACKGROUND_SCHEDULER_IN_CREATE_APP = "false"
# Only the API process should run schema migrations on startup.
$env:M8FLOW_BACKEND_UPGRADE_DB = "false"
$env:M8FLOW_BACKEND_SW_UPGRADE_DB = "false"
if ($Mode -eq "worker") {
  $env:M8FLOW_BACKEND_RUNNING_IN_CELERY_WORKER = "true"
  $env:SPIFFWORKFLOW_BACKEND_RUNNING_IN_CELERY_WORKER = "true"
} else {
  $env:M8FLOW_BACKEND_RUNNING_IN_CELERY_WORKER = "false"
  $env:SPIFFWORKFLOW_BACKEND_RUNNING_IN_CELERY_WORKER = "false"
}

Push-Location (Join-Path $repoRoot "spiffworkflow-backend")
uv sync --all-groups --active
if ($env:M8FLOW_BACKEND_SW_UPGRADE_DB -eq "true") {
  python -m flask db upgrade
}
Pop-Location

$logLevel = $env:M8FLOW_BACKEND_CELERY_LOG_LEVEL
if (-not $logLevel) { $logLevel = "info" }

if ($Mode -eq "worker") {
  $workerArgs = @("worker", "--loglevel", $logLevel)

  $enableEvents = $env:M8FLOW_BACKEND_CELERY_ENABLE_EVENTS
  if (-not $enableEvents) { $enableEvents = "true" }
  if (@("1", "true", "yes", "on") -contains $enableEvents.ToLowerInvariant()) {
    $workerArgs += "-E"
  }

  # --- Concurrency / pool sizing (env-configurable) ---
  # NOTE: Flower autoscale requires Celery worker to start with --autoscale=max,min
  $autoscaleMin = $env:M8FLOW_BACKEND_CELERY_AUTOSCALE_MIN
  $autoscaleMax = $env:M8FLOW_BACKEND_CELERY_AUTOSCALE_MAX
  $concurrency = $env:M8FLOW_BACKEND_CELERY_CONCURRENCY
  $pool = $env:M8FLOW_BACKEND_CELERY_POOL
  if (-not $pool) {
    # Celery's prefork pool is not reliable for local native Windows workers.
    $pool = if ($IsWindows -or $env:OS -eq 'Windows_NT') { "solo" } else { "prefork" }
  }

  # Prefer prefork because it's the pool type that supports resizing reliably.
  $workerArgs += "--pool=$pool"

  # If autoscale is configured, enable it.
  if ($autoscaleMin -and $autoscaleMax) {
    $workerArgs += "--autoscale=$autoscaleMax,$autoscaleMin"
    # Optional: set initial concurrency to min if not explicitly set
    if (-not $concurrency) {
      $concurrency = $autoscaleMin
    }
  }

  # If concurrency is explicitly configured (or set from min), apply it.
  if ($concurrency) {
    $workerArgs += "--concurrency=$concurrency"
  }

  python -m celery -A "m8flow_backend.background_processing.celery_worker:celery_app" @workerArgs @PassthroughArgs
  exit $LASTEXITCODE
}

$flowerPort = $env:M8FLOW_BACKEND_CELERY_FLOWER_PORT
if (-not $flowerPort) { $flowerPort = "5555" }
$flowerAddress = $env:M8FLOW_BACKEND_CELERY_FLOWER_ADDRESS
if (-not $flowerAddress) { $flowerAddress = "0.0.0.0" }
$flowerPort = $flowerPort.Trim()
$flowerAddress = $flowerAddress.Trim()
$flowerArgs = @("flower", "--address=$flowerAddress", "--port=$flowerPort")

$flowerAuth = $env:M8FLOW_BACKEND_CELERY_FLOWER_BASIC_AUTH
if ($flowerAuth) {
  $flowerArgs += @("--basic-auth=$flowerAuth")
}

python -m celery -A "m8flow_backend.background_processing.celery_worker:celery_app" @flowerArgs @PassthroughArgs
