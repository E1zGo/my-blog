# ResearchPilot 与博客

博客导航已增加 ResearchPilot 介绍页 `/researchpilot`，电脑与手机导航共用入口。当前线上工作台尚未部署，页面显示「上线准备中」；不会向访客提供不可用的后端链接。

ResearchPilot 源码放在 `apps/researchpilot/`。根目录依然是原有 Vue / Vite 博客，Vercel 构建命令仍为 `npm run build`，输出仍为 `dist/`；后端目录不属于静态站点输出，也不应在 Vercel 中作为 Python 函数部署。`.vercelignore` 排除后端交付目录，避免将其随博客上传。

拟定工作台地址为 `https://research.e1zgo.top`，需要有持久磁盘的服务器。具体环境配置、Caddy / systemd 模板、管理员初始化、健康检查、大文件验收和回滚说明见 [后端部署说明](../apps/researchpilot/docs/deployment.md)。

## 后端上线后启用入口

1. 在外部网络验证 HTTPS、登录、账号隔离、原文预览和大文件上传；执行后端 `python -m researchpilot.ops check --url https://research.e1zgo.top`。
2. 将根目录 `blog.config.ts` 的 `researchPilot.url` 填为已验证的 HTTPS 站点地址，将 `available` 改为 `true`。
3. 执行 `npm test` 与 `npm run build`，发布博客；访问 `/researchpilot` 并验证「进入 ResearchPilot」跳转。

博客和工作台使用各自的站点，不共享登录状态。这里只保存源码，个人论文、数据库、备份、`.env` 和模型密钥不可提交。后端持续集成在 `.github/workflows/researchpilot.yml` 中独立执行。
