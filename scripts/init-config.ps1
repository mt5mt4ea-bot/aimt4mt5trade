$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$examplePath = Join-Path $projectRoot 'server\.env.example'
$targetPath = Join-Path $projectRoot 'server\.env'

if (Test-Path -LiteralPath $targetPath) {
  Write-Host 'server/.env already exists; no changes made.'
  exit 0
}

function New-Secret {
  $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(36)
  return [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_').TrimEnd('=')
}

$content = Get-Content -LiteralPath $examplePath -Raw
$content = $content.Replace('replace-with-a-long-random-value', (New-Secret))
$content = $content.Replace('replace-with-a-different-long-random-value', (New-Secret))
$content = $content.Replace('replace-with-a-third-long-random-value', (New-Secret))
[System.IO.File]::WriteAllText($targetPath, $content, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Created server/.env with random EA, admin, and plan-signing secrets.'
Write-Host 'Add AI_API_KEY, then copy EA_API_KEY into the MT5 EA input.'

