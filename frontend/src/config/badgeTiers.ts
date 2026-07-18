export const BADGE_TIERS = {
  trial: {
    label: 'Trial',
    color: 'bg-slate-500',
    textColor: 'text-white',
    benefits: ['Coba fitur dasar', '1 job paralel', 'Template standar']
  },
  starter: {
    label: 'Starter',
    color: 'bg-amber-500',
    textColor: 'text-white',
    benefits: ['Antrian normal', 'Template standar', '1 revisi gratis', '1 job paralel']
  },
  pro: {
    label: 'Pro',
    color: 'bg-indigo-600',
    textColor: 'text-white',
    benefits: ['Prioritas tinggi', 'Template premium (sebagian jurnal)', '3 revisi gratis', '2 job paralel', 'Support email prioritas']
  },
  elite: {
    label: 'Elite',
    color: 'badge-elite-gradient',
    textColor: 'text-white',
    benefits: [
      'Prioritas tertinggi',
      'Revisi unlimited',
      '3 job paralel',
      'Semua template jurnal unlocked',
      'Akses humanizer',
      'Kuota image generation lebih besar',
      'Early access fitur beta',
      '+10% token bonus tiap pembelian',
      'Support chat prioritas'
    ]
  }
} as const

export type BadgeKey = keyof typeof BADGE_TIERS
export type BadgeTier = (typeof BADGE_TIERS)[BadgeKey]

// Tier rank: higher = more access
export const TIER_RANK: Record<BadgeKey, number> = { trial: 0, starter: 1, pro: 2, elite: 3 }

// Journal → tier yang dibutuhkan untuk unlock
export const JOURNAL_TIERS: Record<string, BadgeKey> = {
  // Trial (10)
  IEEE: 'trial', ACM: 'trial', Elsevier: 'trial', Springer: 'trial', MDPI: 'trial',
  APA: 'trial', MEV: 'trial', ULTIMACOMP: 'trial', JAT: 'trial', UITM: 'trial',
  // Starter (+9 = 19)
  DJLIT: 'starter', EASR: 'starter', ELCTRICES: 'starter', CCJ: 'starter',
  AMORI: 'starter', CERiMRE: 'starter', ELKOLIND: 'starter', ENERGIUPM: 'starter', 'El-Usrah': 'starter',
  // Pro (+16 = 36)
  ICET: 'pro', ICIMECE: 'pro', ICONIE: 'pro', ICOSEG: 'pro', IJB: 'pro',
  IJECE: 'pro', IJEECS: 'pro', IJIMS: 'pro', IJITEE: 'pro', IJRED: 'pro',
  IJT: 'pro', JAMRIS: 'pro', JCEF: 'pro', JEEMECS: 'pro', JIEB: 'pro', AEJ: 'pro',
  // Elite (+14 = 49 = all)
  JMEM: 'elite', JNTETI: 'elite', JOKI: 'elite', JRC: 'elite', JTMM: 'elite',
  JTRANSIENT: 'elite', JTUNDIP: 'elite', KKCK: 'elite', Murhum: 'elite', Obsesi: 'elite',
  PAUDIA: 'elite', PGPAUDTrunojoyo: 'elite', PST: 'elite', ROTASI: 'elite',
}

// Default tier for journals not explicitly mapped
export const DEFAULT_JOURNAL_TIER: BadgeKey = 'trial'

export function journalTier(journal: string): BadgeKey {
  return JOURNAL_TIERS[journal] || DEFAULT_JOURNAL_TIER
}

export function isJournalUnlocked(_journal: string, _userBadge: BadgeKey | undefined): boolean {
  return true // ponytail: all unlocked for testing — re-enable tier check after template review
}

// Tier badge styling for dropdown
export const TIER_BADGE_STYLE: Record<BadgeKey, string> = {
  trial: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  starter: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  pro: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  elite: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
}

export const TIER_SHORT: Record<BadgeKey, string> = {
  trial: 'T', starter: 'S', pro: 'P', elite: 'E',
}
