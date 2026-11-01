param([string]$Distribution = 'Ubuntu')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$stateDir = Join-Path $projectRoot 'artifacts/local-age'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$pidFile = Join-Path $stateDir 'wsl-keeper.pid'
$keeper = $null
if (Test-Path -LiteralPath $pidFile) {
    $keeperId = Get-Content -LiteralPath $pidFile
    $keeper = Get-Process -Id $keeperId -ErrorAction SilentlyContinue | Where-Object ProcessName -eq 'wsl'
}
if (-not $keeper) {
    $keeper = Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d', $Distribution, '-u', 'root', '--', 'sleep', 'infinity') -WindowStyle Hidden -PassThru
    $keeper.Id | Set-Content -LiteralPath $pidFile
}
& wsl.exe -d $Distribution -u root -- systemctl start docker
if ($LASTEXITCODE -ne 0) { throw 'Docker failed to start' }
& wsl.exe -d $Distribution -u root -- docker start culti-age-live
if ($LASTEXITCODE -ne 0) { throw 'AGE container failed to start' }
Write-Output 'AGE container started; Windows has not been restarted.'
