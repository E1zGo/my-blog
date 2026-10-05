> 2026-10-05 更新：浏览器智能精读已实现中文模型问答、本地 OCR、公式识别与辅助推导、按页全文翻译。配置方式、数据流和验收边界请先阅读 [智能精读说明](researchpilot-intelligence.md)。下文为基础浏览器版的交付记录，其中“不支持 OCR/翻译/模型”的旧边界已被本次更新取代。

# ResearchPilot 浏览器本地版

正式入口：博客导航 → `/researchpilot` → `/research`。使用现有 Vercel 静态托管，无需独立服务器、登录账号、数据库或文件存储服务。`apps/researchpilot/` 保留完整 Python 本机版源码，与浏览器版的资料互不共享。

## 当前提供

- 选择或拖入 PDF，单篇最多 **209,715,200 字节（200 MiB，界面简写 MB）**、300 页、100 万提取字符；每次一篇，最多保留 20 篇。
- PDF.js 在本地 Worker 解析。原文件与文本索引在 IndexedDB 的同一事务中提交，SHA256 去重；失败不显示保存成功。导入可取消，解析超时 3 分钟停止。
- 原版式逐页画布预览，查看数学公式和图片；阅读位置自动保存。仅渲染页面，不执行 PDF 脚本或表单动作。
- 中文科研术语扩展与英文关键词 BM25 检索，显示实际采用的英文对照，支持页码范围；匹配结果只引用原文，不生成答案。双栏恢复是启发式方法，复杂版式以原文为准。
- 每篇最多 200 条笔记，引用带 PDF 物理页码；草稿缓存、笔记保存、Markdown 导出、原文下载及单篇删除。

## 使用边界

资料属于当前 **浏览器 + 网站域名**。`e1zgo.top` 应统一跳转到 `www.e1zgo.top`；预览域名与正式域名的本地资料互不可见。没有跨设备同步、云备份、OCR、通用翻译或大模型回答。PDF 没有文本层的页仍可看原文，但无法检索。

浏览器决定实际存储配额。剩余空间是估算，可能不足以导入 200 MB 文件；大文件会占用较多内存，手机和低内存设备建议拆分 PDF。持久保存请求由浏览器决定，不能阻止用户手动清理网站数据。隐私模式关闭、浏览器清理或卸载可能删除资料，请保留原 PDF，定期导出笔记。

网页首次加载需要网络；当前没有 Service Worker 或可安装的断网网页包。解析时字体、CMap 和解码器均从本站静态目录读取，不向第三方发送论文内容。

## 构建与上线

使用 Node.js 24：`npm ci --ignore-scripts`、`npm test`、`npm run build`。构建会将锁定版 PDF.js 的字体、CMap、WASM 和许可证复制到 `public/pdfjs/`，再生成 `dist/`。这些可重建资源不提交 Git。Vercel 的构建命令仍为 `npm run build`，输出为 `dist/`；`vercel.json` 保留 SPA 路由回退。

持续集成：`.github/workflows/blog.yml` 运行原博客和浏览器版测试、类型检查及生产构建。Python 本机版使用独立的 `researchpilot.yml`。

发布验收：打开 `/researchpilot` 跳转工作台；导入 PDF、中文检索、跳页、保存带引用笔记、刷新恢复、导出、重复导入。检查原文含公式页面。手机宽度检查不横向溢出。个人 PDF、数据库、备份和密钥不能进入 Git 或 `public/`。

## 实现依据

- [Vercel 函数限制](https://vercel.com/docs/functions/limitations)：本版不通过函数接收 PDF，200 MB 限制在浏览器本地执行。
- [PDF.js 示例](https://mozilla.github.io/pdf.js/examples/) 与 [API](https://mozilla.github.io/pdf.js/api/draft/module-pdfjsLib.html)。
- [IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API) 与 [存储配额估算](https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/estimate)。

若未来需要云端账号和跨设备同步，需另行设计服务端存储、用户隔离、任务队列和费用控制。原先的 [Python 服务部署说明](../apps/researchpilot/docs/deployment.md) 仅作为有独立服务器时的可选方案。
