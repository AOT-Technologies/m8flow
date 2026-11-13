#requires -Version 5.1

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$composeFile = Join-Path $repoRoot 'docker\m8flow-docker-compose.yml'
$policyTemplate = Join-Path $repoRoot 'docker\vault\policies\m8flow-policy.hcl.tpl'
$runtimePolicyTemplate = Join-Path $repoRoot 'docker\vault\policies\m8flow-runtime-policy.hcl.tpl'

$vaultService = if ($env:M8FLOW_VAULT_SERVICE_NAME) { $env:M8FLOW_VAULT_SERVICE_NAME } else { 'vault' }
$vaultAddr = if ($env:M8FLOW_VAULT_INTERNAL_ADDR) { $env:M8FLOW_VAULT_INTERNAL_ADDR } else { 'http://127.0.0.1:8200' }
$mountPoint = if ($env:M8FLOW_VAULT_MOUNT_POINT) { $env:M8FLOW_VAULT_MOUNT_POINT } else { 'kv' }
$pathPrefix = if ($env:M8FLOW_VAULT_SECRET_PATH_PREFIX) { $env:M8FLOW_VAULT_SECRET_PATH_PREFIX } else { 'm8flow' }
$approleMountPoint = if ($env:M8FLOW_VAULT_APPROLE_MOUNT_POINT) { $env:M8FLOW_VAULT_APPROLE_MOUNT_POINT } else { 'approle' }
$tenantPolicyPrefix = if ($env:M8FLOW_VAULT_TENANT_POLICY_PREFIX) { $env:M8FLOW_VAULT_TENANT_POLICY_PREFIX } else { 'm8flow-tenant-policy' }
$tenantRolePrefix = if ($env:M8FLOW_VAULT_TENANT_ROLE_PREFIX) { $env:M8FLOW_VAULT_TENANT_ROLE_PREFIX } else { 'm8flow-tenant-role' }
$policyName = if ($env:M8FLOW_VAULT_POLICY_NAME) { $env:M8FLOW_VAULT_POLICY_NAME } else { 'm8flow' }
$runtimePolicyName = if ($env:M8FLOW_VAULT_RUNTIME_POLICY_NAME) { $env:M8FLOW_VAULT_RUNTIME_POLICY_NAME } else { 'm8flow-runtime' }
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
  throw "Provisioner policy template not found at $policyTemplate."
}

if (-not (Test-Path $runtimePolicyTemplate)) {
  throw "Runtime policy template not found at $runtimePolicyTemplate."
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
$env:RUNTIME_POLICY_NAME = $runtimePolicyName

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
$policyText = $policyText.Replace('__APPROLE_MOUNT_POINT__', $approleMountPoint.Trim('/'))
$policyText = $policyText.Replace('__TENANT_POLICY_PREFIX__', $tenantPolicyPrefix.Trim('/'))
$policyText = $policyText.Replace('__TENANT_ROLE_PREFIX__', $tenantRolePrefix.Trim('/'))
$runtimePolicyText = Get-Content -Path $runtimePolicyTemplate -Raw
$runtimePolicyText = $runtimePolicyText.Replace('__APPROLE_MOUNT_POINT__', $approleMountPoint.Trim('/'))
$runtimePolicyText = $runtimePolicyText.Replace('__TENANT_ROLE_PREFIX__', $tenantRolePrefix.Trim('/'))

$tempPolicyFile = [System.IO.Path]::GetTempFileName()
$tempRuntimePolicyFile = [System.IO.Path]::GetTempFileName()
try {
  Set-Content -Path $tempPolicyFile -Value $policyText -NoNewline
  Get-Content -Path $tempPolicyFile -Raw | & docker compose -f $composeFile exec -T -e VAULT_ADDR -e VAULT_TOKEN -e POLICY_NAME $vaultService sh -lc 'vault policy write "$POLICY_NAME" -' | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Could not write policy '$policyName'."
  }
  Set-Content -Path $tempRuntimePolicyFile -Value $runtimePolicyText -NoNewline
  Get-Content -Path $tempRuntimePolicyFile -Raw | & docker compose -f $composeFile exec -T -e VAULT_ADDR -e VAULT_TOKEN -e RUNTIME_POLICY_NAME $vaultService sh -lc 'vault policy write "$RUNTIME_POLICY_NAME" -' | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Could not write runtime policy '$runtimePolicyName'."
  }
} finally {
  Remove-Item -Path $tempPolicyFile -ErrorAction SilentlyContinue
  Remove-Item -Path $tempRuntimePolicyFile -ErrorAction SilentlyContinue
}

Write-Host "configure-m8flow-vault: wrote provisioner policy '$policyName' and runtime policy '$runtimePolicyName'."
Write-Host ''
Write-Host 'Next steps:'
Write-Host '1. For the development-only AppRole + demo-seeding flow, run:'
Write-Host '   docker compose -f docker/m8flow-docker-compose.yml -f docker/m8flow-docker-compose.vault.yml --profile vault --profile vault-demo up -d --build'
Write-Host "2. Create separate workload AppRoles: the provisioner role receives '$policyName'; the backend/worker runtime role receives '$runtimePolicyName'."
Write-Host '3. Never mount the provisioner credential in backend or worker containers. Give the provisioner its own identity and internal API request token.'
Write-Host '4. Keep the provisioner service on a private network and use TLS for remote deployment traffic.'
Write-Host '5. The Vault override file selects the Vault backend and sets its local address.'
Write-Host "   M8FLOW_VAULT_MOUNT_POINT=$mountPoint"
Write-Host "   M8FLOW_VAULT_SECRET_PATH_PREFIX=$pathPrefix"
Write-Host "   M8FLOW_VAULT_APPROLE_MOUNT_POINT=$approleMountPoint"
Write-Host "   M8FLOW_VAULT_TENANT_POLICY_PREFIX=$tenantPolicyPrefix"
Write-Host "   M8FLOW_VAULT_TENANT_ROLE_PREFIX=$tenantRolePrefix"
Write-Host '6. Restart the backend, workers, and provisioner after Vault credentials are configured.'
Write-Host '7. The runtime identity can mint tenant tokens but cannot edit tenant policies or roles.'
