import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useLanguageStore = defineStore('language', () => {
  const locale = ref<'id' | 'en'>(
    (localStorage.getItem('locale') as 'id' | 'en') || 'id'
  )

  function setLocale(lang: 'id' | 'en') {
    locale.value = lang
    localStorage.setItem('locale', lang)
  }

  return {
    locale,
    setLocale
  }
})
