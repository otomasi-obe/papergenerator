import { computed } from 'vue'
import { useLanguageStore } from '../stores/language'

const translations = {
  id: {
    nav: {
      info: 'Informasi',
      signIn: 'Masuk',
      getStarted: 'Mulai Sekarang',
      learnMore: 'Pelajari Lebih Lanjut'
    },
    hero: {
      badge: 'Platform Penulisan Paper Akademik dengan AI',
      title1: 'Generate Paper untuk',
      title2: 'Jurnal',
      title3: 'atau Konferensi',
      subtitle: 'Generate paper siap publikasi untuk IEEE, jurnal internasional, jurnal terindeks SINTA, dan konferensi. Format otomatis dengan rumus LaTeX, gambar, tabel, dan referensi — ekspor ke DOCX siap submit.'
    },
    dropdown: {
      terms: 'Syarat & Ketentuan',
      termsDesc: 'Aturan penggunaan layanan',
      refund: 'Kebijakan Refund',
      refundDesc: 'Prosedur pengembalian dana',
      faq: 'FAQ',
      faqDesc: 'Pertanyaan umum',
      contact: 'Kontak',
      contactDesc: 'Hubungi kami'
    }
  },
  en: {
    nav: {
      info: 'Information',
      signIn: 'Sign In',
      getStarted: 'Get Started',
      learnMore: 'Learn More'
    },
    hero: {
      badge: 'AI-Powered Academic Paper Writing',
      title1: 'Generate Papers for',
      title2: 'Journal',
      title3: 'or Conference',
      subtitle: 'Generate publication-ready papers for IEEE, international journals, SINTA-indexed journals, and conferences. Auto-format with LaTeX formulas, figures, tables, and references — export to DOCX ready for submission.'
    },
    dropdown: {
      terms: 'Terms & Conditions',
      termsDesc: 'Service usage rules',
      refund: 'Refund Policy',
      refundDesc: 'Fund refund procedure',
      faq: 'FAQ',
      faqDesc: 'Frequently asked questions',
      contact: 'Contact',
      contactDesc: 'Get in touch'
    }
  }
}

export function useI18n() {
  const langStore = useLanguageStore()

  const t = computed(() => {
    return (key: string) => {
      const keys = key.split('.')
      let value: any = translations[langStore.locale]
      
      for (const k of keys) {
        value = value?.[k]
      }
      
      return value || key
    }
  })

  return {
    t: t.value,
    locale: computed(() => langStore.locale),
    setLocale: langStore.setLocale
  }
}
