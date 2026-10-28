# 东方知讯 · 校园通知 QQ 助手

**QQ 自动推送、AI 通知检索与手动选择分发，配套 Windows 桌面工作台。**

东方知讯整理学校公开网站的通知，让师生在常用的 QQ 群中接收新增信息、用自然语言找通知，让管理员在分发前选择内容、核对对象。每条结果保留学校原文链接，微信作为补充通道保留。

仓库名称：`Campus-Notice-QQ-Assistant`。作者：**HHF**。

## QQ 自动推送

- 检查本地通知库的新增内容，按每个群订阅的学院、部门来源和分类分发。
- 消息包含标题、发布日期、原文链接；全局排除规则继续生效。
- 新启用群先建立已有通知基线，避免一次性补发历史通知。
- 按群记录投递状态、处理重复事件；发送结果不确定时不自动重发。
- 自动推送不调用大模型。默认抓取间隔60分钟，前端可调10-180分钟；QQ每分钟检查本地库，不代表每分钟抓取学校网站。

## AI 通知检索

群聊中**每次真实 @ 机器人**后提问，例如：

```text
@机器人 帮我找一下最近的竞赛通知
@机器人 第1条详情
```

DeepSeek 将自然语言转换为受约束的检索参数，程序从本地通知库返回标题、日期和链接。竞赛查询区分报名组织、系统培训及获奖结果；最近发布不代表仍可报名，截止时间请核对原文。

普通群消息、@全体、引用或仅输入机器人名字不会触发查询。私聊需要名单授权；短期上下文按群和提问者隔离。与通知无关的内容统一提示“请说出您要查询的通知”。

`查通知 奖学金`、`最新通知`、编号详情等命令式查询无需模型。自然语言提问会发送到配置的 DeepSeek API，模型不替代学校原文。

## 手动选择分发

在桌面收件箱按关键词、来源和日期筛选，勾选通知，选择获准接收的群或私人 QQ，**预览后确认发送**。

- 支持分页、跨页保留选择、全选/反选/取消选择，单批最多50条通知、10个对象。
- 已发送通知再次分发需要明确确认；在途或结果不确定的消息不能绕过保护重发。
- 手动推送不调用模型、不触发额外抓取。

## 统一工作台

| 模块 | 功能 |
|---|---|
| 通知收件箱 | 本地正文、学校原文、主题/来源/日期筛选、已读和收藏 |
| 访问管理 | 群名单、私聊名单、每群订阅、群自动推送设置 |
| 接入设置 | QQ登录二维码、连接与通道诊断、DeepSeek设置及微信授权 |
| 运行管理 | 一键启动/修复、抓取状态、微信与QQ自动推送独立暂停 |
| Windows程序 | WebView2内嵌前端、单实例、托盘、高DPI适配 |

管理页默认仅本机访问：`http://127.0.0.1:8788`。首次部署随机生成管理口令，正常重启保持不变。扫码与手机授权由账号持有人完成。

## 实现结构

```text
学校公开网站
    ↓ school-radar（独立部署的采集组件）
SQLite 通知库
    ├─ QQ 服务：新增检测 / 分群订阅 / 投递状态 → OneBot v11 → QQ
    ├─ DeepSeek 参数解析 → 本地库检索 → QQ 查询回复
    ├─ 管理前端 / Windows WebView2 → 阅读与手动预览分发
    └─ 微信桥 / OpenClaw → 微信补充通道
```

前端使用HTML、CSS、JavaScript；管理服务使用Python标准库与SQLite；桌面外壳使用C# WinForms、WebView2。已有 `bridge.py` 继续承担共享抓取调度，QQ服务不另建学校抓取周期。

## 部署入口

本仓库发布自研源码，不包含第三方可执行程序、账号、密钥、数据库或学校通知附件。目前面向 **Windows已有组件部署**，不是空白电脑的一键离线整合包。

