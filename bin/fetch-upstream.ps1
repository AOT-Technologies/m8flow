#requires -Version 5.1
# bin/fetch-upstream.ps1
# Fetches upstream directories into the local working tree.
#
# Usage: .\bin\fetch-upstream.ps1 [tag]
#   tag: git tag or branch name (default tag from upstream.sources.json)

[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [string]$Tag
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FullPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  return [System.IO.Path]::GetFullPath($Path)
}

function Assert-PathWithinRoot {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Root,
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [Parameter(Mandatory = $true)]
    [string]$Label
  )

  $normalizedRoot = (Get-FullPath -Path $Root).TrimEnd("\", "/")
  $normalizedPath = Get-FullPath -Path $Path
  $rootPrefix = $normalizedRoot + [System.IO.Path]::DirectorySeparatorChar

  if (
    $normalizedPath -ne $normalizedRoot -and
    -not $normalizedPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)
  ) {
    throw "$Label path '$normalizedPath' is outside '$normalizedRoot'."
  }
}

function Convert-ToNativeRelativePath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  return ($Path -replace "[\\/]+", [System.IO.Path]::DirectorySeparatorChar)
}

function Invoke-Git {
  param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
  )

  & git @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
  }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$repoRootPath = Get-FullPath -Path $repoRoot
$configPath = Join-Path $repoRootPath "upstream.sources.json"
$tempRoot = $null

try {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is required but not installed. Please install git and retry."
  }

  if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Missing upstream config file: $configPath"
  }

  $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
  $upstreamUrl = [string]$config.upstream_url
  $defaultUpstreamTag = [string]$config.upstream_ref
  $resolvedUpstreamTag = if ([string]::IsNullOrWhiteSpace($Tag)) { $defaultUpstreamTag } else { $Tag }

  $dirs = @(
    @($config.backend) +
    @($config.frontend) +
    @($config.others) |
      Where-Object { $_ -is [string] -and -not [string]::IsNullOrWhiteSpace($_) } |
      Sort-Object -Unique
  )

  if ([string]::IsNullOrWhiteSpace($upstreamUrl) -or $upstreamUrl -eq "null") {
    throw "Invalid upstream_url in $configPath"
  }

  if ([string]::IsNullOrWhiteSpace($resolvedUpstreamTag) -or $resolvedUpstreamTag -eq "null") {
    throw "upstream_ref is missing or null in $configPath"
  }

  if ($dirs.Count -eq 0) {
    throw "No folders configured in backend/frontend/others of $configPath"
  }

  $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("m8flow-fetch-upstream-" + [System.IO.Path]::GetRandomFileName())
  $null = New-Item -Path $tempRoot -ItemType Directory
  $cloneDir = Join-Path $tempRoot "upstream"

  Write-Host "Fetching upstream $upstreamUrl @ $resolvedUpstreamTag ..."
  Invoke-Git clone --no-local --depth 1 --filter=blob:none --sparse --branch $resolvedUpstreamTag $upstreamUrl $cloneDir

  Push-Location $cloneDir
  try {
    Invoke-Git sparse-checkout set @dirs
    # Avoid piping native command output through PowerShell cmdlets here:
    # that can change $LASTEXITCODE to -1 even when git succeeds.
    $fetchedSha = [string]::Join("`n", (& git rev-parse HEAD)).Trim()
    if ($LASTEXITCODE -ne 0) {
      throw "git rev-parse HEAD failed with exit code $LASTEXITCODE."
    }
  }
  finally {
    Pop-Location
  }

  foreach ($dir in $dirs) {
    $nativeRelativeDir = Convert-ToNativeRelativePath -Path $dir
    $sourceDir = Join-Path $cloneDir $nativeRelativeDir
    $destinationDir = Join-Path $repoRootPath $nativeRelativeDir
    $destinationParent = Split-Path -Parent $destinationDir

    Assert-PathWithinRoot -Root $repoRootPath -Path $destinationDir -Label "Destination"

    if (-not (Test-Path -LiteralPath $sourceDir -PathType Container)) {
      throw "Expected upstream directory '$dir' was not found in the sparse checkout."
    }

    if (-not (Test-Path -LiteralPath $destinationParent -PathType Container)) {
      $null = New-Item -Path $destinationParent -ItemType Directory -Force
    }

    Write-Host "Copying $dir/ ..."
    if (Test-Path -LiteralPath $destinationDir) {
      Remove-Item -LiteralPath $destinationDir -Recurse -Force
    }
    Copy-Item -LiteralPath $sourceDir -Destination $destinationDir -Recurse
  }

  Write-Host ""
  Write-Host "Done. Upstream SHA: $fetchedSha"
  Write-Host "Record this SHA to track which upstream version is in use."
  Write-Host "Upstream directories are gitignored - do not commit them."
}
catch {
  Write-Error $_.Exception.Message
  exit 1
}
finally {
  if ($tempRoot -and (Test-Path -LiteralPath $tempRoot)) {
    Assert-PathWithinRoot -Root ([System.IO.Path]::GetTempPath()) -Path $tempRoot -Label "Temporary"
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
  }
}
