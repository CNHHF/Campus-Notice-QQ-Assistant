param([switch]$InspectOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $PSScriptRoot 'runtime'
$collectorDir = Join-Path $root 'bridge'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$errorsFound = New-Object 'System.Collections.Generic.List[string]'
$mutex = New-Object System.Threading.Mutex($false,'Local\CampusNoticeServiceBootstrap')
try { $ownsMutex = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $ownsMutex = $true }
if (-not $ownsMutex) { $mutex.Dispose(); exit 0 }
try {
function Find-Collector { Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object {$_.CommandLine -like ('*'+(Join-Path $collectorDir 'bridge.py')+'*')} | Select-Object -First 1 }
function Port-Ready([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $task=$client.ConnectAsync('127.0.0.1',$port); return ($task.Wait(300) -and $client.Connected) } catch { return $false } finally { $client.Dispose() }
}
if (-not $InspectOnly) {
    $report=@{phase='starting';started_epoch=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()}
    [System.IO.File]::WriteAllText((Join-Path $runtime 'startup-status.json'),($report|ConvertTo-Json -Compress),[System.Text.UTF8Encoding]::new($false))
    try {
        if (-not (Get-CimInstance Win32_Process -Filter "name='school-radar.exe'" | Select-Object -First 1)) {
            $radar=Join-Path $root 'school-radar-pkg\school-radar'
            Start-Process -WindowStyle Hidden -FilePath (Join-Path $radar 'school-radar.exe') -ArgumentList '--no-open','--serve-only' -WorkingDirectory $radar
        }
    } catch {$errorsFound.Add('Notice workbench launch failed.')}
    try {
        if (-not (Port-Ready 3000) -and -not (Port-Ready 6099)) {
            $launcher=Join-Path $root 'qq-client\start-qq-client.bat'
            if (Test-Path -LiteralPath $launcher) {
                $bot=''
                $cfgPath=Join-Path $runtime 'config.json'
                if (Test-Path -LiteralPath $cfgPath) {$bot=[string]((Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8|ConvertFrom-Json).bot_qq)}
                if ($bot -notmatch '^[1-9][0-9]{4,15}$') {$bot=''}
                Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList '/c',('"'+$launcher+'" '+$bot) -WorkingDirectory (Join-Path $root 'qq-client')
            }
        }
    } catch {$errorsFound.Add('QQ client launch failed.')}
    try {
        if (-not (Find-Collector)) {
            $python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
            if (-not (Test-Path -LiteralPath $python)) {$python=(Get-Command python).Source}
            Start-Process -WindowStyle Hidden -FilePath $python -ArgumentList ('"'+(Join-Path $collectorDir 'bridge.py')+'" --wait-first-round') -WorkingDirectory $collectorDir
        }
    } catch {$errorsFound.Add('Collection scheduler launch failed.')}
}
$collector=Find-Collector
$status=@{phase='finished';errors=@($errorsFound.ToArray());bridge_pid=$(if($collector){$collector.ProcessId}else{0});qq_ready=(Port-Ready 3000);checked_at=[DateTime]::Now.ToString('s')}
[System.IO.File]::WriteAllText((Join-Path $runtime 'startup-status.json'),($status|ConvertTo-Json -Compress),[System.Text.UTF8Encoding]::new($false))
Write-Output ($status|ConvertTo-Json -Compress)
} catch {Write-Output 'Service startup failed; check local installation.';exit 1}
finally {$mutex.ReleaseMutex();$mutex.Dispose()}
