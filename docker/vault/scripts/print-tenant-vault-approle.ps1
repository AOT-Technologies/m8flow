#requires -Version 5.1

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$Tenant,

  [string]$VaultUiBaseUrl
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$composeFile = Join-Path $repoRoot 'docker\m8flow-docker-compose.yml'

$vaultService = if ($env:M8FLOW_VAULT_SERVICE_NAME) { $env:M8FLOW_VAULT_SERVICE_NAME } else { 'vault' }
$dbService = if ($env:M8FLOW_DB_SERVICE_NAME) { $env:M8FLOW_DB_SERVICE_NAME } else { 'm8flow-db' }
$backendService = if ($env:M8FLOW_BACKEND_SERVICE_NAME) { $env:M8FLOW_BACKEND_SERVICE_NAME } else { 'm8flow-backend' }
$postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { 'postgres' }
$postgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { 'postgres' }
$pathPrefix = if ($env:M8FLOW_VAULT_SECRET_PATH_PREFIX) { $env:M8FLOW_VAULT_SECRET_PATH_PREFIX } else { 'm8flow' }
$tenantRolePrefix = if ($env:M8FLOW_VAULT_TENANT_ROLE_PREFIX) { $env:M8FLOW_VAULT_TENANT_ROLE_PREFIX } else { 'm8flow-tenant-role' }

function Invoke-Compose {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  & docker compose -f $composeFile @Arguments
}

function Normalize-VaultUiBaseUrl {
  param(
    [Parameter(Mandatory = $true)]
    [string]$RawValue
  )

  $normalized = $RawValue.Trim()
  if (-not $normalized) {
    throw 'Vault UI base URL must not be empty.'
  }

  if ($normalized -notmatch '^[a-z]+://') {
    $normalized = "http://$normalized"
  }

  return $normalized -replace '://0\.0\.0\.0:', '://127.0.0.1:'
}

function Join-VaultPath {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Parts
  )

  $normalizedParts = foreach ($part in $Parts) {
    $trimmed = ([string]$part).Trim().Trim('/')
    if ($trimmed) {
      $trimmed
    }
  }

  return ($normalizedParts -join '/')
}

function Get-SanitizedVaultNameComponent {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Value
  )

  $normalized = $Value.Trim()
  if (-not $normalized) {
    throw 'Vault name component must not be empty.'
  }

  $sanitized = [regex]::Replace($normalized, '[^A-Za-z0-9._-]+', '-').Trim('.', '-')
  if (-not $sanitized) {
    throw "Vault name component '$Value' does not contain any Vault-safe characters."
  }

  return $sanitized
}

function Resolve-VaultUiBaseUrl {
  if ($VaultUiBaseUrl) {
    return Normalize-VaultUiBaseUrl -RawValue $VaultUiBaseUrl
  }

  $portOutput = Invoke-Compose -Arguments @('port', $vaultService, '8200') 2>$null
  if ($LASTEXITCODE -eq 0 -and $portOutput) {
    $hostPort = ($portOutput | Select-Object -Last 1).Trim()
    if ($hostPort) {
      return Normalize-VaultUiBaseUrl -RawValue $hostPort
    }
  }

  $defaultPort = if ($env:M8FLOW_VAULT_PORT) { $env:M8FLOW_VAULT_PORT } else { '8200' }
  return Normalize-VaultUiBaseUrl -RawValue "127.0.0.1:$defaultPort"
}

function Resolve-OperatorToken {
  if ($env:M8FLOW_VAULT_OPERATOR_TOKEN) {
    return $env:M8FLOW_VAULT_OPERATOR_TOKEN
  }

  if ($env:VAULT_TOKEN) {
    return $env:VAULT_TOKEN
  }

  $initJsonOutput = $null
  try {
    $initJsonOutput = Invoke-Compose -Arguments @('exec', '-T', $backendService, 'sh', '-c', 'cat /vault/demo/init.json') 2>$null
  } catch {
    $initJsonOutput = $null
  }

  if (-not $initJsonOutput) {
    try {
      $initJsonOutput = Invoke-Compose -Arguments @('run', '--rm', '--no-deps', $backendService, 'sh', '-c', 'cat /vault/demo/init.json') 2>$null
    } catch {
      $initJsonOutput = $null
    }
  }

  if (-not $initJsonOutput) {
    throw 'Could not resolve an operator token. Set M8FLOW_VAULT_OPERATOR_TOKEN (or VAULT_TOKEN), or run the local vault-demo bootstrap first.'
  }

  $initPayload = ($initJsonOutput -join [Environment]::NewLine) | ConvertFrom-Json
  if (-not $initPayload.root_token) {
    throw 'The local Vault demo init payload did not contain a root_token.'
  }

  return [string]$initPayload.root_token
}

