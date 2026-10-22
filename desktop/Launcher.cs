using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Drawing;
using System.Diagnostics;
using System.Management;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text;
using System.Web.Script.Serialization;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
[assembly: AssemblyTitle("校园通知助手")]
[assembly: AssemblyCompany("HHF")]
[assembly: AssemblyProduct("Campus Notice")]
[assembly: AssemblyCopyright("Copyright © HHF")]
[assembly: AssemblyVersion("1.1.2.0")]
[assembly: TargetFramework(".NETFramework,Version=v4.8",FrameworkDisplayName=".NET Framework 4.8")]

static class Program {
    [DllImport("user32.dll")] static extern IntPtr GetWindowDpiAwarenessContext(IntPtr window);
    [DllImport("user32.dll")] static extern bool AreDpiAwarenessContextsEqual(IntPtr first,IntPtr second);
    [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr window);
    internal const string Key = @"Software\HHF\CampusNotice";
    internal static string Root;
    internal static bool DpiDiagnostics;
    internal static uint WindowDpi(IntPtr handle){return GetDpiForWindow(handle);}
    internal static bool ValidRoot(string path) {
        try { return Path.IsPathRooted(path) && File.Exists(Path.Combine(path,"qq-service","launch.py")) && File.Exists(Path.Combine(path,"qq-service","app.py")) && File.Exists(Path.Combine(path,"qq-service","start-services.ps1")); }
        catch { return false; }
    }
    internal static bool Port(int port) {
        using(var c=new TcpClient()) { try { var t=c.ConnectAsync("127.0.0.1",port); return t.Wait(250)&&c.Connected; } catch {return false;} }
    }
    internal static bool Healthy() {
        try { var r=(HttpWebRequest)WebRequest.Create("http://127.0.0.1:8788/api/health");r.Proxy=null;r.Timeout=1200;
            using(var response=r.GetResponse()) using(var reader=new StreamReader(response.GetResponseStream())) return reader.ReadToEnd().Contains("campus-qq");
        } catch {return false;}
    }
    internal static string Python() {
        foreach(var hive in new[]{Registry.CurrentUser,Registry.LocalMachine}) {
            using(var key=hive.OpenSubKey(@"Software\Python\PythonCore")) {
                if(key==null)continue;
                var versions=key.GetSubKeyNames();Array.Sort(versions);Array.Reverse(versions);
                foreach(var version in versions) {
                    Version v;if(!Version.TryParse(version,out v)||v<new Version(3,12))continue;
                    using(var install=key.OpenSubKey(version+@"\InstallPath")) {
                        if(install==null)continue;
                        var exe=install.GetValue("ExecutablePath") as string;
                        if(string.IsNullOrEmpty(exe))exe=Path.Combine(install.GetValue("") as string ?? "", "python.exe");
                        if(File.Exists(exe))return exe;
                    }
                }
            }
        }
        throw new InvalidOperationException("未找到 Python 3.12 或更新版本。请先完成项目运行环境安装。");
    }
    internal static string Quote(string s) { return "\""+s.Replace("\"","\\\"").TrimEnd('\\')+"\""; }
    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        if(Array.IndexOf(args,"--dpi-check")>=0) {
            using(var probe=new Form()) {
                var handle=probe.Handle;bool aware=AreDpiAwarenessContextsEqual(GetWindowDpiAwarenessContext(handle),new IntPtr(-4));
                float graphicsDpi;using(var graphics=probe.CreateGraphics())graphicsDpi=graphics.DpiX;
                var report=new{perMonitorV2=aware,windowDpi=GetDpiForWindow(handle),graphicsDpi=graphicsDpi};
                File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"dpi-check.json"),new JavaScriptSerializer().Serialize(report));
                Environment.Exit(aware?0:1);return;
            }
        }
        if(Array.IndexOf(args,"--self-test")>=0) {
            bool ok=!ValidRoot(Path.GetTempPath())&&Quote(@"C:\a b\launch.py")=="\"C:\\a b\\launch.py\""
                &&Launcher.Internal("http://127.0.0.1:8788/")&&!Launcher.Internal("http://127.0.0.1:6099/")
                &&!Launcher.Internal("https://example.com/")&&!Launcher.Internal("file:///C:/Windows/")
                &&!Launcher.Internal("http://user:pass@127.0.0.1:8788/");
            Environment.Exit(ok?0:1);return;
        }
        Root=Registry.GetValue(@"HKEY_CURRENT_USER\"+Key,"DeploymentRoot","") as string;
        DpiDiagnostics=Array.IndexOf(args,"--dpi-diagnostics")>=0;
        foreach(var arg in args) if(arg.StartsWith("--root=",StringComparison.Ordinal))Root=arg.Substring(7);
        if(!ValidRoot(Root)) {
            var guess=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"deploy-work");
            if(ValidRoot(guess))Root=guess;
            else using(var dialog=new FolderBrowserDialog{Description="选择现有校园通知部署目录（包含 qq-service）"}) {
                if(dialog.ShowDialog()!=DialogResult.OK||!ValidRoot(dialog.SelectedPath)) { MessageBox.Show("未找到有效部署目录。请先完成校园通知服务部署，再运行启动器。","校园通知助手");return; }
                Root=dialog.SelectedPath;
            }
        }
        Root=Path.GetFullPath(Root);
        bool created;using(var mutex=new Mutex(true,@"Local\HHF.CampusNotice.Launcher",out created)) {
            if(!created) { try { using(var signal=EventWaitHandle.OpenExisting(@"Local\HHF.CampusNotice.Show"))signal.Set(); } catch {} return; }
            using(var key=Registry.CurrentUser.CreateSubKey(Key))key.SetValue("DeploymentRoot",Root);
            Application.Run(new Launcher(Array.IndexOf(args,"--status-only")>=0));
        }
    }
}

