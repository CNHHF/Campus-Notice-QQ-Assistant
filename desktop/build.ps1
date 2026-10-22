$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$inno = Join-Path $base 'tools\inno\ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Windows .NET Framework compiler not found.' }
if (-not (Test-Path -LiteralPath $inno)) { throw 'Install Inno Setup 6.7.3 in desktop/tools/inno first.' }
New-Item -ItemType Directory -Force -Path (Join-Path $base 'artifacts') | Out-Null
$sdk = Join-Path $base 'tools\webview2'
if (-not (Test-Path "$sdk\lib\net462\Microsoft.Web.WebView2.Core.dll")) { throw 'Restore Microsoft.Web.WebView2 1.0.4258.31 to desktop/tools/webview2 first.' }
Copy-Item "$sdk\lib\net462\Microsoft.Web.WebView2.Core.dll","$sdk\lib\net462\Microsoft.Web.WebView2.WinForms.dll","$sdk\runtimes\win-x64\native\WebView2Loader.dll" "$base\artifacts" -Force
Copy-Item "$sdk\LICENSE.txt" "$base\artifacts\WebView2-LICENSE.txt" -Force
New-Item -ItemType Directory -Force "$base\artifacts\web" | Out-Null
Copy-Item "$base\..\qq-service\web\*.html","$base\..\qq-service\web\*.js","$base\..\qq-service\web\*.css" "$base\artifacts\web" -Force
Copy-Item "$base\..\qq-service\web\school-logo.png","$base\..\qq-service\web\favicon.ico" "$base\artifacts\web" -Force
& $compiler /nologo /win32icon:"$base\artifacts\web\favicon.ico" /target:winexe /platform:x64 /utf8output /win32manifest:"$base\app.manifest" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Management.dll /reference:System.Web.Extensions.dll /reference:"$base\artifacts\Microsoft.Web.WebView2.Core.dll" /reference:"$base\artifacts\Microsoft.Web.WebView2.WinForms.dll" /out:"$base\artifacts\CampusNotice.exe" "$base\Launcher.cs"
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
Copy-Item -LiteralPath (Join-Path $base 'stop_services.py') -Destination (Join-Path $base 'artifacts\stop_services.py') -Force
Copy-Item -LiteralPath (Join-Path $base 'CampusNotice.exe.config') -Destination (Join-Path $base 'artifacts\CampusNotice.exe.config') -Force
& $inno "$base\installer.iss"
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
