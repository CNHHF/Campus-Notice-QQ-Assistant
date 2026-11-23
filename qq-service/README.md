# 东方知讯 · 校园通知 QQ 助手

作者：HHF。

当前官方 QQ Bot 由本项目的 `app.py` 与 `official_bot.py` 直接运行。桌面管理、QQ 消息收发、DeepSeek 通知检索、会话订阅和新增通知投递都在本项目内完成，不依赖 DeepTutor，也不需要 NapCat、QQ 客户端或 OpenClaw。

## Windows 部署

1. 准备 Python 3.12 或以上版本，以及本项目完整目录。
2. 在项目根目录执行 `powershell -NoProfile -File .\qq-service\setup.ps1`。脚本创建项目自己的 `.venv`，安装腾讯官方 `qq-botpy` SDK；再次执行保留已有凭据和状态。
3. 准备本项目原有通知采集组件：`school-radar-pkg/school-radar/school-radar.exe` 及匹配的依赖、`data/`。它负责 8765 本地工作台。采集组件是本项目通知数据来源，不是聊天机器人运行依赖；缺少它仍能配置 Bot，但无法抓取新通知。
4. 双击 `start-all.bat` / `qq-service/start-qq.bat`，或安装桌面启动器并选择本项目目录。桌面安装包接管已有部署，不是包含 Python 和采集器的全组件离线安装包。
5. 在“接入设置 → 官方 QQ Bot”填写自己的 AppID、AppSecret，在同页填写自己的 DeepSeek 模型和 API Key。密钥留空保留，不回显。
6. 默认允许所有能联系机器人的用户查询；如需限制，关闭允许所有用户并填写 OpenID 名单。QQ 单聊/群聊可用范围以官方平台给该机器人的权限为准。

腾讯官方 SDK 是本项目唯一新增 Python 依赖，版本写在 `requirements.txt` 中。无需克隆其他 AI 平台。官方账号在 https://q.qq.com/qqbot/ 创建。

## 使用与能力边界

官方版不提供主动群推送，SDK发送函数拒绝没有用户消息ID的请求，发送调度已禁用。通知仍由原采集器每60分钟自动收集。

- 群内 @ 后发送 `查通知 奖学金`、`最新通知`，或自然语言查询。
- 查询后用 `第2条详情` 查看正文，上下文按会话和提问者隔离。
- 桌面新增会话筛选，选择来源、分类、关键词，预览后保存；群内 @ 后发送 `查看订阅` 使用该筛选。
- `订阅通知` 创建默认筛选；`取消订阅` 停用；`订阅状态` 查看状态。
- `查看订阅` 显示最近匹配的最多5条，可重复查询，不标为已读，不主动发送后续通知。来源/分类/关键词维度内OR、维度间AND，全局排除规则优先。
- 首次找不到群/私聊时先给Bot发消息，再刷新会话列表；官方OpenID不是数字QQ号或群号。

腾讯文档：https://github.com/tencent-connect/bot-docs/blob/main/docs/develop/api-v2/server-inter/message/send-receive/send.md 。不要通过重新订阅、清理基线或重复调用来尝试恢复主动推送。

## 运行与数据

- 本地管理页：`http://127.0.0.1:8788`；通知工作台：`http://127.0.0.1:8765`。
- `runtime/config.json`：本项目管理凭据、DeepSeek Key 及模型；仅管理员可访问。
- `runtime/official-qq.json`：本项目官方 QQ AppID、AppSecret、OpenID 访问名单；不要分享或上传。
- `runtime/official-state/subscriptions.sqlite3`：官方 QQ 订阅、基线、发送状态。
- `runtime/service.db`：查询活动、模型用量与原有管理数据。
- 学校通知仍保存在原 `radar.db`，只读查询；采集沿用原调度，默认60分钟。每分钟检查通知库不等于抓取学校。
- 微信/OpenClaw 默认停用标记为 `runtime/openclaw.disabled`，采集桥配置 `weixin_push_paused=true`。暂停微信时采集不需要微信 target 或 OpenClaw。
- 当前桌面只提供官方渠道查询与会话筛选，旧 OneBot 手动发送入口已停用。附件下载、教务 Cookie/身份绑定不开放。

`runtime/`、`.venv/`、数据库、日志、附件、凭据和本机备份不能进入公开源码或老师的演示部署包。新部署使用老师自己的账号和密钥。

验证：`qq-service/.venv/Scripts/python.exe -m unittest discover -s qq-service/tests`。隔离测试不发送真实 QQ 消息或触发学校抓取。
