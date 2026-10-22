[Setup]
AppId={{6E973BA2-F10E-4B38-9D52-9F1BFB42F918}
AppName=校园通知助手
AppVersion=1.1.2
AppPublisher=HHF
DefaultDirName={localappdata}\Programs\CampusNotice
DefaultGroupName=校园通知助手
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=artifacts
OutputBaseFilename=CampusNotice-Setup-1.1.2
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=artifacts\web\favicon.ico
UninstallDisplayIcon={app}\CampusNotice.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
LicenseFile=LICENSE.txt

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Files]
Source: "artifacts\CampusNotice.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\CampusNotice.exe.config"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\Microsoft.Web.WebView2.Core.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\Microsoft.Web.WebView2.WinForms.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\WebView2Loader.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\WebView2-LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "artifacts\web\*"; DestDir: "{app}\web"; Flags: ignoreversion
Source: "stop_services.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\校园通知助手"; Filename: "{app}\CampusNotice.exe"
Name: "{autodesktop}\校园通知助手"; Filename: "{app}\CampusNotice.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\HHF\CampusNotice"; ValueType: string; ValueName: "DeploymentRoot"; ValueData: "{code:DeployRoot}"

[Run]
Filename: "{app}\CampusNotice.exe"; Description: "打开校园通知助手"; Flags: nowait postinstall skipifsilent

[Code]
var DeployPage: TInputDirWizardPage;
function DeployRoot(Param: String): String;
begin Result := DeployPage.Values[0]; end;
procedure InitializeWizard;
var Existing: String;
begin
  DeployPage := CreateInputDirPage(wpSelectDir, '选择已有部署目录', '接管现有校园通知服务，账号和数据留在原处。', '请选择包含 qq-service 的目录。本安装包提供桌面启动器，沿用该目录现有 Python、抓取器、微信及 QQ 组件。卸载启动器不会删除此目录。', False, '');
  DeployPage.Add('校园通知部署目录：');
  if not RegQueryStringValue(HKCU, 'Software\HHF\CampusNotice', 'DeploymentRoot', Existing) then
    Existing := AddBackslash(GetEnv('USERPROFILE')) + 'deploy-work';
  DeployPage.Values[0] := Existing;
end;
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = DeployPage.ID then begin
    if not FileExists(AddBackslash(DeployPage.Values[0]) + 'qq-service\app.py') or
       not FileExists(AddBackslash(DeployPage.Values[0]) + 'qq-service\launch.py') or
       not FileExists(AddBackslash(DeployPage.Values[0]) + 'qq-service\start-services.ps1') then begin
      MsgBox('未找到有效部署目录，请选择含 qq-service 的校园通知目录。', mbError, MB_OK);
      Result := False;
    end;
  end;
end;
