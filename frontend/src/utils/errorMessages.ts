type UserLevel = 'beginner' | 'intermediate' | 'advanced'

interface ErrorMessageConfig {
  message: string
  action: string
  showDetails: boolean
}

type ErrorMessages = {
  [key: string]: {
    [K in UserLevel]: ErrorMessageConfig
  }
}

const ERROR_MESSAGES: ErrorMessages = {
  VALIDATION_FAILED: {
    beginner: {
      message: 'Ada yang salah dengan input kamu. Coba cek lagi ya.',
      action: 'Fix',
      showDetails: false
    },
    intermediate: {
      message: 'Validasi gagal. Periksa input dan coba lagi.',
      action: 'Fix',
      showDetails: true
    },
    advanced: {
      message: 'Validation failed. Check input fields and constraints.',
      action: 'Fix',
      showDetails: true
    }
  },
  INVALID_INPUT: {
    beginner: {
      message: 'Input tidak valid. Coba cek lagi ya.',
      action: 'Fix',
      showDetails: false
    },
    intermediate: {
      message: 'Input tidak valid. Periksa format dan coba lagi.',
      action: 'Fix',
      showDetails: true
    },
    advanced: {
      message: 'Invalid input format. Check validation rules.',
      action: 'Fix',
      showDetails: true
    }
  },
  UNAUTHORIZED: {
    beginner: {
      message: 'Kamu belum login. Login dulu ya 😊',
      action: 'Login',
      showDetails: false
    },
    intermediate: {
      message: 'Sesi berakhir. Silakan login kembali.',
      action: 'Login',
      showDetails: false
    },
    advanced: {
      message: 'Unauthorized. Token expired or invalid.',
      action: 'Login',
      showDetails: true
    }
  },
  PAPER_NOT_FOUND: {
    beginner: {
      message: 'Paper tidak ditemukan. Mungkin sudah dihapus.',
      action: 'Back',
      showDetails: false
    },
    intermediate: {
      message: 'Paper tidak ditemukan atau sudah dihapus.',
      action: 'Back',
      showDetails: true
    },
    advanced: {
      message: 'Paper not found. Resource may have been deleted.',
      action: 'Back',
      showDetails: true
    }
  },
  QUOTA_EXCEEDED: {
    beginner: {
      message: 'Kuota kamu habis. Hubungi admin ya.',
      action: 'Contact',
      showDetails: false
    },
    intermediate: {
      message: 'Kuota token habis. Hubungi admin untuk menambah kuota.',
      action: 'Contact',
      showDetails: true
    },
    advanced: {
      message: 'Token quota exceeded. Contact admin for quota increase.',
      action: 'Contact',
      showDetails: true
    }
  },
  RATE_LIMIT_EXCEEDED: {
    beginner: {
      message: 'Terlalu banyak request. Tunggu sebentar ya 😊',
      action: 'Wait',
      showDetails: false
    },
    intermediate: {
      message: 'Rate limit exceeded. Tunggu 1 menit dan coba lagi.',
      action: 'Wait',
      showDetails: true
    },
    advanced: {
      message: 'Rate limit exceeded. Wait 60s before retry.',
      action: 'Wait',
      showDetails: true
    }
  },
  UPSTREAM_TIMEOUT: {
    beginner: {
      message: 'AI sedang sibuk. Coba lagi dalam 30 detik ya 😊',
      action: 'Retry',
      showDetails: false
    },
    intermediate: {
      message: 'Server timeout. Retry dalam 30 detik atau cek koneksi.',
      action: 'Retry',
      showDetails: true
    },
    advanced: {
      message: 'Upstream timeout after 180s. Check network/API status.',
      action: 'Retry',
      showDetails: true
    }
  },
  TOOL_EXECUTION_FAILED: {
    beginner: {
      message: 'Ada yang salah. Coba kirim ulang pesanmu.',
      action: 'Retry',
      showDetails: false
    },
    intermediate: {
      message: 'Tool execution gagal. Coba lagi atau ubah request.',
      action: 'Retry',
      showDetails: true
    },
    advanced: {
      message: 'Tool execution failed. Check logs for details.',
      action: 'Retry',
      showDetails: true
    }
  },
  PAPER_LOCKED: {
    beginner: {
      message: 'Paper sedang diproses. Tunggu sebentar ya 😊',
      action: 'Wait',
      showDetails: false
    },
    intermediate: {
      message: 'Paper locked: generation in progress. Wait or cancel.',
      action: 'Cancel',
      showDetails: true
    },
    advanced: {
      message: 'Paper locked by active operation. Cancel or wait for completion.',
      action: 'Cancel',
      showDetails: true
    }
  },
  NETWORK_ERROR: {
    beginner: {
      message: 'Koneksi terputus. Cek internet kamu ya.',
      action: 'Retry',
      showDetails: false
    },
    intermediate: {
      message: 'Network error. Check connection and retry.',
      action: 'Retry',
      showDetails: true
    },
    advanced: {
      message: 'Network error. Check connection, proxy, or firewall.',
      action: 'Retry',
      showDetails: true
    }
  },
  DATABASE_ERROR: {
    beginner: {
      message: 'Ada masalah di server. Coba lagi sebentar.',
      action: 'Retry',
      showDetails: false
    },
    intermediate: {
      message: 'Database error. Coba lagi atau hubungi admin.',
      action: 'Retry',
      showDetails: true
    },
    advanced: {
      message: 'Database error. Check logs and connection pool.',
      action: 'Retry',
      showDetails: true
    }
  },
  INTERNAL_ERROR: {
    beginner: {
      message: 'Ada masalah di server. Coba lagi sebentar.',
      action: 'Retry',
      showDetails: false
    },
    intermediate: {
      message: 'Terjadi kesalahan sistem. Coba lagi atau hubungi admin.',
      action: 'Retry',
      showDetails: true
    },
    advanced: {
      message: 'Internal server error. Check logs for stack trace.',
      action: 'Retry',
      showDetails: true
    }
  }
}

interface ErrorWithCode {
  code?: string
  message?: string
}

export function adaptErrorMessage(error: ErrorWithCode, userLevel: UserLevel = 'intermediate'): ErrorMessageConfig {
  const errorCode = error.code || 'UNKNOWN'
  const levelMap = ERROR_MESSAGES[errorCode]
  
  if (!levelMap) {
    return {
      message: error.message || 'Terjadi kesalahan',
      action: 'Retry',
      showDetails: userLevel !== 'beginner'
    }
  }
  
  return levelMap[userLevel] || levelMap.intermediate
}

export default { adaptErrorMessage }
