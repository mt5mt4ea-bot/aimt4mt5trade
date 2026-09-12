$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot 'server\.env'
$webIndex = Join-Path $projectRoot 'web\dist\client\index.html'

if (-not (Test-Path -LiteralPath $envPath)) {
  throw 'Missing server/.env. Run scripts/init-config.ps1 first.'
}
if (-not (Test-Path -LiteralPath $webIndex)) {
  throw 'Missing frontend build. Run scripts/build.ps1 first.'
}

Push-Location $projectRoot
try {
  python -m uvicorn server.app.main:app --host 0.0.0.0 --port 1899
} finally {
  Pop-Location
}

