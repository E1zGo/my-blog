import { useLocalStorage } from '@vueuse/core'
import { watch } from 'vue'

export function useDarkMode() {
  const isDark = useLocalStorage('blog-dark-mode', false)

  function apply() {
    document.documentElement.classList.toggle('dark', isDark.value)
  }

  watch(isDark, apply, { immediate: true })

  function toggle() {
    isDark.value = !isDark.value
  }

  return { isDark, toggle }
}
