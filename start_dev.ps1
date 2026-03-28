#requires -Version 5.1

param(
  [Parameter(Position = 0)]
  [int]$BackendPort = $(if ($env:M8FLOW_BACKEND_PORT) { [int]$env:M8FLOW_BACKEND_PORT } else { 7000 }),

  [Parameter(Position = 1)]
  [int]$FrontendPort = 7001
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$locationPushed = $false
Push-Location $root
$locationPushed = $true

function Quote-PowerShellLiteral {
  param([string]$Value)

  return "'" + $Value.Replace("'", "''") + "'"
}

function Load-DotEnv {
  param([string]$EnvFilePath)

  $originalValues = @{}

  if (-not (Test-Path $EnvFilePath)) {
    return $originalValues
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

    if (-not $key) { return }

    if (-not $originalValues.ContainsKey($key)) {
      $existingItem = Get-Item -Path "Env:$key" -ErrorAction SilentlyContinue
      $originalValues[$key] = [pscustomobject]@{
        HadValue = $null -ne $existingItem
        Value    = if ($existingItem) { $existingItem.Value } else { $null }
      }
    }

    Set-Item -Path "Env:$key" -Value $value
  }

  Write-Host 'Loaded .env'
  return $originalValues
}

function Restore-DotEnv {
  param([hashtable]$OriginalValues)

  foreach ($entry in $OriginalValues.GetEnumerator()) {
    if ($entry.Value.HadValue) {
      Set-Item -Path "Env:$($entry.Key)" -Value $entry.Value.Value
    } else {
      Remove-Item -Path "Env:$($entry.Key)" -ErrorAction SilentlyContinue
    }
  }
}

function Get-EnvSnapshot {
  param([string[]]$Keys)

  $snapshot = @{}
  foreach ($key in $Keys) {
    $existingItem = Get-Item -Path "Env:$key" -ErrorAction SilentlyContinue
    $snapshot[$key] = [pscustomobject]@{
      HadValue = $null -ne $existingItem
      Value    = if ($existingItem) { $existingItem.Value } else { $null }
    }
  }

  return $snapshot
}

function Restore-EnvSnapshot {
  param([hashtable]$Snapshot)

  foreach ($entry in $Snapshot.GetEnumerator()) {
    if ($entry.Value.HadValue) {
      Set-Item -Path "Env:$($entry.Key)" -Value $entry.Value.Value
    } else {
      Remove-Item -Path "Env:$($entry.Key)" -ErrorAction SilentlyContinue
    }
  }
}

function Get-ProcessIdsForPort {
  param([int]$Port)

  $processIds = @()

  if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    try {
      $processIds += Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop |
        Select-Object -ExpandProperty OwningProcess
    } catch {
    }
  }

  if (-not $processIds) {
    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+\S+\s+(\d+)\s*$"
    $processIds += netstat -ano |
      Select-String -Pattern $pattern |
      ForEach-Object {
        if ($_.Matches.Count -gt 0) {
          [int]$_.Matches[0].Groups[1].Value
        }
      }
  }

  return $processIds |
    Where-Object { $_ -and $_ -ne $PID } |
    Sort-Object -Unique
}

function Get-ProcessesForPort {
  param([int]$Port)

  $processes = @()

  foreach ($processId in @(Get-ProcessIdsForPort -Port $Port)) {
    try {
      $proc = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $processId" -ErrorAction Stop
      $processes += [pscustomobject]@{
        Id             = $processId
        Name           = $proc.Name
        ExecutablePath = $proc.ExecutablePath
        CommandLine    = $proc.CommandLine
      }
      continue
    } catch {
    }

    try {
      $proc = Get-Process -Id $processId -ErrorAction Stop
      $processes += [pscustomobject]@{
        Id             = $processId
        Name           = $proc.ProcessName
        ExecutablePath = $null
        CommandLine    = $null
      }
    } catch {
    }
  }

  return $processes
}

function Test-DockerManagedProcess {
  param([pscustomobject]$ProcessInfo)

  $candidates = @(
    $ProcessInfo.Name
    $ProcessInfo.ExecutablePath
    $ProcessInfo.CommandLine
  ) | Where-Object { $_ }

  foreach ($candidate in $candidates) {
    if ($candidate -match '(?i)docker|com\.docker|dockerdesktoplinuxengine|docker-desktop|docker-proxy|vpnkit') {
      return $true
    }
  }

  return $false
}

function Get-ComposeServicesForPort {
  param([int]$Port)

  $services = @()

  if ($Port -eq $BackendPort) {
    $services += 'm8flow-backend'
  }
  if ($Port -eq $FrontendPort) {
    $services += 'm8flow-frontend'
  }

  return $services
}

