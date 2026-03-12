#requires -Version 5.1

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$proxyRoot = Split-Path -Parent $scriptDir
Set-Location $proxyRoot

if (-not $env:FLASK_DEBUG) {
  $env:FLASK_DEBUG = "1"
}

$env:FLASK_SESSION_SECRET_KEY = "super_secret_key"

$port = if ($env:CONNECTOR_PROXY_PORT) { $env:CONNECTOR_PROXY_PORT } else { "7004" }

poetry run flask run -p $port --host=0.0.0.0
