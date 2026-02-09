#requires -Version 5.1
# Usage:
#   .\run_m8flow_alembic.ps1 upgrade head
#   .\run_m8flow_alembic.ps1 current
#   .\run_m8flow_alembic.ps1 history
#   .\run_m8flow_alembic.ps1 stamp head
#   .\run_m8flow_alembic.ps1 downgrade -1
# Notes:
#   downgrade -1 steps back one revision; downgrade base resets to the first revision.
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$AlembicArgs
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
Set-Location $repoRoot

$envPath = Join-Path $repoRoot ".env"
if (Test-Path $envPath) {
  Get-Content $envPath | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $parts = $line -split "=", 2
    if ($parts.Length -ne 2) { return }
    $name = $parts[0].Trim()
    $value = $parts[1].Trim()

    if ($value.StartsWith('"') -and $value.EndsWith('"')) {
      $value = $value.Substring(1, $value.Length - 2)
    } elseif ($value.StartsWith("'") -and $value.EndsWith("'")) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    $value = $value -replace "\s+#.*$", ""
    Set-Item -Path ("Env:{0}" -f $name) -Value $value
  }
}

$env:M8FLOW_BACKEND_DATABASE_URI = $env:M8FLOW_BACKEND_DATABASE_URI
$env:SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR = $env:M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR

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

$alembicIni = Join-Path $repoRoot "extensions\m8flow-backend\migrations\alembic.ini"
if (-not $AlembicArgs -or $AlembicArgs.Count -eq 0) {
  Write-Host "Usage: .\run_m8flow_alembic.ps1 <alembic args>"
  Write-Host "Example: .\run_m8flow_alembic.ps1 upgrade head"
  exit 1
}

python -m alembic -c $alembicIni @AlembicArgs
