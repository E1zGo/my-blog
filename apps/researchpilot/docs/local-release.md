# v0.10 本机测试版与部署准备

本版支持本机安装、数据备份、可选账号、用量限制与运行检查。启用账号见 [账号与迁移说明](accounts.md)，博客接入与服务器模板见 [部署说明](deployment.md)；真实模型服务和公网部署未验收。默认 offline / BM25，单文件上传 200 MB；版本号不代表公开服务的完成百分比。

## 两类 ZIP

| 文件 | 用途 | 内容 |
| --- | --- | --- |
| `researchpilot-0.10.0-local.zip` | 在另一目录或电脑安装程序 | 源码、前端、合成示例、锁定依赖、测试、部署模板、文档和发布清单 |
| `researchpilot-backup-日期-编号.zip` | 备份/迁移个人研究数据 | 一致的数据库快照、已登记原文件和校验清单 |

源码交付包不带 `.env`、`data/`、虚拟环境、个人报告或备份；数据备份不包含代码、运行依赖、浏览器未保存草稿和阅读进度。账号模式的备份保留用户与项目归属，剔除会话、邀请码与限流记录，恢复后必须重新登录并配置 RP_AUTH_MODE=accounts。正式笔记、已归档笔记、实验记录、任务及引用快照均在数据库内。

## 在新目录安装

1. 将源码交付包解压到新目录，安装 Python 3.12（本机验证版本 3.12.14）。
2. 在该目录运行 `py -3.12 -m venv .venv`，再运行 `.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt`。第一次安装需访问依赖源或使用准备好的离线 wheel 包；交付包没有内置 Python。
3. 双击 `start.bat`，或运行 `start.ps1`；启动脚本先执行自检。第一次启动创建空数据库，打开 `http://127.0.0.1:8765/`，可导入自己的论文或内置示例。
4. 无需模型密钥即可使用离线流程。若要迁移旧数据，先完成下方恢复步骤，再启动服务。

若自检发现缺少依赖、数据库异常或已登记原文件缺失，会阻止快捷启动并显示检查结果。请先补齐依赖/原文件或从备份恢复，不要删除现有数据库来消除提示。所有资料的原文件均已遗失但仍需进入系统补传时，可用 README 中的 uvicorn 命令直接启动；应先备份现存目录并核对错误原因。

## 备份与升级

在网页导航「自检与备份」下载 ZIP，或运行 README 中的 `backup --output` 命令。生成前完成或取消后台任务，并保存笔记。查看自检中的“仅有提取文本的资料”提示：教学示例没有原文件属正常情况；旧论文缺失原文件副本时，备份也无法补出原文。

升级前运行 `verify` 检查备份，再在新程序目录运行 `restore 备份.zip --to data-restored`。工具先在临时目录校验每个文件的大小、SHA256、数据库完整性、外键与原文件清单，然后建立新的目标目录。已有目标（包括空目录）会被拒绝。工具不修改当前 `.env`，也不自动切换或重启服务。

确认新目录的 `doctor --data-dir data-restored` 结果后，停止旧服务，设置新程序 `.env` 的 `RP_DATA_DIR=./data-restored` 并启动。打开原论文、历史任务和笔记核对；保留旧程序及其原数据目录，出现问题时停止新服务并启动旧版本。回退后看不到仅在新目录中创建的数据，请先导出需要保留的内容。

备份格式版本为 1，当前只支持本工具生成的 ZIP；过去手动保存的 `.sqlite3` 文件不是完整 ZIP 备份。完整 ZIP 默认不压缩，避免大 PDF 无效重复压缩；SHA256 用于发现损坏，不验证发送者身份。只恢复可信备份。容量边界：10 GB 展开总量、10000 个文件条目、4 MB 清单。大资料库需要预留备份和校验的临时磁盘空间。

## 发布验收与自动化

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/build_release.py
```

还需对 `frontend/*.js` 执行 `node --check`。构建脚本对明确目录及扩展名取文件，拒绝链接和覆盖现有输出，包内附 `release-manifest.json` 文件校验清单，命令输出 ZIP 的 SHA256。相同文件内容在本机连续构建得到相同 ZIP 校验值；不承诺不同压缩器版本的字节完全一致。

`.github/workflows/checks.yml` 已定义 Windows / Ubuntu、Python 3.12 的依赖检查、自动测试、前端语法检查和本机包构建。该配置需项目进入 GitHub 后才会执行；目前不代表已经取得远端 CI 通过记录。Actions 用法参照官方 [checkout](https://github.com/actions/checkout)、[setup-python](https://github.com/actions/setup-python)、[setup-node](https://github.com/actions/setup-node)。

备份实现依据 Python 的 [SQLite backup 接口](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup)；ZIP 按白名单逐项读取，不直接解压外部文件名，参见 [zipfile 文档](https://docs.python.org/3/library/zipfile.html)。

## 下一阶段边界

| 阶段 | 当前状态 | 剩余验收 |
| --- | --- | --- |
| 本机数据交付 | v0.8 已实现 | 在另一台真实电脑安装；持续收集试用问题 |
| 账号权限基础 | v0.9 已实现，本机默认未启用 | 设置管理员密码后启用，持续验证实际用户流程 |
| 上线前运维基础 | v0.10 已实现账号额度、并发管理、运行状态和检查工具 | 在目标环境核对磁盘、代理和进程限制 |
| 小范围联网试用 | 尚未开展 | 服务器、域名/HTTPS、隔离解析、异地备份及外部告警 |
| LLM 科研助手 | 接口已有，真实效果未验收 | 确定模型服务，真实论文题集，中文回答/引用支持度、费用与失败案例 |
| 公网正式服务 | 尚未部署 | 安全和负载验收、备份恢复演练、运行告警、升级回滚、用户反馈闭环 |

Docker 配置仍未在本机 Docker 引擎构建验证；账号系统为可选启用；没有自动执行训练、OCR 或公网发布。当前仍需单进程单 worker，不能通过直接增加 worker 数实现安全扩容。
