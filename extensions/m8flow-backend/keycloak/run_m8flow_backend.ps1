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

Push-Location (Join-Path $repoRoot "spiffworkflow-backend")
uv sync --all-groups --active
Pop-Location

python -m uvicorn extensions.app:app --host 0.0.0.0 --port 8000 --env-file (Join-Path $repoRoot ".env") --app-dir $repoRoot
