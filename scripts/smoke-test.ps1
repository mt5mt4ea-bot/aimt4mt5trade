$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:1899'
$health = Invoke-RestMethod -Uri "$base/api/v1/health" -TimeoutSec 10
$page = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 10
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$login = Invoke-RestMethod -Uri "$base/api/v1/auth/login" -Method Post -ContentType 'application/json' -Body (@{ email = 'member@wisefx.ai'; password = 'WiseFX@Member11' } | ConvertTo-Json) -WebSession $session -TimeoutSec 10
$overview = Invoke-RestMethod -Uri "$base/api/v1/dashboard/overview" -WebSession $session -TimeoutSec 10
if ($health.status -ne 'ok') { throw 'Health endpoint failed.' }
if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'WiseFX AI') { throw 'Frontend failed.' }
if ($login.user.roles -notcontains 'MEMBER') { throw 'RBAC login failed.' }
Write-Host "OK: frontend=$($page.StatusCode), API=$($health.status), role=$($login.user.roles[0]), action=$($overview.decision.action)"
