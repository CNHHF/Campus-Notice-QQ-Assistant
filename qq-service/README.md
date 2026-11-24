# QQ 通知服务 v1.3.1 · HHF

使用 NapCat / OneBot HTTP，管理服务仅监听127.0.0.1:8788，通知采集工作台8765。

先运行 `setup.ps1`。依赖仅 `qrcode==8.2`，用于本地生成QQ登录二维码，不需要Node或其他应用的模块。二维码URL只接受固定的腾讯登录域名。

`launch.py` / `start-qq.bat` 启动本项目管理服务、独立采集调度及NapCat；已有进程跳过，不启动其他渠道。配置保存在 `runtime/config.json`，只在本机保存QQ接口令牌、管理口令和DeepSeek凭据。模型也可使用环境变量DEEPSEEK_API_KEY，密钥不回显。

采集设置与QQ过滤规则：`bridge/bridge-config.json`，首次部署从example复制。默认60分钟，旧值迁移保留；正常启动按最后真实抓取时间判断是否到期；维护使用--wait-first-round保留等待，不维护抓取。原通知库及 `runtime/service.db` 的基线、投递状态、阅读收藏与查询记录保留。每群首次启用推送建立当前历史基线，发送中或回执不确定不自动重发。

管理界面只提供采集、QQ扫码、群和私聊访问管理、DeepSeek检索、自动推送及手动预览发送。被移除的旧渠道接口返回404。

不要公开runtime、数据库、凭据、日志或备份。桌面启动器不是含采集器、Python和NapCat的全组件离线安装包。

验证：`.venv/Scripts/python.exe -m unittest discover -s tests`。隔离测试不联系学校或发送真实消息。
