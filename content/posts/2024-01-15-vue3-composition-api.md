---
title: Vue 3 Composition API 深度实践指南
date: 2026-02-21
updated: 2026-02-22
tags: [Vue3, 前端]
excerpt: 从 Options API 到 Composition API 的思维转变，以及如何组织复杂业务逻辑的最佳实践。
---

# Vue 3 Composition API 深度实践指南

Vue 3 的 Composition API 是一种全新的组织组件逻辑的方式，它让代码复用和逻辑组织变得更加灵活。

## 为什么需要 Composition API？

在大型 Vue 2 项目中，Options API 会面临一个核心问题：**同一个逻辑关注点的代码被迫分散在不同的选项中**。

```javascript
// Options API — 逻辑分散
export default {
  data() {
    return { count: 0, user: null }
  },
  computed: {
    doubleCount() { return this.count * 2 }
  },
  methods: {
    increment() { this.count++ },
    async fetchUser() { /* ... */ }
  }
}
```

## Composition API 的核心思想

Composition API 让你可以按**逻辑关注点**组织代码：

```typescript
import { ref, computed } from 'vue'

function useCounter() {
  const count = ref(0)
  const doubleCount = computed(() => count.value * 2)
  function increment() { count.value++ }
  return { count, doubleCount, increment }
}

const { count, doubleCount, increment } = useCounter()
```

## setup 语法糖

使用 `<script setup>` 让代码更简洁：

```typescript
import { ref, computed, onMounted } from 'vue'

const count = ref(0)
const doubled = computed(() => count.value * 2)

onMounted(() => console.log('组件挂载完成'))
```

## 总结

Composition API 带来了更好的逻辑复用、类型推断和代码组织方式。对于新项目，推荐直接使用 Composition API + `<script setup>` 的组合。

> 理解 Composition API 最好的方式就是实际动手写几个 composable 函数。
