[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$NodeWireRoot,
    [string]$NodeWireVersion = '1.0.0'
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

if (-not (Test-Path -LiteralPath $stageDir -PathType Container)) {
    New-Item -ItemType Directory -Path $stageDir | Out-Null
}

if ($PSCmdlet.ShouldProcess($stageDir, 'Replace staged wheel files')) {
    Get-ChildItem -LiteralPath $stageDir -Filter '*.whl' -File | Remove-Item -Force
    Copy-Item -LiteralPath $runtimeWheels.FullName -Destination $stageDir -Force
    Copy-Item -LiteralPath $httpGenericWheels.FullName -Destination $stageDir -Force
}

Write-Output "Staged wheels into $stageDir"
Get-ChildItem -LiteralPath $stageDir -Filter '*.whl' -File |
    Sort-Object Name |
    Select-Object -ExpandProperty Name
