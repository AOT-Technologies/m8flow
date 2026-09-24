[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$NodeWireRoot,
    [string]$NodeWireVersion = '1.1.0'
)

$ErrorActionPreference = 'Stop'

$proxyRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repoRoot = (Resolve-Path (Join-Path $proxyRoot '..')).Path

if ([string]::IsNullOrWhiteSpace($NodeWireRoot)) {
    $NodeWireRoot = Join-Path (Split-Path $repoRoot -Parent) 'node-wire'
}
$NodeWireRoot = (Resolve-Path $NodeWireRoot).Path

$stageDir = Join-Path $proxyRoot 'vendor\wheels'
$runtimeDist = Join-Path $NodeWireRoot 'packages\runtime\dist'
$httpGenericDist = Join-Path $NodeWireRoot 'packages\connectors\http_generic\dist'

if (-not (Test-Path -LiteralPath $runtimeDist -PathType Container) -or
    -not (Test-Path -LiteralPath $httpGenericDist -PathType Container)) {
    throw "node-wire package dist directories were not found under '$NodeWireRoot'. Build the packages first or pass -NodeWireRoot <path>."
}

$runtimeWheels = @(Get-ChildItem -LiteralPath $runtimeDist -Filter "node_wire_runtime-$NodeWireVersion-*.whl" -File)
$httpGenericWheels = @(Get-ChildItem -LiteralPath $httpGenericDist -Filter "node_wire_http_generic-$NodeWireVersion-*.whl" -File)

if ($runtimeWheels.Count -eq 0 -or $httpGenericWheels.Count -eq 0) {
    throw @"
Required $NodeWireVersion wheels were not found.
Build them in '$NodeWireRoot' with:
  ./scripts/build-packages.sh packages/runtime packages/connectors/http_generic
"@
}

# The m8flow connectors version independently of the runtime, so each is taken
# at whatever version its own dist holds rather than $NodeWireVersion. Newest
# per package: a rebuild leaves the previous wheel behind in dist/.
$m8flowPackages = @(
    'm8flow_github', 'm8flow_n8n', 'm8flow_smtp', 'm8flow_slack',
    'm8flow_salesforce', 'm8flow_stripe', 'm8flow_postgres'
)
$m8flowWheels = @()
$missing = @()
foreach ($package in $m8flowPackages) {
    $dist = Join-Path $NodeWireRoot "packages\connectors\$package\dist"
    $wheel = $null
    if (Test-Path -LiteralPath $dist -PathType Container) {
        $wheel = Get-ChildItem -LiteralPath $dist -Filter "node_wire_$package-*.whl" -File |
            Sort-Object LastWriteTime |
            Select-Object -Last 1
    }
    if ($null -eq $wheel) { $missing += $package } else { $m8flowWheels += $wheel }
}
if ($missing.Count -gt 0) {
    throw @"
No wheel found for: $($missing -join ', ')
Build them in '$NodeWireRoot', e.g.:
  docker run --rm -e HOME=/tmp -v "${NodeWireRoot}:/work" ``
    -w "/work/packages/connectors/<name>" ``
    nw-wheel-builder:local python -m build --wheel --no-isolation
"@
}

if (-not (Test-Path -LiteralPath $stageDir -PathType Container)) {
    New-Item -ItemType Directory -Path $stageDir | Out-Null
}

if ($PSCmdlet.ShouldProcess($stageDir, 'Replace staged wheel files')) {
    # Clear first so the staged set stays internally consistent: a leftover
    # wheel from an older build would otherwise be installed alongside.
    Get-ChildItem -LiteralPath $stageDir -Filter '*.whl' -File | Remove-Item -Force
    Copy-Item -LiteralPath $runtimeWheels.FullName -Destination $stageDir -Force
    Copy-Item -LiteralPath $httpGenericWheels.FullName -Destination $stageDir -Force
    foreach ($wheel in $m8flowWheels) {
        Copy-Item -LiteralPath $wheel.FullName -Destination $stageDir -Force
    }
}

Write-Output "Staged wheels into $stageDir"
Get-ChildItem -LiteralPath $stageDir -Filter '*.whl' -File |
    Sort-Object Name |
    Select-Object -ExpandProperty Name
