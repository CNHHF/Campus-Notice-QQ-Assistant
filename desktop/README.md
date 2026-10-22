# 校园通知助手 Windows 桌面工作台 · HHF

1.1.2 是**接管已有部署**的安装版：安装启动器、开始菜单及可选桌面快捷方式；首次安装选择含 qq-service 的项目目录。原 Python 3.12+、school-radar、OpenClaw 微信插件与 NapCat 保持独立安装，不随本包分发。此包不能在完全空白的电脑上替代这些组件的首次部署。

双击后在WebView2程序窗口内显示完整工作台，安装包携带web页面文件；后台接口继续使用本机8788服务。启动通过launch.py --no-browser，不另开浏览器。学校原文等外部链接在系统浏览器打开。管理口令仅在本机后端认证，程序注入HttpOnly管理会话Cookie，不放进网址或命令行。关闭窗口收起到托盘；退出启动器后服务继续运行。状态显示端口在线，不等同于登录或消息送达；扫码和投递诊断在网页内完成。停止服务需明确确认，遇有在途 QQ 任务或微信轮次未处于等待期时拒绝停止。

程序文件默认安装在当前用户 LocalAppData/Programs/CampusNotice；部署目录记录在 HKCU/Software/HHF/CampusNotice。安装不创建开机自启，不复制账号、Token、Cookie、数据库、附件或日志。升级与卸载启动器保留原部署目录和该目录指针。

构建：Windows .NET Framework 4.x 编译器编译 Launcher.cs；Inno Setup 6.7.3 编译 installer.iss。SDK依赖固定为Microsoft.Web.WebView2 1.0.4258.31（NuGet官方包），先解压到tools/webview2，复制托管DLL、x64加载器及上游LICENSE到产物；需本机已安装Microsoft Edge WebView2 Evergreen运行时。运行 build.ps1。artifacts/ 与 tools/ 是本机输出，不入源代码库。安装包尚无代码签名证书。

验证：CampusNotice.exe --self-test；CampusNotice.exe --status-only 仅连接已运行的管理服务，不启动其他服务。可通过 --root=绝对路径 选择另一份已有部署。停止服务仅按精确部署路径和验证过的网关 PID 匹配，禁止按程序名批量结束 Python/Node/QQ。

中文安装语言来自 Inno Setup 上游 https://github.com/jrsoftware/issrc/blob/main/Files/Languages/ChineseSimplified.isl ，保留文件内译者与来源说明；Inno Setup 仅为构建工具，不随本项目源码分发。

窗口支持关闭到托盘，重复双击唤回已有窗口。只允许本机8788导航，外链仅用户操作时在浏览器打开；拒绝file等协议，无宿主对象与网页消息桥。浏览器缓存及Cookie保存在当前用户LocalAppData/CampusNotice/WebView2，不放程序安装目录。回滚基线保留在artifacts/baseline-1.0.0-*。

1.1.2 修复高DPI模糊：明确目标.NET Framework 4.8，app.config启用PerMonitorV2，manifest声明Windows10兼容性；窗口以96DPI设计并整体自动缩放。构建必须携带CampusNotice.exe.config。--dpi-check可在不启动业务服务时验证窗口DPI感知，--dpi-diagnostics可输出窗口和WebView2像素比例到LocalAppData/CampusNotice/dpi-window.json。本机125%缩放实测windowDpi=120、devicePixelRatio=1.25；未修改系统缩放设置。

学校标识：使用用户提供的浙江财经大学东方学院校徽，保留原始蓝色及透明背景，应用于桌面、窗口、托盘、安装程序及网页。校徽属于学校标识，不包含在本项目代码的 MIT 授权范围内。
