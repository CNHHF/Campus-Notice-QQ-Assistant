param([switch]$InspectOnly)
$ErrorActionPreference = 'Stop'
$root = if ($env:CAMPUS_DEPLOY_ROOT) { $env:CAMPUS_DEPLOY_ROOT } else { Split-Path -Parent $PSScriptRoot }
$bridgeDir = if (Test-Path -LiteralPath (Join-Path $root 'weixin-bridge')) { Join-Path $root 'weixin-bridge' } else { Join-Path $root 'bridge' }
$runtime = Join-Path $PSScriptRoot 'runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
function Find-Gateway { Get-CimInstance Win32_Process -Filter "name='node.exe'" | Where-Object { $_.CommandLine -like '*openclaw*index.js gateway*' } | Select-Object -First 1 }
function Find-Bridge { Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like ('*' + $bridgeDir + '*bridge.py*') } | Select-Object -First 1 }
function Port-Ready([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $task = $client.ConnectAsync('127.0.0.1',$port); return ($task.Wait(300) -and $client.Connected) } catch { return $false } finally { $client.Dispose() }
}
if (-not $InspectOnly) {
    if (-not (Find-Gateway)) { Start-Process -WindowStyle Hidden -FilePath 'wscript.exe' -ArgumentList (Join-Path $env:USERPROFILE '.openclaw\gateway.vbs') }
    if (-not (Get-CimInstance Win32_Process -Filter "name='school-radar.exe'" | Select-Object -First 1)) {
        $radar = Join-Path $root 'school-radar-pkg\school-radar'
        Start-Process -WindowStyle Hidden -FilePath (Join-Path $radar 'school-radar.exe') -ArgumentList '--no-open','--serve-only' -WorkingDirectory $radar
    }
    # Start the bridge only after the gateway has actually opened its port.
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while (-not (Port-Ready 18789) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if ((Port-Ready 18789) -and -not (Find-Bridge)) {
        $vbs = Join-Path $bridgeDir 'weixin-bridge.vbs'
        if (Test-Path -LiteralPath $vbs) { Start-Process -WindowStyle Hidden -FilePath 'wscript.exe' -ArgumentList $vbs }
        else { Start-Process -WindowStyle Hidden -FilePath (Get-Command python.exe).Source -ArgumentList ('"' + (Join-Path $bridgeDir 'bridge.py') + '"') -WorkingDirectory $bridgeDir }
        Start-Sleep -Milliseconds 700
    }
    if (-not (Port-Ready 3000)) {
        $client = Join-Path $root 'qq-client\start-qq-client.bat'
        if (Test-Path -LiteralPath $client) {
            $qq = Get-CimInstance Win32_Process -Filter "name='QQ.exe'" | Where-Object { $_.CommandLine -like '*NapCat*' } | Select-Object -First 1
            if (-not $qq) { Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList '/c',('"' + $client + '"') -WorkingDirectory (Join-Path $root 'qq-client') }
        }
    }
}
$gateway = Find-Gateway
$bridge = Find-Bridge
$status = @{ gateway_pid = if ($gateway) { $gateway.ProcessId } else { 0 }; bridge_pid = if ($bridge) { $bridge.ProcessId } else { 0 }; gateway_ready = (Port-Ready 18789); qq_ready = (Port-Ready 3000); checked_at = [DateTime]::Now.ToString('s') }
$json = $status | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText((Join-Path $runtime 'startup-status.json'),$json,[System.Text.UTF8Encoding]::new($false))
Write-Output $json
