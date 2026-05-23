import api from '@/api'

const LOG_LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
  CRITICAL: 4
}

class Logger {
  constructor() {
    this.level = this._getLogLevel()
    this.requestId = null
    this.context = {}
    this.buffer = []
    this.flushInterval = null
    this.maxBufferSize = 50
    this.flushIntervalMs = 10000
    
    if (typeof window !== 'undefined') {
      this._startFlushInterval()
      window.addEventListener('beforeunload', () => this._flush())
    }
  }

  _getLogLevel() {
    const env = import.meta.env.VITE_LOG_LEVEL || 'INFO'
    return LOG_LEVELS[env.toUpperCase()] || LOG_LEVELS.INFO
  }

  _generateRequestId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
  }

  _startFlushInterval() {
    this.flushInterval = setInterval(() => {
      this._flush()
    }, this.flushIntervalMs)
  }

  _shouldLog(level) {
    return LOG_LEVELS[level] >= this.level
  }

  _formatLog(level, message, data = {}) {
    return {
      ts: new Date().toISOString(),
      level,
      msg: message,
      req_id: this.requestId,
      url: typeof window !== 'undefined' ? window.location.pathname : null,
      ...this.context,
      ...data
    }
  }

  _log(level, message, data = {}) {
    if (!this._shouldLog(level)) return

    const logEntry = this._formatLog(level, message, data)

    if (import.meta.env.DEV || LOG_LEVELS[level] >= LOG_LEVELS.WARN) {
      const consoleMethod = level === 'ERROR' || level === 'CRITICAL' ? 'error' : 
                           level === 'WARN' ? 'warn' : 'log'
      console[consoleMethod](`[${level}]`, message, data)
    }

    if (LOG_LEVELS[level] >= LOG_LEVELS.ERROR) {
      this.buffer.push(logEntry)
      if (this.buffer.length >= this.maxBufferSize) {
        this._flush()
      }
    }
  }

  async _flush() {
    if (this.buffer.length === 0) return

    const logs = [...this.buffer]
    this.buffer = []

    try {
      await api.post('/api/logs/frontend', { logs }, { timeout: 5000 })
    } catch (error) {
      console.error('[Logger] Failed to send logs to backend:', error.message)
    }
  }

  setRequestId(requestId) {
    this.requestId = requestId || this._generateRequestId()
    return this.requestId
  }

  getRequestId() {
    return this.requestId
  }

  setContext(context) {
    this.context = { ...this.context, ...context }
  }

  clearContext() {
    this.context = {}
  }

  debug(message, data) {
    this._log('DEBUG', message, data)
  }

  info(message, data) {
    this._log('INFO', message, data)
  }

  warn(message, data) {
    this._log('WARN', message, data)
  }

  error(message, data) {
    this._log('ERROR', message, data)
  }

  critical(message, data) {
    this._log('CRITICAL', message, data)
  }

  logApiCall(method, url, status, duration, error = null) {
    const data = {
      method,
      url,
      status,
      duration_ms: duration
    }

    if (error) {
      data.error = error.message || String(error)
      this.error(`API ${method} ${url} failed`, data)
    } else if (status >= 400) {
      this.warn(`API ${method} ${url} returned ${status}`, data)
    } else {
      this.debug(`API ${method} ${url} completed`, data)
    }
  }

  logUserAction(action, details = {}) {
    this.info(`User action: ${action}`, { action, ...details })
  }

  logPerformance(operation, duration, threshold = 1000) {
    const data = { operation, duration_ms: duration }
    if (duration > threshold) {
      this.warn(`Slow operation: ${operation}`, data)
    } else {
      this.debug(`Performance: ${operation}`, data)
    }
  }
}

export const logger = new Logger()

export default logger
