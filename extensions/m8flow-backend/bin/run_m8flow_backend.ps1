#requires -Version 5.1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
Set-Location $repoRoot

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
  (Join-Path $repoRoot "extensions\m8flow-backend\src")
)
$existing = $env:PYTHONPATH
$allPaths = @()
$allPaths += $extraPaths
if ($existing) { $allPaths += $existing }
$env:PYTHONPATH = ($allPaths | Where-Object { $_ }) -join [IO.Path]::PathSeparator

# --- .env loading (reload-friendly) ------------------------------------------
# keep a list of keys loaded from .env in this PowerShell session
if (-not $script:LoadedEnvKeys) { $script:LoadedEnvKeys = @() }

# remove previously-loaded keys so changes in .env take effect on re-run
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
      Set-Item -Path "Env:$key" -Value $value
      $script:LoadedEnvKeys += $key
    }
  }
}
# -----------------------------------------------------------------------------

$env:SPIFFWORKFLOW_BACKEND_DATABASE_URI = $env:M8FLOW_BACKEND_DATABASE_URI
$env:SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR = $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR

Push-Location (Join-Path $repoRoot "spiffworkflow-backend")
uv sync --all-groups --active
if ($env:M8FLOW_BACKEND_SW_UPGRADE_DB -eq "true") {
  python -m flask db upgrade
}
Pop-Location

$logConfig = Join-Path $repoRoot "uvicorn-log.yaml"

python -m uvicorn extensions.app:app `
  --host 0.0.0.0 --port 8000 `
  --env-file (Join-Path $repoRoot ".env") `
  --app-dir $repoRoot `
  --log-config $logConfig