1. 准备Python 3.12+，将 [school-radar](https://github.com/MAIBAI-W/Campus-Notice-Classifier) 放在 `school-radar-pkg/school-radar/`。可用 `CAMPUS_DEPLOY_ROOT` 指定已有部署，`RADAR_DB` 指定数据库路径。
2. 按示例设置共享抓取桥配置（仓库使用 `bridge/`，兼容已有 `weixin-bridge/`）。当前统一启动流程仍保留微信网关/桥的检查，完整启动依赖请查看接入文档。
3. 独立安装兼容OneBot v11的QQ客户端，如 [NapCat](https://napneko.github.io/guide/boot/Shell)，由本人登录机器人账号。
4. 使用根目录 `start-all.bat` 启动；在管理页设置QQ身份、OneBot HTTP与事件上报、私聊名单及群订阅。已有进程会跳过。
5. 如需程序窗口，按 [桌面版构建说明](desktop/README.md) 构建并安装启动器；源码仓库不包含预构建安装包。

详细操作：

- [QQ与管理中心配置](qq-service/README.md)
- [Windows桌面程序构建与部署](desktop/README.md)
- [微信补充通道与附件工具](docs/wechat-setup.md)
- [OpenClaw Windows兼容补丁](patches/openclaw-worker-task-pool-datacloneerror.md)

## 目录

| 路径 | 作用 |
|---|---|
| `qq-service/` | QQ查询、订阅、权限、人工分发及管理服务 |
| `qq-service/web/` | 统一收件箱与管理前端 |
| `qq-service/competition_search.py` | 竞赛检索的标题约束和阶段过滤 |
| `desktop/` | Windows桌面外壳、安装脚本与边界测试 |
| `bridge/` | 共享抓取调度、微信桥和原通知工具 |
| `skill/school-notice/` | 微信端历史查询与附件工具技能 |
| `autostart/`、`patches/` | 启动模板与兼容维护说明 |

## 验证

```powershell
python -m unittest discover -s qq-service/tests -v
python -m unittest discover -s desktop -p test_desktop.py -v
```

当前通过71项服务隔离测试、4项桌面测试。测试使用临时状态与模拟QQ，不发送真实消息或调用真实模型；测试通过不代表所有通知都已真实送达，也不代替实际用户试用。

## 使用边界

- 查询只覆盖已配置来源与已抓取内容；时间、办理要求、政策及附件以学校原文为准。
- QQ当前不提供登录附件下载或个人教务身份绑定，不向群成员共享个人Cookie。
- 微信推送受会话等条件影响；服务在线和消息送达分别诊断。
- 当前管理端口和OneBot接口仅在本机使用。云端迁移需要重新配置访问认证、HTTPS、私网连接和运行监控。
- Windows安装器接管现有部署，升级/卸载启动器保留原账号配置、通知库与发送记录；不默认启用开机自启。

## 第三方来源与许可

自研范围包括桥接规则、QQ管理与查询服务、统一前端、桌面外壳以及投递状态/权限流程。采集与分类组件由 [Campus-Notice-Classifier](https://github.com/MAIBAI-W/Campus-Notice-Classifier) 提供，不归为本团队独立原创。

QQ接入使用NapCat / OneBot v11；自然语言解析使用DeepSeek；微信补充通道使用OpenClaw与腾讯微信插件；桌面使用Microsoft WebView2，安装构建使用Inno Setup。各组件保留上游许可与权利。学校标识不包含在本项目代码MIT授权内。

项目代码采用 [MIT License](LICENSE)。


## 采集器栏目修复（2026-10-28）

`crawler/` 是基于 [School Radar v1.0.0](https://github.com/MAIBAI-W/Campus-Notice-Classifier/tree/v1.0.0) 的独立采集器修改源码，遵循其 **GPL-3.0**，保留上游作者与许可证；本仓库根 MIT 许可不覆盖该目录。管理服务与采集器通过本机 HTTP / SQLite 交互。

该修复覆盖党务公示、学生工作、教学实践等公开栏目，修正相对文章链接、链接末尾空格及分块日期，保留原分类与数据库接口。完整修订记录见 [crawler/HHF-CHANGES.md](crawler/HHF-CHANGES.md)，栏目清单见 [crawler/column-coverage.json](crawler/column-coverage.json)。

如需复现修复后的采集器，在独立构建环境安装 requests、beautifulsoup4、lxml 与 PyInstaller，执行 `python crawler/build_exe.py`，替换部署目录内两个 exe 及匹配的 `_internal`，保留 `data/`。先备份并在采集空闲时操作；以 `--serve-only --no-open` 启动，不额外触发抓取。第三方采集器二进制仍不进入源码仓库。
