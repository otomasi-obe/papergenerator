import type { AxiosInstance } from 'axios'

type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL'

const LOG_LEVELS: Record<LogLevel, number> = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
  CRITICAL: 4
}

interface LogEntry {
  ts: string
  level: LogLevel
  msg: string
  req_id: string | null
  url: string | null
  [key: string]: unknown
}

class Logger {
  private level: number
  private requestId: string | null
  private context: Record<string, unknown>
  private buffer: LogEntry[]
  private _flushInterval: number | null
  private maxBufferSize: number
  private flushIntervalMs: number
  private api: AxiosInstance | null

  constructor() {
    this.level = this._getLogLevel()
    this.requestId = null
    this.context = {}
    this.buffer = []
    this._flushInterval = null
    this.maxBufferSize = 50
    this.flushIntervalMs = 10000
    this.api = null
    
    if (typeof window !== 'undefined') {
      this._startFlushInterval()
      window.addEventListener('beforeunload', () => this._flush())
    }
  }

  setApi(api: AxiosInstance): void {
    this.api = api
  }

  private _getLogLevel(): number {
    const env = import.meta.env.VITE_LOG_LEVEL || 'INFO'
    return LOG_LEVELS[env.toUpperCase() as LogLevel] || LOG_LEVELS.INFO
  }

  private _generateRequestId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
  }

  private _startFlushInterval(): void {
    this._flushInterval = window.setInterval(() => {
      this._flush()
    }, this.flushIntervalMs)
  }

  stopFlushInterval(): void {
    if (this._flushInterval) {
      clearInterval(this._flushInterval)
      this._flushInterval = null
    }
  }

  private _shouldLog(level: LogLevel): boolean {
    return LOG_LEVELS[level] >= this.level
  }

  private _formatLog(level: LogLevel, message: string, data: Record<string, unknown> = {}): LogEntry {
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

  private _log(level: LogLevel, message: string, data: Record<string, unknown> = {}): void {
    if (!this._shouldLog(level)) return

    const logEntry = this._formatLog(level, message, data)

    if (import.meta.env.DEV || LOG_LEVELS[level] >= LOG_LEVELS.WARN) {
      const consoleMethod = level === 'ERROR' || level === 'CRITICAL' ? 'error' : 
                           level === 'WARN' ? 'warn' : 'log'
      console[consoleMethod](`[${level}]`, message, data)
    }

    this.buffer.push(logEntry)
    if (this.buffer.length >= this.maxBufferSize) {
      this._flush()
    }
  }

  private async _flush(): Promise<void> {
    if (this.buffer.length === 0 || !this.api) return

    const logs = [...this.buffer]
    this.buffer = []

    try {
      await this.api.post('/api/logs/frontend', { logs }, { timeout: 5000 })
    } catch (error) {
      console.error('[Logger] Failed to send logs to backend:', (error as Error).message)
    }
  }

  setRequestId(requestId?: string): string {
    this.requestId = requestId || this._generateRequestId()
    return this.requestId
  }

  getRequestId(): string | null {
    return this.requestId
  }

  setContext(context: Record<string, unknown>): void {
    this.context = { ...this.context, ...context }
  }

  clearContext(): void {
    this.context = {}
  }

  debug(message: string, data?: Record<string, unknown>): void {
    this._log('DEBUG', message, data)
  }

  info(message: string, data?: Record<string, unknown>): void {
    this._log('INFO', message, data)
  }

  warn(message: string, data?: Record<string, unknown>): void {
    this._log('WARN', message, data)
  }

  error(message: string, data?: Record<string, unknown>): void {
    this._log('ERROR', message, data)
  }

  critical(message: string, data?: Record<string, unknown>): void {
    this._log('CRITICAL', message, data)
  }

  logApiCall(method: string, url: string, status: number, duration: number, error: Error | null = null): void {
    const data: Record<string, unknown> = {
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

  logUserAction(action: string, details: Record<string, unknown> = {}): void {
    this.info(`User action: ${action}`, { action, ...details })
  }

  logPerformance(operation: string, duration: number, threshold = 1000): void {
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
