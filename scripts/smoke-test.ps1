$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:1899'
$health = Invoke-RestMethod -Uri "$base/api/v1/health" -TimeoutSec 10
$overview = Invoke-RestMethod -Uri "$base/api/v1/dashboard/overview" -TimeoutSec 10
$page = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 10
if ($health.status -ne 'ok') { throw 'Health endpoint failed.' }
if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'WiseFX AI') { throw 'Frontend failed.' }
Write-Host "OK: frontend=$($page.StatusCode), API=$($health.status), action=$($overview.decision.action)"
