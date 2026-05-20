import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index.js'
import { applyInitialTheme } from './stores/theme.js'
import './style.css'

// Apply theme before mount to avoid a flash of the wrong colors.
applyInitialTheme()

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.mount('#app')

// Expose pinia for E2E test debugging in dev only
if (import.meta.env.DEV || import.meta.env.MODE === 'development') {
  window.__pinia = pinia
}
