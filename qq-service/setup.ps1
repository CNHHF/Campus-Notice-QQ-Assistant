param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $PSScriptRoot 'runtime'
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required.' }
}
& $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Official QQ SDK installation failed.' }
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$configPath = Join-Path $runtime 'official-qq.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    [IO.File]::WriteAllText($configPath, '{"transport":"qq-official","app_id":"","secret":"","allow_from":["*"]}', [Text.UTF8Encoding]::new($false))
}
New-Item -ItemType File -Force -Path (Join-Path $runtime 'openclaw.disabled') | Out-Null
$root = Split-Path -Parent $PSScriptRoot
$bridge = Join-Path $root 'weixin-bridge'
if (-not (Test-Path -LiteralPath $bridge)) { $bridge = Join-Path $root 'bridge' }
New-Item -ItemType Directory -Force -Path $bridge | Out-Null
$bridgeConfig = Join-Path $bridge 'bridge-config.json'
if (-not (Test-Path -LiteralPath $bridgeConfig)) {
    $defaults = @{
        radar_base='http://127.0.0.1:8765'; radar_db=(Join-Path $root 'school-radar-pkg\school-radar\data\radar.db');
        interval_minutes=60; weixin_push_paused=$true; qq_push_paused=$false;
        exclude_categories=@('jobstart'); exclude_keywords=@('招聘','招募','校园大使','宣讲会','双选会','就业指导','考公','公考','事业单位');
        max_age_days=30; categories=@(); quiet_hours=@(); min_score=0.0
    }
    [IO.File]::WriteAllText($bridgeConfig, ($defaults | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
}
Write-Output 'Ready. Open the campus desktop app and configure QQ Bot and DeepSeek in Settings.'