function Get-TenantRow {
  param(
    [Parameter(Mandatory = $true)]
    [string]$TenantIdentifier
  )

  $tenantRows = Invoke-Compose -Arguments @(
    'exec',
    '-T',
    $dbService,
    'psql',
    '-U',
    $postgresUser,
    '-d',
    $postgresDb,
    '-At',
    '-F',
    '|',
    '-c',
    'select id, name, slug from m8flow_tenant order by created_at_in_seconds desc;'
  )
  if ($LASTEXITCODE -ne 0) {
    throw "Could not query tenants from service '$dbService'."
  }

  $normalizedLookup = $TenantIdentifier.Trim().ToLowerInvariant()
  foreach ($tenantRow in $tenantRows) {
    $line = [string]$tenantRow
    if (-not $line.Trim()) {
      continue
    }

    $parts = $line.Split('|')
    if ($parts.Count -lt 3) {
      continue
    }

    $tenantId = $parts[0].Trim()
    $tenantName = $parts[1].Trim()
    $tenantSlug = $parts[2].Trim()

    if ($normalizedLookup -eq $tenantId.ToLowerInvariant() -or
        $normalizedLookup -eq $tenantSlug.ToLowerInvariant() -or
        $normalizedLookup -eq $tenantName.ToLowerInvariant()) {
      return [pscustomobject]@{
        Id = $tenantId
        Name = $tenantName
        Slug = $tenantSlug
      }
    }
  }

  throw "Tenant '$TenantIdentifier' was not found in m8flow_tenant."
}

function Get-TenantVaultMetadata {
  param(
    [Parameter(Mandatory = $true)]
    [string]$TenantId
  )

  $roleName = '{0}-{1}' -f (Get-SanitizedVaultNameComponent -Value $tenantRolePrefix), (Get-SanitizedVaultNameComponent -Value $TenantId)
  return [pscustomobject]@{
    RoleName = $roleName
    BootstrapPath = Join-VaultPath -Parts @($pathPrefix, 'tenants', $TenantId, 'bootstrap')
    SecretsPath = Join-VaultPath -Parts @($pathPrefix, 'tenants', $TenantId, 'secrets')
  }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Required command 'docker' is not available."
}

if (-not (Test-Path $composeFile)) {
  throw "Compose file not found at $composeFile."
}

$tenantRow = Get-TenantRow -TenantIdentifier $Tenant
$tenantMetadata = Get-TenantVaultMetadata -TenantId $tenantRow.Id
$resolvedOperatorToken = Resolve-OperatorToken
$resolvedVaultUiBaseUrl = Resolve-VaultUiBaseUrl

$roleIdOutput = Invoke-Compose -Arguments @(
  'exec',
  '-T',
  '-e',
  'VAULT_ADDR=http://127.0.0.1:8200',
  '-e',
  "VAULT_TOKEN=$resolvedOperatorToken",
  '-e',
  "VAULT_ROLE_NAME=$($tenantMetadata.RoleName)",
  $vaultService,
  'sh',
  '-c',
  'vault read -field=role_id "auth/approle/role/$VAULT_ROLE_NAME/role-id"'
)
if ($LASTEXITCODE -ne 0) {
  throw "Could not read role_id for tenant AppRole '$($tenantMetadata.RoleName)'."
}
$roleId = ($roleIdOutput -join [Environment]::NewLine).Trim()

$secretIdOutput = Invoke-Compose -Arguments @(
  'exec',
  '-T',
  '-e',
  'VAULT_ADDR=http://127.0.0.1:8200',
  '-e',
  "VAULT_TOKEN=$resolvedOperatorToken",
  '-e',
  "VAULT_ROLE_NAME=$($tenantMetadata.RoleName)",
  $vaultService,
  'sh',
  '-c',
  'vault write -f -field=secret_id "auth/approle/role/$VAULT_ROLE_NAME/secret-id"'
)
if ($LASTEXITCODE -ne 0) {
  throw "Could not generate a secret_id for tenant AppRole '$($tenantMetadata.RoleName)'."
}
$secretId = ($secretIdOutput -join [Environment]::NewLine).Trim()

$authUrl = "$resolvedVaultUiBaseUrl/ui/vault/auth?with=approle"
$bootstrapUrl = "$resolvedVaultUiBaseUrl/ui/vault/secrets/kv/show/$($tenantMetadata.BootstrapPath)"
$secretsUrl = "$resolvedVaultUiBaseUrl/ui/vault/secrets/kv/list/$($tenantMetadata.SecretsPath)/"

Write-Host "tenant_name=$($tenantRow.Name)"
Write-Host "tenant_slug=$($tenantRow.Slug)"
Write-Host "tenant_id=$($tenantRow.Id)"
Write-Host "role_name=$($tenantMetadata.RoleName)"
Write-Host "role_id=$roleId"
Write-Host "secret_id=$secretId"
Write-Host "approle_auth_url=$authUrl"
Write-Host "bootstrap_url=$bootstrapUrl"
Write-Host "tenant_secrets_url=$secretsUrl"
Write-Host ''
Write-Host 'This script minted a fresh tenant AppRole secret_id for local use.'
Write-Host 'Use the AppRole auth method in the Vault UI and sign in with:'
Write-Host "  Role ID:   $roleId"
Write-Host "  Secret ID: $secretId"