function Stop-ProcessesOnPort {
  param([int]$Port)

  $processes = @(Get-ProcessesForPort -Port $Port)
  if (-not $processes) {
    return
  }

  $dockerManaged = @($processes | Where-Object { Test-DockerManagedProcess -ProcessInfo $_ })
  if ($dockerManaged.Count -gt 0) {
    $dockerSummary = $dockerManaged |
      ForEach-Object {
        if ($_.Name) {
          "$($_.Name) (PID $($_.Id))"
        } else {
          "PID $($_.Id)"
        }
      }

    $composeServices = @(Get-ComposeServicesForPort -Port $Port)
    $composeStopExample = if ($composeServices.Count -gt 0) {
      "docker compose -f docker/m8flow-docker-compose.yml stop $($composeServices -join ' ')"
    } else {
      'docker compose ps'
    }

    throw "Port $Port is currently owned by Docker-managed process(es): $($dockerSummary -join ', '). start_dev.ps1 will not kill Docker Desktop listeners because that can disconnect the Docker engine. Stop the Docker service using this port first (for example: $composeStopExample) and then re-run .\start_dev.ps1."
  }

  $processIds = @($processes | Select-Object -ExpandProperty Id)
  Write-Host "Killing existing process(es) on port ${Port}: $($processIds -join ', ')"
  foreach ($processId in $processIds) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 1
}

function Test-PortListening {
  param([int]$Port)

  return @(Get-ProcessIdsForPort -Port $Port).Count -gt 0
}

function Wait-ForProcessToListen {
  param(
    [System.Diagnostics.Process]$Process,
    [int]$Port,
    [int]$TimeoutSeconds = 30
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

  while ((Get-Date) -lt $deadline) {
    $Process.Refresh()
    if ($Process.HasExited) {
      throw "Backend process exited early with code $($Process.ExitCode)."
    }
    if (Test-PortListening -Port $Port) {
      return
    }
    Start-Sleep -Milliseconds 500
  }

  $Process.Refresh()
  if ($Process.HasExited) {
    throw "Backend process exited early with code $($Process.ExitCode)."
  }

  throw "Backend did not start listening on port $Port within $TimeoutSeconds seconds."
}

function Assert-CommandExists {
  param([string]$Name)

  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command '$Name' was not found in PATH."
  }
}

function Assert-FrontendDependencies {
  param([string]$FrontendDir)

  $viteScript = Join-Path $FrontendDir 'node_modules\vite\bin\vite.js'
  if (-not (Test-Path $viteScript)) {
    throw "Vite entrypoint was not found at '$viteScript'. Run 'npm install' in extensions\m8flow-frontend."
  }

  $rollupNativeScript = Join-Path $FrontendDir 'node_modules\rollup\dist\native.js'
  if (-not (Test-Path $rollupNativeScript)) {
    throw "Rollup native loader was not found at '$rollupNativeScript'. Run 'npm install' in extensions\m8flow-frontend."
  }

  $nodeArch = (& node -p process.arch 2>$null | Select-Object -First 1)
  if ($nodeArch) {
    $nodeArch = $nodeArch.Trim()
  }
  $rollupNativePackageDir = switch ($nodeArch) {
    'x64' { Join-Path $FrontendDir 'node_modules\@rollup\rollup-win32-x64-msvc' }
    'arm64' { Join-Path $FrontendDir 'node_modules\@rollup\rollup-win32-arm64-msvc' }
    'ia32' { Join-Path $FrontendDir 'node_modules\@rollup\rollup-win32-ia32-msvc' }
    default { $null }
  }

  if ($rollupNativePackageDir -and -not (Test-Path (Join-Path $rollupNativePackageDir 'package.json'))) {
    throw "Frontend dependencies in 'extensions\m8flow-frontend' are incomplete for this platform. Missing Rollup native package for Node architecture '$nodeArch' at '$rollupNativePackageDir'. Reinstall them on this machine with 'npm install' in extensions\m8flow-frontend. If the problem persists, remove 'extensions\m8flow-frontend\node_modules' and install again."
  }
}

function Convert-DockerRedisUrlToLocalhost {
  param([string]$Url)

  if (-not $Url) {
    return $Url
  }

  return ($Url -replace '^(redis(?:s)?://(?:[^/@]+@)?)redis(?=[:/]|$)', '$1localhost')
}

function Use-LocalDevHostServices {
  $env:M8FLOW_LOCAL_DEV_USE_HOST_SERVICES = 'true'

  foreach ($key in @(
    'M8FLOW_BACKEND_CELERY_BROKER_URL',
    'SPIFFWORKFLOW_BACKEND_CELERY_BROKER_URL',
    'M8FLOW_BACKEND_CELERY_RESULT_BACKEND',
    'SPIFFWORKFLOW_BACKEND_CELERY_RESULT_BACKEND'
  )) {
    $existingItem = Get-Item -Path "Env:$key" -ErrorAction SilentlyContinue
    if (-not $existingItem) {
      continue
    }

    $normalized = Convert-DockerRedisUrlToLocalhost -Url $existingItem.Value
    if ($normalized -ne $existingItem.Value) {
      Set-Item -Path "Env:$key" -Value $normalized
      Write-Host "Using host-reachable $key=$normalized for local dev."
    }
  }
}

$backendProcess = $null
$loadedEnv = @{}
$tempEnvSnapshot = @{}

