# E1zGo 的个人博客

Vue 3 + TypeScript + Vite，文章使用 Markdown 管理。

## 本地运行

建议使用 Node.js 22.18 或更新版本（内置类型擦除用于测试）。

```sh
npm ci
npm run dev
npm run build
npm run preview
npm test
```

`build` 会先检查 TypeScript，再生成 `dist/`。`preview` 可以检查实际发布文件。

## 写文章

在 `content/posts/` 新建 Markdown 文件，文件名就是文章网址的一部分。已发布文章尽量保留原文件名，避免旧链接失效。

```yaml
---
title: 文章标题
date: 2026-09-24
tags: [前端, 随笔]
excerpt: 一两句话介绍这篇文章。
updated: 2026-09-25  # 可选
cover: /cover.jpg   # 可选，图片放 public/
draft: false       # true 时不会显示在文章列表、标签和搜索里
---
```

正文从 `##` 二级标题开始即可。为兼容现有文章，与元信息标题相同的第一个 `#` 标题会自动略去。中文标题和重复标题会生成可分享的独立锚点。代码块支持常用语言高亮与复制。

文章摘要在构建时单独提取，正文进入文章页后才加载。阅读时间根据实际正文估算。`draft` 是展示控制，不适合保存敏感内容；源文件和构建文件都不应包含私密信息。

## 配置与样式

- `blog.config.ts`：作者、头像、社交链接、每页数量和功能开关。
- `src/style.css`：全站颜色、字体、布局、响应式与阅读排版。主题变量集中在文件开头。
- `src/pages/index.vue`：首页文案与山景插画。
- `src/components/ui/GiscusComment.vue`：现有 Giscus 仓库配置；读者展开评论时才连接服务。

浅色 / 深色模式默认跟随系统，手动选择会保存。搜索支持 Ctrl/Cmd + K、方向键、Enter 和 Esc。手机端提供导航菜单、文章筛选和折叠目录。

## 发布注意

沿用现有托管平台，把 `dist/` 作为发布目录。项目使用 history 路由，托管平台需要将 `/posts/*`、`/tags/*` 等非文件请求回退到 `index.html`。本地预览支持回退，但不能代替对线上托管配置的检查。

文章原有地址和站点域名保持不变。
