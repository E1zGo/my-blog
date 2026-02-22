import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const searchOpen = ref(false)
  const menuOpen = ref(false)

  function openSearch() { searchOpen.value = true }
  function closeSearch() { searchOpen.value = false }
  function toggleMenu() { menuOpen.value = !menuOpen.value }
  function closeMenu() { menuOpen.value = false }

  return { searchOpen, menuOpen, openSearch, closeSearch, toggleMenu, closeMenu }
})
