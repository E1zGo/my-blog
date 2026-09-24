import { useDark, useToggle } from '@vueuse/core'
// All consumers share the same storage key; new visitors follow their system theme.
export function useDarkMode() {
  const isDark = useDark({ storageKey: 'blog-theme', valueDark: 'dark', valueLight: '' })
  const toggleValue = useToggle(isDark)
  const toggle = () => { toggleValue() }
  return { isDark, toggle }
}
