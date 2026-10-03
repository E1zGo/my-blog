# 博客入口与联网试用部署（v0.10）

## 当前状态与方案

博客仓库为 `E1zGo/my-blog`，域名 `e1zgo.top`，DNS 指向 Vercel。ResearchPilot 使用 Python 常驻进程、SQLite、后台解析和持久原文件。Vercel 函数请求大小上限为 4.5 MB，且没有适合本项目的持久本地数据库目录，不能把现有后端复制到静态博客后直接运行。依据：[函数限制](https://vercel.com/docs/functions/limitations)、[SQLite 支持说明](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel)。

保持博客现有托管，博客导航进入 `/researchpilot` 介绍页；部署验收完成后，入口跳转至拟定子域名 `https://research.e1zgo.top`。后端单独放在有持久磁盘的 Linux 服务器上，同一 Git 仓库可使用 `apps/researchpilot/` 保存源码。博客构建仍在仓库根目录，输出仍为 `dist/`。

**模板已准备；真实服务器、DNS、证书和公网上传尚未验收。** 服务器地址、系统和已有 SSH 连接方式仍待提供。不要发送密码或私钥，不要将本机 `.env`、论文、数据库、账号会话或备份提交到博客仓库。

## 容量与状态

| 配置 | 默认值 | 口径 |
| --- | --- | --- |
| RP_MAX_UPLOAD_MB | 200 | 单文件，1 MB = 1024² 字节 |
| RP_MAX_PROJECTS | 20 | 每账号项目数；本机模式共用一个额度 |
| RP_MAX_SOURCES | 200 | 每项目资料数，重复导入不重复计数 |
| RP_MAX_STORAGE_MB | 2048 | 每账号已登记原文件及正在导入的预留空间 |
| RP_MAX_ACTIVE_TASKS / RP_MAX_ACTIVE_IMPORTS | 3 / 2 | 每账号正在执行或排队的任务，取消收尾仍占名额 |
| RP_MAX_TASKS_DAILY | 100 | 滚动 24 小时研究任务数，含失败和取消 |
| RP_MIN_FREE_DISK_MB | 512 | 数据所在磁盘低于该值时停止新增项目/任务/资料 |

原文件额度不包括数据库、备份、预览图片和浏览器草稿。重复文件在解析确认前需要临时空间，接近额度时可能需要先移除无用资料；重建索引不重复计算已有原文件。旧数据超过新额度仍可阅读，不自动删除。限制通过环境配置调整并重启生效；全站研究/后台导入仍分别最多 10/8 个，HTTP 请求同时最多 32 个（健康探针除外）。

「用量与运行」展示本人项目与额度；管理员另可查看本次启动的请求数量、近期错误、P95 耗时、队列和磁盘余量。统计不保存请求内容；近期耗时只取最近 5 分钟内最多 512 条样本，重启清零。该界面不是持续外部告警系统。

`/api/ready` 未登录也可访问，只返回 `ready` 或 `not_ready`；数据库、磁盘和管理员条件不满足时返回 503。它不验证模型效果、所有原文件校验值或外部备份。管理员的「自检与备份」提供更完整的数据检查。

## 目标服务器准备

以下是待在服务器实际验收的原生 systemd + Caddy 模板。先确认服务器系统、空闲磁盘、内存与现有站点，再选择路径；不能覆盖现有 Caddy 配置。需要 Python 3.12、venv、Caddy 2.10+。200 MB PDF 的展开内存取决于内容，2 GB 服务内存上限是试用起点，必须实测；内存不足会重启进程并将未完成任务标记失败。

1. 建立无交互登录的 `researchpilot` 服务账号。程序版本解压至 `/opt/researchpilot/releases/0.10.0/`；建立 `current` 链接。程序和虚拟环境由部署管理员维护，服务账号只需读取。不要把 `data/` 放在代码版本目录内。
2. 建立 `/var/lib/researchpilot/data` 和 `/var/lib/researchpilot/tmp`，仅服务账号可写。临时上传与数据库放在同一磁盘，方便磁盘保护检查。为升级备份至少预留现有数据量的额外空间。
3. 在版本目录创建 `.venv`，安装 `requirements-lock.txt`。复制 `deploy/production.env.example` 到 `/etc/researchpilot.env`，由 root 持有、researchpilot 组可读（0640），核对域名及绝对路径。不要把配置中的密钥传给浏览器或提交 Git。
4. 创建首个管理员。使用交互式终端，以服务账号进入程序目录，用同一环境配置运行：

   ```sh
   sudo -u researchpilot sh -c 'set -a; . /etc/researchpilot.env; set +a; cd /opt/researchpilot/current; exec .venv/bin/python -m researchpilot.accounts create-admin --username admin'
   ```

   密码在终端隐藏输入，15–128 字符。不要使用共享演示密码。首次部署默认建立空资料库；如要迁移个人论文，另行使用受保护的数据备份恢复流程。

5. 以相同环境运行 `.venv/bin/python -m researchpilot.ops preflight`。输出必须 `ok: true`，再安装 `deploy/researchpilot.service`、重载 systemd 并启动。服务仅监听 `127.0.0.1:8765`，使用单进程单 worker；不设置多 worker 或 reload。
6. DNS 新增 `research.e1zgo.top` 到服务器的记录，保留博客原有根域名/www 记录。只开放所需 SSH 和 HTTP/HTTPS 端口；8765 不对公网开放。若使用额外 CDN，先核对它的请求体与超时上限是否满足 200 MB。
7. 将 `deploy/Caddyfile.example` 的站点块合并进现有 Caddy 配置，执行 `caddy validate --config /etc/caddy/Caddyfile` 后再 reload。Caddy 自动处理该站点证书；应用只信任来自 `127.0.0.1` 的转发头。不要把 `--forwarded-allow-ips` 改为 `*`。反向代理请求体上限与应用 200 MB 加 multipart 余量一致；修改上传上限时须同步修改代理配置。

Caddy 配置依据 [reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) 和 [request_body](https://caddyserver.com/docs/caddyfile/directives/request_body)。Uvicorn 参数可用已安装版本的 `python -m uvicorn --help` 复核。现有 Docker 配置用于本机回环端口，未完成真实容器验收，不等同上述生产模板。

## 开放入口前验收

在外部网络执行 `python -m researchpilot.ops check --url https://research.e1zgo.top`，要求退出码 0；工具不跟随重定向，不关闭证书校验。然后验证：

- 未登录不能访问项目、PDF 和导出；管理员创建邀请，两个普通账号之间项目隔离；Cookie 有 Secure / HttpOnly。
- 实际大 PDF 导入、原文翻页、中文检索、取消及重启恢复；再检查磁盘和内存峰值。通过代理实测接近 200 MB 文件与超限 413，不能仅靠配置值宣称已支持公网 200 MB。
- 下载备份并在另一个目录恢复，核对 PDF 校验值和笔记；将备份保存到有访问控制的异地位置。管理员完整备份包含所有账号的数据，不应放到博客静态目录。
- 从外部确认 HTTPS 与 HTTP 跳转、8765 不可访问；配置外部健康检查、磁盘和 5xx 告警。当前探针工具可供现有监控系统调用，但尚未创建外部监控服务。

验收后将博客 `blog.config.ts` 中 `researchPilot.url` 填为上述 HTTPS 地址并设 `available: true`，构建并发布博客。入口只做普通链接，不跨域传递密码、会话或论文；账号在 ResearchPilot 页面登录。

## 升级与回滚

停止接收新任务，等待任务收尾，使用完整备份并验证。新版本先放新目录并安装依赖；停止旧服务后切换 `current`、运行 preflight，再启动服务和外部探针。保留旧代码和升级前数据备份；若发生不兼容迁移，停服后将备份恢复到新目录，修改数据路径再回滚，不直接覆盖正在使用的数据库。systemd 的自动重启不代替备份恢复。

当前阶段面向邀请制小范围试用。PDF 仍在同一进程解析，尚未实现独立受限解析进程，也未完成持续负载测试、真实模型质量/费用验收或公开注册服务验收。
