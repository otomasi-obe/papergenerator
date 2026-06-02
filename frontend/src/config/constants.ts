export const TIMEOUTS = {
  AI_GENERATION_MAX: 25 * 60 * 1000,
  AI_GENERATION_WARNING: 20 * 60 * 1000,
  JOB_POLL_INTERVAL: 3000,
  JOB_POLL_FAST: 1000,
  JOB_POLL_SLOW: 5000,
  QUOTA_REFRESH_INTERVAL: 30_000,
  AUTO_SAVE_DEBOUNCE: 1000,
  TOAST_DURATION: 3000,
  TOAST_DURATION_ERROR: 5000,
  API_TIMEOUT: 30_000,
  API_TIMEOUT_LONG: 60_000,
  RETRY_DELAY: 2000,
  MAX_RETRIES: 3,
} as const

export const LIMITS = {
  MAX_TITLE_LENGTH: 200,
  MAX_ABSTRACT_LENGTH: 500,
  MIN_ABSTRACT_LENGTH: 50,
  MAX_SECTION_LENGTH: 10000,
  MAX_PAPERS_PER_PAGE: 50,
  MAX_CHAT_MESSAGES_HISTORY: 12,
  MAX_REFERENCES: 100,
  MAX_AUTHORS: 20,
  MAX_FILE_SIZE: 10 * 1024 * 1024,
  MAX_IMAGE_SIZE: 5 * 1024 * 1024,
  ALLOWED_FILE_TYPES: ['.pdf', '.docx', '.txt', '.bib'],
  ALLOWED_IMAGE_TYPES: ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
} as const

export const STORAGE_KEYS = {
  PAPER: 'paper',
  THEME: 'theme',
  AUTH_TOKEN: 'auth_token',
  USER_PREFERENCES: 'user_prefs',
  DRAFT_PREFIX: 'draft_',
} as const

export const API_ENDPOINTS = {
  LOGIN: '/auth/login',
  LOGOUT: '/auth/logout',
  REFRESH: '/auth/refresh',
  PAPERS: '/papers',
  PAPER_DETAIL: (id: string) => `/papers/${id}`,
  PAPER_GENERATE: '/papers/generate',
  CHAT: '/chat',
  CHAT_STREAM: '/chat/stream',
  FILES_UPLOAD: '/files/upload',
  FILES_DOWNLOAD: (id: string) => `/files/${id}`,
} as const

export const FEATURE_FLAGS = {
  ENABLE_DARK_MODE: true,
  ENABLE_AUTO_SAVE: true,
  ENABLE_OFFLINE_MODE: false,
  ENABLE_ANALYTICS: false,
  ENABLE_BETA_FEATURES: false,
} as const

export const VALIDATION_RULES = {
  EMAIL: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
  PASSWORD_MIN_LENGTH: 8,
  PASSWORD_REQUIRE_UPPERCASE: true,
  PASSWORD_REQUIRE_NUMBER: true,
  PASSWORD_REQUIRE_SPECIAL: false,
  TITLE_MIN_LENGTH: 5,
  ABSTRACT_MIN_LENGTH: 50,
} as const

export default {
  TIMEOUTS,
  LIMITS,
  STORAGE_KEYS,
  API_ENDPOINTS,
  FEATURE_FLAGS,
  VALIDATION_RULES,
}
