<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <PublicHeader />

    <main class="max-w-4xl mx-auto px-6 py-12">
      <div class="mb-6">
        <router-link to="/" class="inline-flex items-center gap-1.5 text-sm text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 font-medium transition-colors">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 19l-7-7 7-7"/></svg>
          Kembali ke Beranda
        </router-link>
      </div>
      <article class="prose prose-lg dark:prose-invert max-w-none">
        <h1 class="text-3xl font-bold text-ink-900 dark:text-ink-50 mb-2">FAQ — Paperfull</h1>
        <p class="text-sm text-ink-500 dark:text-ink-400 mb-8">Pertanyaan yang sering diajukan</p>

        <div class="space-y-3 mt-6">
          <div
            v-for="(faq, index) in faqs"
            :key="index"
            class="faq-item rounded-xl overflow-hidden transition-all duration-300"
            :class="[
              openedIndex === index
                ? 'faq-item--open bg-white dark:bg-ash-800 shadow-lg shadow-amber-500/5 border border-amber-300/40 dark:border-amber-600/20'
                : 'bg-white/60 dark:bg-ash-800/40 border border-ink-200 dark:border-ink-600 hover:border-ink-300 dark:hover:border-ink-500',
              itemRevealed[index] ? 'faq-revealed' : 'faq-hidden'
            ]"
            :style="{ '--reveal-delay': index * 60 + 'ms' }"
          >
            <button
              @click="toggle(index)"
              @touchstart.passive="onTouchStart($event, index)"
              @touchmove.passive="onTouchMove($event, index)"
              @touchend="onTouchEnd($event, index)"
              class="w-full text-left px-6 py-4 flex justify-between items-center transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 rounded-xl"
              :class="openedIndex === index ? 'text-amber-900 dark:text-amber-100' : 'text-ink-900 dark:text-ink-50 hover:bg-ink-50 dark:hover:bg-ash-700/50'"
              :aria-expanded="openedIndex === index"
              :aria-controls="'faq-content-' + index"
            >
              <span class="font-semibold pr-4">
                <span class="text-amber-500 dark:text-amber-400 mr-1.5">{{ index + 1 }}.</span>
                {{ faq.question }}
              </span>
              <span class="faq-chevron ml-4 flex-shrink-0" :class="{ 'faq-chevron--open': openedIndex === index }">
                <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </span>
            </button>

            <div
              :id="'faq-content-' + index"
              class="faq-content-wrapper"
              :class="{ 'faq-content--open': openedIndex === index }"
            >
              <div class="faq-content-inner px-6 pb-4 pt-1">
                <div class="border-t border-ink-200/60 dark:border-ink-600/40 pt-4">
                  <p class="text-ink-700 dark:text-ink-200 leading-relaxed text-[15px]">
                    {{ faq.answer }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="mt-12 p-6 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
          <p class="text-ink-700 dark:text-ink-200">
            Tidak menemukan jawaban yang kamu cari?
            <router-link to="/contact" class="font-semibold text-amber-600 dark:text-amber-400 hover:underline">
              Hubungi tim support kami
            </router-link>
          </p>
        </div>
      </article>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import PublicHeader from '../components/PublicHeader.vue'

const openedIndex = ref<number | null>(null)
const itemRevealed = ref<boolean[]>([])

const faqs = [
  {
    question: 'Apa itu Paperfull?',
    answer:
      'Paperfull adalah platform berbasis AI yang membantu kamu generate paper/dokumen akademik dalam format .docx, dengan pilihan template jurnal yang fleksibel sesuai kebutuhan kamu.',
  },
  {
    question: 'Apakah hasil generate dari Paperfull bisa langsung dipakai untuk submit jurnal?',
    answer:
      'Hasil generate adalah draf bantuan berbasis AI. Kami sangat menyarankan kamu memeriksa ulang isi, referensi, dan format sebelum digunakan untuk keperluan resmi (submission jurnal, skripsi, tesis, dll).',
  },
  {
    question: 'Apakah Paperfull menjamin hasil bebas plagiarisme?',
    answer:
      'Tidak. Paperfull tidak menjamin keaslian 100% dari konten yang dihasilkan AI. Pengguna bertanggung jawab penuh untuk memverifikasi orisinalitas sebelum digunakan.',
  },
  {
    question: 'Bagaimana cara pembayaran di Paperfull?',
    answer:
      'Pembayaran diproses melalui iPaymu, mendukung berbagai metode seperti transfer bank, e-wallet, QRIS, dan kartu kredit/debit.',
  },
  {
    question: 'Apakah saya bisa mendapatkan refund?',
    answer:
      'Bisa, sesuai dengan ketentuan yang tercantum di halaman Kebijakan Refund. Silakan cek halaman tersebut untuk detail prosedur dan syaratnya.',
  },
  {
    question: 'Template jurnal apa saja yang didukung?',
    answer:
      'Paperfull mendukung berbagai format template jurnal umum. Jika template yang kamu butuhkan belum tersedia, kamu bisa menghubungi tim support kami melalui halaman Kontak.',
  },
  {
    question: 'Bagaimana cara menghubungi tim Paperfull jika ada kendala?',
    answer:
      'Kamu bisa menghubungi kami melalui email, nomor telepon, atau alamat yang tercantum di halaman Kontak.',
  },
  {
    question: 'Apakah data dan dokumen saya aman?',
    answer:
      'Kami berupaya menjaga keamanan data pengguna. Dokumen dan informasi pribadi tidak akan dibagikan ke pihak ketiga tanpa izin, kecuali diwajibkan oleh hukum.',
  },
  {
    question: 'Apakah Paperfull berbayar?',
    answer:
      'Paperfull menyediakan layanan berbayar untuk fitur-fitur tertentu. Detail harga dapat dilihat langsung di halaman layanan/pricing kami.',
  },
]

function toggle(index: number) {
  openedIndex.value = openedIndex.value === index ? null : index
}

// Staggered reveal on mount
onMounted(async () => {
  await nextTick()
  itemRevealed.value = faqs.map(() => false)
  // Use IntersectionObserver for viewport reveal
  const items = document.querySelectorAll('.faq-item')
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const idx = Array.from(items).indexOf(entry.target)
          if (idx >= 0) {
            setTimeout(() => {
              itemRevealed.value[idx] = true
            }, idx * 60)
          }
          observer.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.1 }
  )
  items.forEach((item) => observer.observe(item))
})