sealed class Launcher:Form {
    WebView2 web;Panel loading;Label summary;NotifyIcon tray;bool busy,exit,initialized;
    string root=Program.Root;EventWaitHandle signal;RegisteredWaitHandle registration;
    string appDir=AppDomain.CurrentDomain.BaseDirectory;
    public Launcher(bool statusOnly) {
        SuspendLayout();
        AutoScaleDimensions=new SizeF(96F,96F);AutoScaleMode=AutoScaleMode.Dpi;
        Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Text="校园通知助手";ClientSize=new Size(1280,820);MinimumSize=new Size(900,620);
        Font=new Font("Microsoft YaHei UI",10);BackColor=Color.White;StartPosition=FormStartPosition.CenterScreen;
        var menu=new MenuStrip();var service=new ToolStripMenuItem("服务");
        service.DropDownItems.Add("启动 / 修复",null,async delegate{await StartAll();});
        service.DropDownItems.Add("查看连接状态",null,async delegate{await ShowStatus();});
        service.DropDownItems.Add("查看运行目录",null,delegate{Process.Start(Path.Combine(root,"qq-service","runtime"));});
        service.DropDownItems.Add("停止服务并退出",null,StopAll);
        service.DropDownItems.Add("退出程序（服务继续运行）",null,delegate{exit=true;Close();});
        menu.Items.Add(service);menu.Items.Add("重新加载",null,async delegate{await OpenPage();});MainMenuStrip=menu;
        web=new WebView2{Dock=DockStyle.Fill,Visible=false};Controls.Add(web);
        loading=new Panel{Dock=DockStyle.Fill,BackColor=Color.FromArgb(246,248,249)};
        var column=new FlowLayoutPanel{FlowDirection=FlowDirection.TopDown,AutoSize=true,WrapContents=false,Location=new Point(40,60)};
        column.Controls.Add(new Label{Text="校园通知助手",AutoSize=true,Font=new Font(Font.FontFamily,24,FontStyle.Bold),Margin=new Padding(0,0,0,24)});
        summary=new Label{Text="正在准备工作台…",AutoSize=true,MaximumSize=new Size(700,0),Margin=new Padding(0,0,0,24)};column.Controls.Add(summary);
        var retry=new Button{Text="启动 / 重试",AutoSize=true,Padding=new Padding(16,8,16,8)};retry.Click+=async delegate{await StartAll();};column.Controls.Add(retry);
        loading.Controls.Add(column);Controls.Add(loading);Controls.Add(menu);
        var context=new ContextMenuStrip();context.Items.Add("打开工作台",null,async delegate{Restore();await OpenPage();});context.Items.Add("启动 / 修复",null,async delegate{await StartAll();});
        context.Items.Add("查看状态",null,async delegate{Restore();await ShowStatus();});context.Items.Add("停止服务并退出",null,StopAll);context.Items.Add("退出程序（服务继续运行）",null,delegate{exit=true;Close();});
        tray=new NotifyIcon{Icon=Icon,Text="校园通知助手",Visible=true,ContextMenuStrip=context};tray.DoubleClick+=delegate{Restore();};
        signal=new EventWaitHandle(false,EventResetMode.AutoReset,@"Local\HHF.CampusNotice.Show");
        registration=ThreadPool.RegisterWaitForSingleObject(signal,delegate(object state,bool timeout){if(!IsDisposed&&IsHandleCreated)BeginInvoke(new Action(Restore));},null,-1,false);
        FormClosing+=delegate(object sender,FormClosingEventArgs e){if(!exit){e.Cancel=true;Hide();tray.ShowBalloonTip(2500,Text,"已收起到托盘，通知服务继续运行。",ToolTipIcon.Info);}};
        FormClosed+=delegate{registration.Unregister(null);signal.Dispose();tray.Visible=false;tray.Dispose();web.Dispose();};
        Shown+=async delegate{if(statusOnly){if(await Task.Run<bool>(()=>Program.Healthy()))await OpenPage();else summary.Text="管理服务未运行。点击启动 / 重试打开工作台。";}else await StartAll();};
        ResumeLayout(false);PerformLayout();
    }
    void Restore(){Show();WindowState=FormWindowState.Normal;Activate();}
    internal static bool Internal(string text) {
        Uri uri;return Uri.TryCreate(text,UriKind.Absolute,out uri)&&uri.Scheme=="http"&&uri.Host=="127.0.0.1"&&uri.Port==8788&&string.IsNullOrEmpty(uri.UserInfo);
    }
    static bool External(string text){Uri uri;return Uri.TryCreate(text,UriKind.Absolute,out uri)&&(uri.Scheme=="http"||uri.Scheme=="https")&&string.IsNullOrEmpty(uri.UserInfo);}
    void ExternalLink(string text){if(External(text))Process.Start(text);}
    async Task InitializeWeb() {
        if(initialized)return;
        var profile=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CampusNotice","WebView2");
        var environment=await CoreWebView2Environment.CreateAsync(null,profile,null);
        await web.EnsureCoreWebView2Async(environment);
        web.CoreWebView2.Settings.AreHostObjectsAllowed=false;web.CoreWebView2.Settings.IsWebMessageEnabled=false;
        web.CoreWebView2.Settings.AreDevToolsEnabled=false;web.CoreWebView2.Settings.IsPasswordAutosaveEnabled=false;
        web.CoreWebView2.Settings.IsGeneralAutofillEnabled=false;
        web.CoreWebView2.NavigationStarting+=delegate(object sender,CoreWebView2NavigationStartingEventArgs e){if(!Internal(e.Uri)){e.Cancel=true;if(e.IsUserInitiated)ExternalLink(e.Uri);}};
        web.CoreWebView2.NewWindowRequested+=delegate(object sender,CoreWebView2NewWindowRequestedEventArgs e){e.Handled=true;if(Internal(e.Uri))web.CoreWebView2.Navigate(e.Uri);else if(e.IsUserInitiated)ExternalLink(e.Uri);};
        web.CoreWebView2.PermissionRequested+=delegate(object sender,CoreWebView2PermissionRequestedEventArgs e){e.State=CoreWebView2PermissionState.Deny;};
        web.CoreWebView2.NavigationCompleted+=async delegate(object sender,CoreWebView2NavigationCompletedEventArgs e){if(e.IsSuccess){loading.Visible=false;web.Visible=true;if(Program.DpiDiagnostics){try{var renderer=await web.CoreWebView2.ExecuteScriptAsync("({devicePixelRatio:window.devicePixelRatio,viewportWidth:window.innerWidth,viewportHeight:window.innerHeight})");var directory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CampusNotice");Directory.CreateDirectory(directory);File.WriteAllText(Path.Combine(directory,"dpi-window.json"),new JavaScriptSerializer().Serialize(new{windowDpi=Program.WindowDpi(Handle),renderer=renderer}));}catch{}}}else{web.Visible=false;loading.Visible=true;summary.Text="工作台暂时无法加载，请点击启动 / 重试。";}};
        web.CoreWebView2.ProcessFailed+=delegate{web.Visible=false;loading.Visible=true;summary.Text="网页运行进程已退出，请重新打开程序；后台服务仍可独立运行。";};
        web.CoreWebView2.AddWebResourceRequestedFilter("http://127.0.0.1:8788/*",CoreWebView2WebResourceContext.All);
        web.CoreWebView2.WebResourceRequested+=delegate(object sender,CoreWebView2WebResourceRequestedEventArgs e){
            if(e.Request.Method!="GET"||!Internal(e.Request.Uri))return;
            var path=new Uri(e.Request.Uri).AbsolutePath;
            var name=path=="/"?"index.html":path=="/app.js"?"app.js":path=="/style.css"?"style.css":path=="/school-logo.png"?"school-logo.png":path=="/favicon.ico"?"favicon.ico":null;
            if(name==null)return;
            var file=Path.Combine(appDir,"web",name);if(!File.Exists(file))return;
            var mime=name.EndsWith(".html")?"text/html":name.EndsWith(".js")?"text/javascript":name.EndsWith(".png")?"image/png":name.EndsWith(".ico")?"image/x-icon":"text/css";
            e.Response=environment.CreateWebResourceResponse(new MemoryStream(File.ReadAllBytes(file)),200,"OK","Content-Type: "+mime+"; charset=utf-8\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nContent-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src 'self' http://127.0.0.1:8765; frame-ancestors 'none'\r\n");
        };
        initialized=true;
    }
    string LoginCookie() {
        var serializer=new JavaScriptSerializer();
        var config=serializer.Deserialize<System.Collections.Generic.Dictionary<string,object>>(File.ReadAllText(Path.Combine(root,"qq-service","runtime","config.json"),Encoding.UTF8));
        var body=Encoding.UTF8.GetBytes(serializer.Serialize(new{token=(string)config["admin_token"]}));
        var request=(HttpWebRequest)WebRequest.Create("http://127.0.0.1:8788/api/login");request.Proxy=null;request.AllowAutoRedirect=false;request.Timeout=5000;request.Method="POST";request.ContentType="application/json";request.ContentLength=body.Length;request.Headers["Origin"]="http://127.0.0.1:8788";
        using(var stream=request.GetRequestStream())stream.Write(body,0,body.Length);
        using(var response=request.GetResponse()) {
            var raw=response.Headers["Set-Cookie"]??"";var match=System.Text.RegularExpressions.Regex.Match(raw,@"campus_session=([A-Za-z0-9_-]{20,100})");
            if(!match.Success)throw new InvalidOperationException("无法创建管理会话，请检查服务配置。");return match.Groups[1].Value;
        }
    }
    async Task OpenPage() {
        try {
            if(!await Task.Run<bool>(()=>Program.Healthy())){web.Visible=false;loading.Visible=true;summary.Text="管理服务未运行，请点击启动 / 重试。";return;}
            await InitializeWeb();
            var value=await Task.Run<string>(()=>LoginCookie());var cookie=web.CoreWebView2.CookieManager.CreateCookie("campus_session",value,"127.0.0.1","/");cookie.IsHttpOnly=true;cookie.SameSite=CoreWebView2CookieSameSiteKind.Strict;web.CoreWebView2.CookieManager.AddOrUpdateCookie(cookie);
            web.CoreWebView2.Navigate("http://127.0.0.1:8788/");
        }catch{web.Visible=false;loading.Visible=true;summary.Text="工作台启动未完成。请确认 WebView2 运行时已安装、部署目录可用，再重试。";}
    }
    async Task StartAll() {
        if(busy)return;busy=true;summary.Text="正在启动本机服务…";
        try{
            var python=Program.Python();var script=Path.Combine(root,"qq-service","launch.py");
            var info=new ProcessStartInfo(python,Program.Quote(script)+" --no-browser"){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=Path.GetDirectoryName(script),RedirectStandardOutput=true,RedirectStandardError=true};
            using(var p=Process.Start(info)){var output=p.StandardOutput.ReadToEndAsync();var errors=p.StandardError.ReadToEndAsync();if(!await Task.Run(delegate{return p.WaitForExit(30000);}))throw new InvalidOperationException();await Task.WhenAll(output,errors);if(p.ExitCode!=0)throw new InvalidOperationException();}
            await OpenPage();
        }catch{loading.Visible=true;web.Visible=false;summary.Text="服务尚未就绪。可稍后重试，或通过服务菜单查看状态和运行日志。";}
        finally{busy=false;}
    }
    async Task ShowStatus(){var states=await Task.Run(delegate{return new[]{Program.Healthy(),Program.Port(8765),Program.Port(18789),Program.Port(3000)};});MessageBox.Show("管理服务："+(states[0]?"在线":"未就绪")+"\n通知工作台："+(states[1]?"在线":"未就绪")+"\n微信网关："+(states[2]?"端口在线":"未就绪")+"\nQQ 接口："+(states[3]?"端口在线":"等待登录")+"\n\n扫码及投递状态请在工作台接入设置中查看。",Text);}
    async void StopAll(object sender,EventArgs e){
        if(busy||MessageBox.Show("停止本部署的通知服务并退出？配置和历史记录会保留。发送中任务会阻止停止。",Text,MessageBoxButtons.YesNo)!=DialogResult.Yes)return;
        busy=true;try{var info=new ProcessStartInfo(Program.Python(),Program.Quote(Path.Combine(appDir,"stop_services.py"))+" "+Program.Quote(root)){UseShellExecute=false,CreateNoWindow=true};using(var p=Process.Start(info)){await Task.Run(delegate{p.WaitForExit();});if(p.ExitCode!=0)throw new InvalidOperationException();}exit=true;Close();}catch{MessageBox.Show("当前无法安全停止，请稍后重试。",Text);}finally{busy=false;}
    }
}

