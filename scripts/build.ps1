$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $projectRoot 'web')
try {
  npm ci
  $nodeMajor = [int]((node --version).TrimStart('v').Split('.')[0])
  if ($nodeMajor -ge 24) {
    # Vinext export currently hits a Windows libuv shutdown assertion on Node 24
    # after producing valid output. Build with its supported Node 22 runtime.
    npm exec --yes --package=node@22 -- node node_modules/vinext/dist/cli.js build
  } else {
    npm run build
  }
} finally {
  Pop-Location
}
python -m pip install -r (Join-Path $projectRoot 'server\requirements.txt')
Write-Host 'Build completed.'