// Mobile swipe gesture
let touchStartX = 0
let touchStartY = 0
let swipeIndex: number | null = null

function onTouchStart(e: TouchEvent, index: number) {
  touchStartX = e.touches[0].clientX
  touchStartY = e.touches[0].clientY
  swipeIndex = index
}

function onTouchMove(e: TouchEvent, _index: number) {
  // Prevent vertical scroll if swiping horizontally
  const dx = Math.abs(e.touches[0].clientX - touchStartX)
  const dy = Math.abs(e.touches[0].clientY - touchStartY)
  if (dx > dy && dx > 10) {
    e.preventDefault()
  }
}

function onTouchEnd(e: TouchEvent, _index: number) {
  if (swipeIndex !== _index) return
  const dx = e.changedTouches[0].clientX - touchStartX
  const threshold = 50

  if (dx < -threshold && openedIndex.value === _index) {
    // Swipe left → close
    openedIndex.value = null
  } else if (dx > threshold && openedIndex.value !== _index) {
    // Swipe right → open
    openedIndex.value = _index
  }
  swipeIndex = null
}
</script>

<style scoped>
/* Staggered reveal */
.faq-hidden {
  opacity: 0;
  transform: translateY(16px);
}

.faq-revealed {
  animation: faqReveal 0.5s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  animation-delay: var(--reveal-delay, 0ms);
}

@keyframes faqReveal {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Chevron rotation with spring feel */
.faq-chevron {
  transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  color: inherit;
}

.faq-chevron--open {
  transform: rotate(180deg);
}

/* Expand/collapse with height animation */
.faq-content-wrapper {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.35s cubic-bezier(0.34, 1.2, 0.64, 1),
              opacity 0.25s ease;
  opacity: 0;
}

.faq-content--open {
  grid-template-rows: 1fr;
  opacity: 1;
}

.faq-content-inner {
  overflow: hidden;
}

/* Open item glow pulse */
.faq-item--open {
  animation: openPulse 0.6s ease-out;
}

@keyframes openPulse {
  0% {
    box-shadow: 0 0 0 0 rgba(251, 191, 36, 0.3);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(251, 191, 36, 0.08);
  }
  100% {
    box-shadow: 0 8px 24px -4px rgba(251, 191, 36, 0.05);
  }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .faq-revealed {
    animation: none;
    opacity: 1;
    transform: none;
  }
  .faq-chevron {
    transition: none;
  }
  .faq-content-wrapper {
    transition: none;
  }
  .faq-item--open {
    animation: none;
  }
}
</style>
