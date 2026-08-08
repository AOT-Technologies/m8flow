#requires -Version 5.1

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$composeFile = Join-Path $repoRoot 'docker\m8flow-docker-compose.yml'
$policyTemplate = Join-Path $repoRoot 'docker\vault\policies\m8flow-policy.hcl.tpl'

$vaultService = if ($env:M8FLOW_VAULT_SERVICE_NAME) { $env:M8FLOW_VAULT_SERVICE_NAME } else { 'vault' }
$vaultAddr = if ($env:M8FLOW_VAULT_INTERNAL_ADDR) { $env:M8FLOW_VAULT_INTERNAL_ADDR } else { 'http://127.0.0.1:8200' }
$mountPoint = if ($env:M8FLOW_VAULT_MOUNT_POINT) { $env:M8FLOW_VAULT_MOUNT_POINT } else { 'kv' }
$pathPrefix = if ($env:M8FLOW_VAULT_SECRET_PATH_PREFIX) { $env:M8FLOW_VAULT_SECRET_PATH_PREFIX } else { 'm8flow' }
$policyName = if ($env:M8FLOW_VAULT_POLICY_NAME) { $env:M8FLOW_VAULT_POLICY_NAME } else { 'm8flow' }
$operatorToken = if ($env:M8FLOW_VAULT_OPERATOR_TOKEN) { $env:M8FLOW_VAULT_OPERATOR_TOKEN } elseif ($env:VAULT_TOKEN) { $env:VAULT_TOKEN } else { '' }

function Invoke-Compose {
  param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
  )

  & docker compose -f $composeFile @Arguments
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Required command 'docker' is not available."
}

if (-not (Test-Path $composeFile)) {
  throw "Compose file not found at $composeFile."
}

if (-not (Test-Path $policyTemplate)) {
  throw "Policy template not found at $policyTemplate."
}

if (-not $operatorToken) {
  throw "Set M8FLOW_VAULT_OPERATOR_TOKEN (or VAULT_TOKEN) to an authorized operator token."
}

$statusOutput = Invoke-Compose exec -T $vaultService sh -lc "VAULT_ADDR='$vaultAddr' vault status -format=json" 2>&1
$statusCode = $LASTEXITCODE

try {
  $status = ($statusOutput -join [Environment]::NewLine) | ConvertFrom-Json
} catch {
  if ($statusCode -ne 0) {
    throw "Could not query Vault status from service '$vaultService'. Output: $($statusOutput -join [Environment]::NewLine)"
  }
  throw
}

if (-not $status.initialized) {
  throw "Vault is not initialized. Run 'docker compose -f docker/m8flow-docker-compose.yml exec vault vault operator init' first."
}

if ($status.sealed) {
  throw "Vault is sealed. Unseal it before running this script."
}

$env:VAULT_ADDR = $vaultAddr
$env:VAULT_TOKEN = $operatorToken
$env:MOUNT_POINT = $mountPoint
$env:POLICY_NAME = $policyName

Invoke-Compose exec -T -e VAULT_ADDR -e VAULT_TOKEN $vaultService sh -lc 'vault token lookup >/dev/null'
if ($LASTEXITCODE -ne 0) {
  throw "The supplied operator token is missing or not authorized for Vault administration."
}

$mountsOutput = Invoke-Compose exec -T -e VAULT_ADDR -e VAULT_TOKEN $vaultService sh -lc 'vault secrets list -format=json' 2>&1
if ($LASTEXITCODE -ne 0) {
  throw "Could not read mounted secrets engines. Output: $($mountsOutput -join [Environment]::NewLine)"
}

$mounts = ($mountsOutput -join [Environment]::NewLine) | ConvertFrom-Json
$mountKey = '{0}/' -f $mountPoint.TrimEnd('/')
$mountEntry = $mounts.PSObject.Properties | Where-Object { $_.Name -eq $mountKey } | Select-Object -First 1

if (-not $mountEntry) {
  Invoke-Compose exec -T -e VAULT_ADDR -e VAULT_TOKEN -e MOUNT_POINT $vaultService sh -lc 'vault secrets enable -path="$MOUNT_POINT" -version=2 kv' | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Could not enable KV v2 mount '$mountPoint'."
  }
  Write-Host "configure-m8flow-vault: enabled KV v2 mount '$mountPoint'."
} else {
  Write-Host "configure-m8flow-vault: KV mount '$mountPoint' already exists."
}

$policyText = Get-Content -Path $policyTemplate -Raw
$policyText = $policyText.Replace('__MOUNT_POINT__', $mountPoint.Trim('/'))
$policyText = $policyText.Replace('__PATH_PREFIX__', $pathPrefix.Trim('/'))

$tempPolicyFile = [System.IO.Path]::GetTempFileName()
try {
  Set-Content -Path $tempPolicyFile -Value $policyText -NoNewline
  Get-Content -Path $tempPolicyFile -Raw | & docker compose -f $composeFile exec -T -e VAULT_ADDR -e VAULT_TOKEN -e POLICY_NAME $vaultService sh -lc 'vault policy write "$POLICY_NAME" -' | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Could not write policy '$policyName'."
  }
} finally {
  Remove-Item -Path $tempPolicyFile -ErrorAction SilentlyContinue
}

Write-Host "configure-m8flow-vault: wrote policy '$policyName' for mount '$mountPoint' and prefix '$pathPrefix'."
Write-Host ''
Write-Host 'Next steps:'
Write-Host '1. For the development-only AppRole + demo-seeding flow, run:'
Write-Host '   docker compose -f docker/m8flow-docker-compose.yml --profile vault --profile vault-demo up -d --build'
Write-Host '2. Or create a non-root application token with that policy manually, for example:'
Write-Host "   docker compose -f docker/m8flow-docker-compose.yml exec vault sh -lc 'VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=`$M8FLOW_VAULT_OPERATOR_TOKEN vault token create -policy=$policyName -display-name=m8flow-local -ttl=24h -renewable=true'"
Write-Host '3. Save the returned token outside source control and add these lines to your local .env:'
Write-Host '   M8FLOW_VAULT_ENABLED=true'
Write-Host '   M8FLOW_VAULT_ADDR=http://vault:8200'
Write-Host '   M8FLOW_VAULT_TOKEN=<application token>'
Write-Host "   M8FLOW_VAULT_MOUNT_POINT=$mountPoint"
Write-Host "   M8FLOW_VAULT_SECRET_PATH_PREFIX=$pathPrefix"
Write-Host '4. Restart the backend and Celery services after Vault is unsealed and the app token is configured.'
