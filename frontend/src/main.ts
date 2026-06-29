import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index'
import { applyInitialTheme } from './stores/theme'
import { vAutosize } from './directives/autosize'
import { setupErrorHandler } from './services/globalErrorHandler'
import { logger } from './utils/logger'
import api from './api/index'
import './style.css'

// Wire logger to axios so frontend logs actually reach the backend
logger.setApi(api)

applyInitialTheme()

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.directive('autosize', vAutosize)

setupErrorHandler(app)

window.addEventListener('error', (event: ErrorEvent) => {
  logger.error('Uncaught error', {
    message: event.message,
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
    error: event.error?.stack || String(event.error)
  })
})

logger.info('Application initialized', {
  mode: import.meta.env.MODE,
  base: import.meta.env.BASE_URL
})

app.mount('#app')

if (import.meta.env.DEV || import.meta.env.MODE === 'development') {
  (window as any).__pinia = pinia
}
