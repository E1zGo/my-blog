import { createRouter, createWebHistory } from 'vue-router'
import routes from 'virtual:generated-pages'

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return { ...savedPosition, behavior: 'instant' }
    if (to.hash) {
      try {
        const element = document.getElementById(decodeURIComponent(to.hash.slice(1)))
        // An asynchronously loaded article handles its own initial fragment once ready.
        return element ? { el: element, top: 100, behavior: 'instant' } : false
      } catch { return { top: 0, behavior: 'instant' } }
    }
    if (to.path === from.path) return false
    return { top: 0, behavior: 'instant' }
  },
})

export default router
