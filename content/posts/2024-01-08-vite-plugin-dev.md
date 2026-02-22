---
title: Vite 插件开发从入门到上手
date: 2026-02-22
tags: [Vite, 工程化, 前端]
excerpt: Rollup 插件机制与 Vite 专属钩子的全面解析，附带实战插件开发案例。
---

# Vite 插件开发从入门到上手

Vite 的插件系统兼容 Rollup 插件 API，同时提供了一些 Vite 专属的钩子。

## 插件的基本结构

```typescript
import type { Plugin } from 'vite'

function myPlugin(): Plugin {
  return {
    name: 'vite-plugin-my',
    enforce: 'pre',
    configResolved(config) {
      console.log('配置已解析:', config.mode)
    },
    transform(code, id) {
      if (!id.endsWith('.vue')) return
      return code.replace(/__VERSION__/g, '1.0.0')
    },
  }
}

export default myPlugin
```

## 实战：Markdown 信息注入插件

```typescript
import type { Plugin } from 'vite'
import { readFileSync } from 'fs'

export function markdownMetaPlugin(): Plugin {
  return {
    name: 'markdown-meta',
    transform(code, id) {
      if (!id.endsWith('.md')) return
      return `${code}\nexport const __injected = true`
    },
  }
}
```

## 常用钩子速查

- `config` — 修改 Vite 配置
- `configResolved` — 读取最终配置
- `transform` — 修改源码
- `resolveId` — 自定义路径解析
- `load` — 虚拟模块
- `handleHotUpdate` — 自定义热更新
