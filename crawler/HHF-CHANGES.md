# School Radar v1.0.0 栏目修复（HHF，2026-10-28）

来源：https://github.com/MAIBAI-W/Campus-Notice-Classifier/tree/v1.0.0

本目录为该版本的独立采集器源码及本次修改，沿用上游 GPL-3.0（见 LICENSE），不改变上游作者、许可或分类规则。它与东方知讯管理服务通过本机 HTTP 和 SQLite 交互。

本次修改：

- 22 站点公开导航审计后扩展显式栏目清单（column-coverage.json），保持站点 key/name 不变；不含需要登录的栏目。
- 先解析并清理相对 URL，再识别文章；修复 `info/...`、前后空格，保留原栏目编号。
- 识别日期卡片中分开的日与年月；详情优先处理尚未入库的通知，按发布日期排序。
- 自动发现补充党务/组织建设/教学/学生工作等栏目，跳过认证入口，避免重复请求已配置栏目。
- 分类、模型建议、数据库结构和 API 不变；抓取周期仍由东方知讯现有调度控制。

构建：Python 3.12、requests、beautifulsoup4、lxml、PyInstaller。运行上游 build_exe.py（默认 onedir / noupx，含控制台和无控制台两个版本）。构建目录、data、缓存和工具不属于提交源码。

验证：`python cases.py`、`python -m unittest test_columns -v`；`--reclassify` 仅在隔离测试数据库运行；`--doctor` 仅探测公开首页，不启动推送。

更改后的二进制只用于本机部署，发布时须同时提供本目录对应源码和 GPL 许可证。
