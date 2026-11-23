$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & python -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE) { throw 'Python environment creation failed.' }
}
& $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE) { throw 'Dependency installation failed.' }
$config = Join-Path (Split-Path -Parent $PSScriptRoot) 'bridge\bridge-config.json'
if (-not (Test-Path -LiteralPath $config)) { Copy-Item -LiteralPath ($config.Replace('bridge-config.json','bridge-config.example.json')) -Destination $config }
Write-Output 'QQ-only setup complete; existing credentials and data preserved.'
