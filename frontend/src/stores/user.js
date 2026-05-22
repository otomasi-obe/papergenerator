import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useUserStore = defineStore('user', () => {
  const preferences = ref({
    experience_level: 'auto',
    show_technical_details: false,
    workflow_style: 'guided'
  })

  const detectedLevel = ref('intermediate')

  function detectUserLevel(indicators) {
    const beginnerSignals = [
      'bingung', 'tidak tahu', 'gimana', 'contoh', 'help',
      'cara', 'bagaimana', 'tolong', 'bantu'
    ]
    const advancedSignals = [
      'langsung generate', 'skip', 'bulk', 'fast',
      'technical', 'debug', 'api', 'parameter'
    ]
    
    const text = (indicators.lastMessage || '').toLowerCase()
    
    const beginnerScore = beginnerSignals.filter(s => text.includes(s)).length
    const advancedScore = advancedSignals.filter(s => text.includes(s)).length
    
    if (advancedScore > beginnerScore && advancedScore >= 2) {
      detectedLevel.value = 'advanced'
    } else if (beginnerScore > advancedScore && beginnerScore >= 2) {
      detectedLevel.value = 'beginner'
    } else {
      detectedLevel.value = 'intermediate'
    }
    
    return detectedLevel.value
  }

  const effectiveLevel = computed(() => {
    return preferences.value.experience_level === 'auto' 
      ? detectedLevel.value 
      : preferences.value.experience_level
  })

  function setPreference(key, value) {
    preferences.value[key] = value
    localStorage.setItem('user_preferences', JSON.stringify(preferences.value))
  }

  function loadPreferences() {
    const stored = localStorage.getItem('user_preferences')
    if (stored) {
      try {
        preferences.value = { ...preferences.value, ...JSON.parse(stored) }
      } catch (e) {
        console.warn('Failed to load user preferences:', e)
      }
    }
  }

  return {
    preferences,
    detectedLevel,
    effectiveLevel,
    detectUserLevel,
    setPreference,
    loadPreferences
  }
})