try {
  Assert-CommandExists -Name 'npm'
  Assert-CommandExists -Name 'node'
  Assert-FrontendDependencies -FrontendDir (Join-Path $root 'extensions\m8flow-frontend')

  $loadedEnv = Load-DotEnv -EnvFilePath (Join-Path $root '.env')
  $tempEnvSnapshot = Get-EnvSnapshot -Keys @(
    'SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP',
    'M8FLOW_BACKEND_RUN_BOOTSTRAP',
    'UVICORN_LOG_LEVEL',
    'M8FLOW_LOCAL_DEV_USE_HOST_SERVICES',
    'M8FLOW_BACKEND_CELERY_BROKER_URL',
    'SPIFFWORKFLOW_BACKEND_CELERY_BROKER_URL',
    'M8FLOW_BACKEND_CELERY_RESULT_BACKEND',
    'SPIFFWORKFLOW_BACKEND_CELERY_RESULT_BACKEND',
    'PORT',
    'BACKEND_PORT',
    'VITE_VERSION_INFO',
    'VITE_BACKEND_BASE_URL',
    'VITE_MULTI_TENANT_ON'
  )
  Use-LocalDevHostServices

  if (-not $env:SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP) {
    $env:SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP = 'false'
  }

  Stop-ProcessesOnPort -Port $BackendPort

  $powershellExe = Join-Path $PSHOME 'powershell.exe'
  $rootLiteral = Quote-PowerShellLiteral $root
  $spiffRoot = Join-Path $root 'spiffworkflow-backend'
  $spiffRootLiteral = Quote-PowerShellLiteral $spiffRoot
  $backendScriptLiteral = Quote-PowerShellLiteral (Join-Path $root 'extensions\m8flow-backend\bin\run_m8flow_backend.ps1')

  if (Test-Path (Join-Path $root 'extensions/app.py')) {
    Write-Host "Starting backend (extensions app) on port $BackendPort in background..."
    $env:M8FLOW_BACKEND_RUN_BOOTSTRAP = if ($env:M8FLOW_BACKEND_RUN_BOOTSTRAP) {
      $env:M8FLOW_BACKEND_RUN_BOOTSTRAP
    } else {
      'false'
    }
    $env:UVICORN_LOG_LEVEL = if ($env:UVICORN_LOG_LEVEL) {
      $env:UVICORN_LOG_LEVEL
    } else {
      'debug'
    }
    $backendCommand = @"
`$ErrorActionPreference = 'Stop'
Set-Location ${rootLiteral}
& ${backendScriptLiteral} -Port $BackendPort -Reload
"@
  } else {
    Write-Host "Starting backend (Keycloak mode) on port $BackendPort in background..."
    $backendCommand = @"
`$ErrorActionPreference = 'Stop'
Set-Location ${spiffRootLiteral}
`$env:PORT = '$BackendPort'
if (-not `$env:UVICORN_LOG_LEVEL) { `$env:UVICORN_LOG_LEVEL = 'debug' }
if (`$env:SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP -ne 'false') {
  `$env:SPIFFWORKFLOW_BACKEND_RUN_BACKGROUND_SCHEDULER_IN_CREATE_APP = 'false'
  uv run python bin/refresh_all_caches.py
}
uv run python bin/bootstrap.py
uv run uvicorn spiff_web_server:connexion_app --reload --host 0.0.0.0 --port $BackendPort --workers 1 --log-level `$env:UVICORN_LOG_LEVEL
"@
  }

  $backendProcess = Start-Process -FilePath $powershellExe `
    -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $backendCommand) `
    -WorkingDirectory $root `
    -NoNewWindow `
    -PassThru

  Write-Host "Waiting for backend to start listening on port $BackendPort..."
  Wait-ForProcessToListen -Process $backendProcess -Port $BackendPort

  Stop-ProcessesOnPort -Port $FrontendPort

  Write-Host 'Starting frontend (Ctrl+C to stop both)...'
  if (Test-Path (Join-Path $root 'extensions/app.py')) {
    Set-Location (Join-Path $root 'extensions\m8flow-frontend')
    Write-Host 'Using extensions frontend (tenant gate, MULTI_TENANT_ON from .env)'
    $env:PORT = $FrontendPort.ToString()
    $env:BACKEND_PORT = $BackendPort.ToString()
    $env:VITE_VERSION_INFO = '{"version":"local"}'
    $env:VITE_BACKEND_BASE_URL = '/v1.0'
    $env:VITE_MULTI_TENANT_ON = if ($env:MULTI_TENANT_ON) { $env:MULTI_TENANT_ON } else { 'false' }
    $viteScript = Join-Path $root 'extensions\m8flow-frontend\node_modules\vite\bin\vite.js'
    & node $viteScript '--host' '0.0.0.0' '--port' $FrontendPort.ToString()
  } else {
    Set-Location (Join-Path $root 'spiffworkflow-frontend')
    npm start
  }
} finally {
  if ($backendProcess) {
    try {
      if (-not $backendProcess.HasExited) {
        Write-Host "Stopping backend (PID $($backendProcess.Id))..."
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
      }
    } catch {
    }
  }

  Restore-EnvSnapshot -Snapshot $tempEnvSnapshot
  Restore-DotEnv -OriginalValues $loadedEnv

  if ($locationPushed) {
    Pop-Location
  }
}
