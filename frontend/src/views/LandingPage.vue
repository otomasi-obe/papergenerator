<template>
 <div class="min-h-screen text-cream-50 animated-gradient-bg">
 <!-- Navigation -->
 <nav class="flex items-center justify-between px-8 py-5 max-w-7xl mx-auto">
   <div class="flex items-center gap-2.5">
     <img :src="logoWithText" alt="PaperFull" class="h-9 object-contain" />
     <span class="text-xs bg-cream-300/20 text-cream-200 px-2 py-0.5 rounded-full font-medium ml-1">Multi-Journal</span>
   </div>
   <div class="flex items-center gap-3">
     <!-- Info Dropdown -->
     <div class="relative" ref="dropdownRef" @mouseenter="handleMouseEnter" @mouseleave="handleMouseLeave">
       <button
         @click="dropdownOpen = !dropdownOpen"
         class="flex items-center gap-1.5 px-4 py-2.5 bg-white/95 hover:bg-amber-50/95 backdrop-blur-sm text-amber-900 border border-amber-300/50 shadow-amber-200/30 hover:shadow-amber-200/50 active:bg-amber-100 rounded-full font-bold transition-all shadow-lg text-sm active:scale-95"
       >
         {{ t('nav.info') }}
         <svg 
           class="w-4 h-4 transition-transform duration-200"
           :class="{ 'rotate-180': dropdownOpen }"
           fill="none" 
           stroke="currentColor" 
           viewBox="0 0 24 24"
         >
           <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
         </svg>
       </button>

       <!-- Dropdown Menu -->
       <transition
         enter-active-class="transition ease-out duration-200"
         enter-from-class="opacity-0 translate-y-1"
         enter-to-class="opacity-100 translate-y-0"
         leave-active-class="transition ease-in duration-150"
         leave-from-class="opacity-100 translate-y-0"
         leave-to-class="opacity-0 translate-y-1"
       >
         <div
           v-if="dropdownOpen"
           class="absolute right-0 mt-1 w-56 bg-white/95 backdrop-blur-sm border border-amber-300/50 rounded-xl shadow-xl overflow-hidden z-50"
         >
           <router-link
             to="/terms"
             class="block px-4 py-3 text-sm text-amber-900 hover:bg-amber-50 transition-colors border-b border-amber-100 last:border-b-0"
             @click="dropdownOpen = false"
           >
             <div class="font-semibold">{{ t('dropdown.terms') }}</div>
             <div class="text-xs text-amber-700 mt-0.5">{{ t('dropdown.termsDesc') }}</div>
           </router-link>
           <router-link
             to="/refund"
             class="block px-4 py-3 text-sm text-amber-900 hover:bg-amber-50 transition-colors border-b border-amber-100 last:border-b-0"
             @click="dropdownOpen = false"
           >
             <div class="font-semibold">{{ t('dropdown.refund') }}</div>
             <div class="text-xs text-amber-700 mt-0.5">{{ t('dropdown.refundDesc') }}</div>
           </router-link>
           <router-link
             to="/faq"
             class="block px-4 py-3 text-sm text-amber-900 hover:bg-amber-50 transition-colors border-b border-amber-100 last:border-b-0"
             @click="dropdownOpen = false"
           >
             <div class="font-semibold">{{ t('dropdown.faq') }}</div>
             <div class="text-xs text-amber-700 mt-0.5">{{ t('dropdown.faqDesc') }}</div>
           </router-link>
           <router-link
             to="/contact"
             class="block px-4 py-3 text-sm text-amber-900 hover:bg-amber-50 transition-colors border-b border-amber-100 last:border-b-0"
             @click="dropdownOpen = false"
           >
             <div class="font-semibold">{{ t('dropdown.contact') }}</div>
             <div class="text-xs text-amber-700 mt-0.5">{{ t('dropdown.contactDesc') }}</div>
           </router-link>
         </div>
       </transition>
     </div>

     <!-- Language Toggle -->
     <button
       @click="toggleLanguage"
       class="flex items-center gap-1.5 px-4 py-2.5 bg-white/95 hover:bg-amber-50/95 backdrop-blur-sm text-amber-900 border border-amber-300/50 shadow-amber-200/30 hover:shadow-amber-200/50 active:bg-amber-100 rounded-full font-bold transition-all shadow-lg text-sm active:scale-95"
       :title="locale === 'id' ? 'Switch to English' : 'Ganti ke Bahasa Indonesia'"
     >
       {{ locale === 'id' ? '🇮🇩 ID' : '🇬🇧 EN' }}
     </button>

     <!-- Sign In Button -->
     <router-link to="/login"
       class="flex items-center gap-2 px-5 py-2.5 bg-white/95 hover:bg-amber-50/95 backdrop-blur-sm text-amber-900 border border-amber-300/50 shadow-amber-200/30 hover:shadow-amber-200/50 active:bg-amber-100 active:border-amber-400 rounded-full font-bold transition-all shadow-lg text-sm active:scale-95"
     >
       {{ t('nav.signIn') }}
     </router-link>
   </div>
 </nav>

 <main>
 <!-- Hero -->
 <section class="relative max-w-6xl mx-auto px-8 pt-16 pb-20">
 <div class="grid lg:grid-cols-2 gap-12 items-center">
 <div class="text-center lg:text-left">
   <div class="hero-badge">
     <span class="w-1.5 h-1.5 bg-amber-400 rounded-full animate-pulse"></span>
     {{ t('hero.badge') }}
   </div>
   <h1 class="text-5xl md:text-6xl font-extrabold mb-6 leading-tight font-serif">
     <span v-html="typedHtml"></span><span
       class="inline-block w-[3px] h-[0.85em] bg-cream-200 ml-0.5 align-middle"
       style="animation: cursor-blink 500ms step-end infinite"
     ></span>
   </h1>
   <p class="text-lg text-cream-200/70 max-w-xl mx-auto lg:mx-0 mb-10 leading-relaxed">
     {{ t('hero.subtitle') }}
   </p>
   <div class="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
     <router-link to="/login"
       class="flex items-center justify-center gap-3 px-8 py-4 bg-white hover:bg-amber-50 text-amber-900 border border-amber-300 shadow-amber-200/50 hover:border-amber-400 active:bg-amber-100 active:border-amber-500 rounded-xl font-bold transition-all shadow-2xl text-base active:scale-95"
     >
       {{ t('nav.getStarted') }}
     </router-link>
     <a href="#features" class="flex items-center justify-center gap-2 px-8 py-4 border border-cream-300/40 rounded-xl text-cream-200 hover:border-cream-200 hover:text-cream-50 transition text-base">
       {{ t('nav.learnMore') }} →
     </a>
   </div>
 </div>
 <div class="relative">
 <div class="absolute -inset-6 bg-gradient-to-r from-cream-300/20 via-cream-400/10 to-navy-500/20 blur-3xl"></div>
 <img :src="landingHero" alt="PaperFull editor preview"
 class="relative w-full rounded-2xl ring-1 ring-cream-200/10 shadow-[0_30px_60px_-15px_rgba(0,0,0,0.6)]" />
 </div>
 </div>
 </section>

 <!-- Trust Strip → Counters + Marquee -->
 <section class="relative count-section">
 <img :src="trustStrip" alt="" aria-hidden="true"
 class="absolute inset-0 w-full h-full object-cover opacity-25" />
 <div class="absolute inset-0 bg-gradient-to-r from-navy-900/85 via-navy-900/70 to-navy-900/85"></div>
 <div class="relative max-w-6xl mx-auto px-8 py-12">
 <div class="grid grid-cols-2 md:grid-cols-4 gap-6 text-center mb-12">
 <div>
 <div class="text-3xl font-bold text-white counter-value" data-target="100" data-suffix="+">0</div>
 <div class="text-cream-300 text-sm">Domain topics</div>
 </div>
 <div>
 <div class="text-3xl font-bold text-white counter-value" data-target="20" data-suffix="+">0</div>
 <div class="text-cream-300 text-sm">Citation styles</div>
 </div>
 <div>
 <div class="text-3xl font-bold text-white counter-value" data-target="4000" data-suffix="+">0</div>
 <div class="text-cream-300 text-sm">Words per paper</div>
 </div>
 <div>
 <div class="text-3xl font-bold text-white">DOCX</div>
 <div class="text-cream-300 text-sm">Submission-ready</div>
 </div>
 </div>
 <div class="marquee-wrapper">
   <div class="marquee-track">
     <span class="marquee-item"><span class="dot"></span>IEEE Journals</span>
     <span class="marquee-item"><span class="dot amber"></span>SINTA 1–6</span>
     <span class="marquee-item"><span class="dot green"></span>Scopus</span>
     <span class="marquee-item"><span class="dot"></span>Web of Science</span>
     <span class="marquee-item"><span class="dot amber"></span>International Journals</span>
     <span class="marquee-item"><span class="dot green"></span>APA · Vancouver · IEEE</span>
     <span class="marquee-item"><span class="dot"></span>Conferences</span>
     <span class="marquee-item"><span class="dot"></span>IEEE Journals</span>
     <span class="marquee-item"><span class="dot amber"></span>SINTA 1–6</span>
     <span class="marquee-item"><span class="dot green"></span>Scopus</span>
     <span class="marquee-item"><span class="dot"></span>Web of Science</span>
     <span class="marquee-item"><span class="dot amber"></span>International Journals</span>
     <span class="marquee-item"><span class="dot green"></span>APA · Vancouver · IEEE</span>
     <span class="marquee-item"><span class="dot"></span>Conferences</span>
   </div>
 </div>
 </div>
 </section>

 <!-- Feature Cards -->
 <section id="features" class="max-w-6xl mx-auto px-8 py-24">
 <div class="grid lg:grid-cols-2 gap-12 items-center mb-16">
 <div>
 <h2 class="text-3xl font-bold mb-4 text-white font-serif">Everything you need to write great papers</h2>
 <p class="text-cream-300 leading-relaxed">
 From the first draft to the final DOCX, PaperFull handles the structural work so you can focus on the ideas. Domain-aware prompts, anti-detection writing, full citation hygiene, and a chat assistant that reads your reference PDFs.
 </p>
 </div>
 <img :src="featureIllustration" alt="PaperFull feature illustration"
 class="w-full rounded-2xl ring-1 ring-white/10 shadow-2xl" />
 </div>
 <div class="grid md:grid-cols-3 gap-6">
 <div v-for="(feature, index) in features" :key="feature.title"
 class="feat-card bg-white/5 border border-white/10 rounded-2xl p-6" :style="{ '--stagger': index + 'ms' }">
 <div class="text-3xl mb-4" aria-hidden="true">{{ feature.icon }}</div>
 <h3 class="text-lg font-semibold mb-2">{{ feature.title }}</h3>
 <p class="text-cream-300/80 text-sm leading-relaxed">{{ feature.description }}</p>
 </div>
 </div>
 </section>

 <!-- Publication Types Section -->
 <section class="max-w-6xl mx-auto px-8 pb-24">
 <h2 class="text-3xl font-bold text-center mb-4 text-white font-serif">Supported Publication Types</h2>
 <p class="text-cream-200/70 text-center mb-12 max-w-2xl mx-auto">Generate papers for various publication venues with proper formatting and citation styles</p>
 <div class="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">📚</div>
 <h3 class="font-semibold mb-1 text-white">IEEE Journals</h3>
 <p class="text-cream-200/80 text-xs">TIE, TPEL, RA-L, TMECH, IoT-J, Access, and more. IEEE citation format and conference standards.</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">🌐</div>
 <h3 class="font-semibold mb-1 text-white">International Journals</h3>
 <p class="text-cream-200/80 text-xs">Scopus, Web of Science indexed journals. APA, Vancouver, and custom citation formats supported.</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">🏆</div>
 <h3 class="font-semibold mb-1 text-white">SINTA Journals</h3>
 <p class="text-cream-200/80 text-xs">Indonesian SINTA 1-6 indexed journals. Proper formatting for national publication requirements.</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">🎤</div>
 <h3 class="font-semibold mb-1 text-white">Conferences</h3>
 <p class="text-cream-200/80 text-xs">International and local conferences. ICRA, IROS, IECON, and other technical conferences.</p>
 </div>
 </div>
 </section>

 <!-- Domains Section -->
 <section class="max-w-6xl mx-auto px-8 pb-24">
 <h2 class="text-3xl font-bold text-center mb-4 text-white font-serif">Specialized Domains</h2>
 <p class="text-cream-200/70 text-center mb-12 max-w-2xl mx-auto">Our AI is trained on 100+ domain-specific topics for accurate technical content generation</p>
 <div class="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">⚙️</div>
 <h3 class="font-semibold mb-1 text-white">Engineering</h3>
 <p class="text-cream-200/80 text-xs">Mechanical, Electrical, Civil, Chemical, Aerospace, Mechatronics, Robotics, Power Electronics</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">💻</div>
 <h3 class="font-semibold mb-1 text-white">Computer Science</h3>
 <p class="text-cream-200/80 text-xs">AI, Machine Learning, Data Science, Cybersecurity, Cloud Computing, IoT, Blockchain, Networks</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">🏥</div>
 <h3 class="font-semibold mb-1 text-white">Medical & Health</h3>
 <p class="text-cream-200/80 text-xs">Medicine, Nursing, Cardiology, Oncology, Biomedical Engineering, Public Health, Pharmacology</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">🔬</div>
 <h3 class="font-semibold mb-1 text-white">Natural Sciences</h3>
 <p class="text-cream-200/80 text-xs">Biology, Chemistry, Physics, Mathematics, Environmental Science, Geology, Genetics</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">💰</div>
 <h3 class="font-semibold mb-1 text-white">Business & Finance</h3>
 <p class="text-cream-200/80 text-xs">Accounting, Finance, Economics, Management, Marketing, Entrepreneurship, Operations</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">🧭</div>
 <h3 class="font-semibold mb-1 text-white">Social Sciences</h3>
 <p class="text-cream-200/80 text-xs">Psychology, Sociology, Anthropology, Political Science, Education, Communication, Law</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">🌾</div>
 <h3 class="font-semibold mb-1 text-white">Agriculture & Environment</h3>
 <p class="text-cream-200/80 text-xs">Agriculture, Agronomy, Horticulture, Environmental Engineering, Climate Science, Food Science</p>
 </div>
 <div class="bg-white/5 border border-white/10 rounded-xl p-5">
 <div class="text-2xl mb-2" aria-hidden="true">🎨</div>
 <h3 class="font-semibold mb-1 text-white">Arts & Humanities</h3>
 <p class="text-cream-200/80 text-xs">Literature, Philosophy, History, Linguistics, Architecture, Performing Arts, Religious Studies</p>
 </div>
 </div>
 </section>

 <!-- CTA -->
 <section class="max-w-3xl mx-auto px-8 pb-24 text-center">
 <div class="bg-gradient-to-r from-navy-500/20 to-navy-400/20 border border-navy-400/30 rounded-3xl p-12">
 <h2 class="text-3xl font-bold mb-4 font-serif">Ready to write your paper?</h2>
 <p class="text-cream-200/70 mb-8">Join researchers using AI to accelerate their academic writing.</p>
 <router-link to="/login"
 class="inline-flex items-center gap-3 px-8 py-4 bg-navy-500 hover:bg-navy-400 text-white rounded-xl font-semibold transition shadow-lg active:scale-95"
 >
 Start Writing for Free
 </router-link>
 </div>
 </section>

 </main>

 <button
 v-if="showBackToTop"
 type="button"
 class="fixed bottom-6 right-6 z-50 rounded-full px-4 py-3 text-white shadow-2xl transition hover:brightness-110 focus:outline-none focus:ring-4 focus:ring-[#238f7f]/40 active:scale-95"
 style="background: var(--accent)"
 aria-label="Back to top"
 @click="backToTop"
 >
 ↑
 </button>

 <!-- Footer -->
 <footer class="border-t border-white/10 py-8 text-center text-ink-200 text-sm">
 <p>© 2026 PaperFull · Multi-Journal Academic Paper AI Tool</p>
 </footer>
 <PatchNotification />
 </div>
 </template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from '../composables/useI18n'
import PatchNotification from '../components/PatchNotification.vue'

const { t, locale, setLocale } = useI18n()

const logoWithText = '/assets/logo-with-text.png'
const landingHero = '/assets/landing-page.jpg'
const featureIllustration = '/assets/feature-illustration.jpg'
const trustStrip = '/assets/trust-strip-bg.jpg'

const scrollY = ref(0)
const showBackToTop = computed(() => scrollY.value > 520)

// Dropdown state
const dropdownOpen = ref(false)
const dropdownRef = ref(null)

// Typewriter animation for hero heading
const typedHtml = ref('')
let typeTimer = null

function buildFullHtml() {
  const accent = `<span class="bg-gradient-to-r from-cream-200 to-cream-400 bg-clip-text text-transparent">${t('hero.title2')}</span>`
  return `${t('hero.title1')} ${accent}<br />${t('hero.title3')}`
}

function startTyping() {
  if (typeTimer) clearInterval(typeTimer)
  // Plain text sequence to type; render HTML up to the current plain-text index.
  const part1 = t('hero.title1')
  const part2 = t('hero.title2')
  const part3 = t('hero.title3')
  const plain = `${part1} ${part2}\n${part3}`
  const accent = `<span class="bg-gradient-to-r from-cream-200 to-cream-400 bg-clip-text text-transparent">${part2}</span>`
  let i = 0
  typedHtml.value = ''
  typeTimer = setInterval(() => {
    i++
    if (i > plain.length) {
      clearInterval(typeTimer)
      typeTimer = null
      return
    }
    const slice = plain.slice(0, i)
    // Replace part2 with accent span only when fully typed
    let html = slice.replace('\n', '<br />')
    if (slice.length >= (part1.length + 1 + part2.length)) {
      html = (part1 + ' ' + accent + slice.slice(part1.length + 1 + part2.length).replace('\n', '<br />'))
    }
    typedHtml.value = html
  }, 60)
}

function updateScrollY() {
  scrollY.value = window.scrollY
}

function backToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

let hoverTimer = null

function handleMouseEnter() {
  clearTimeout(hoverTimer)
  dropdownOpen.value = true
}

function handleMouseLeave() {
  hoverTimer = setTimeout(() => {
    dropdownOpen.value = false
  }, 150)
}

// Close dropdown when clicking outside
function handleClickOutside(event) {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target)) {
    dropdownOpen.value = false
  }
}

function toggleLanguage() {
  setLocale(locale.value === 'id' ? 'en' : 'id')
}

// Restart typewriter when language changes
watch(locale, () => startTyping())

onMounted(() => {
  updateScrollY()
  window.addEventListener('scroll', updateScrollY, { passive: true })
  document.addEventListener('click', handleClickOutside)
  startTyping()
 // Animated stat counters
 function animateCounter(el, target, suffix = '') {
   const duration = 1800
   const start = performance.now()
   const update = (now) => {
     const progress = Math.min((now - start) / duration, 1)
     const ease = 1 - Math.pow(1 - progress, 3)
     el.textContent = Math.round(ease * target).toLocaleString() + (progress > 0.5 ? suffix : '')
     if (progress < 1) requestAnimationFrame(update)
     else el.textContent = target.toLocaleString() + suffix
   }
   requestAnimationFrame(update)
 }

 const counterObserver = new IntersectionObserver((entries) => {
   entries.forEach(entry => {
     if (entry.isIntersecting) {
       const counters = entry.target.querySelectorAll('.counter-value')
       counters.forEach(el => {
         const target = parseInt(el.dataset.target)
         const suffix = el.dataset.suffix || ''
         if (!isNaN(target)) animateCounter(el, target, suffix)
       })
       counterObserver.unobserve(entry.target)
     }
   })
 }, { threshold: 0.3 })

 const countSection = document.querySelector('.count-section')
 if (countSection) counterObserver.observe(countSection)

 // Staggered card reveal
 const cardObserver = new IntersectionObserver((entries) => {
   entries.forEach(entry => {
     if (entry.isIntersecting) {
       const cards = entry.target.querySelectorAll('.feat-card')
       cards.forEach((card, i) => {
         setTimeout(() => card.classList.add('visible'), i * 80)
       })
       cardObserver.unobserve(entry.target)
     }
   })
 }, { threshold: 0.15 })

 const cardGrid = document.querySelector('#features .grid.md\\:grid-cols-3')
 if (cardGrid) cardObserver.observe(cardGrid)
 })

onUnmounted(() => {
  window.removeEventListener('scroll', updateScrollY)
  document.removeEventListener('click', handleClickOutside)
  if (typeTimer) clearInterval(typeTimer)
})

const features = [
 {
 icon: '⚡',
 title: 'AI Paper Generation',
 description: 'Generate complete papers with 4000+ words from a single prompt. AI writes all sections with academic writing style, proper citations, and anti-AI detection strategies.',
 },
 {
 icon: '🌍',
 title: 'Multi-Journal Support',
 description: 'Support for IEEE, international journals, SINTA-indexed journals, and conferences. Auto-adapt formatting to match specific journal or conference requirements.',
 },
 {
 icon: '🧮',
 title: 'LaTeX Formula Generation',
 description: 'Auto-generate mathematical formulas with DOCX-compatible LaTeX syntax. Supports domain-specific equations for control theory, kinematics, machine learning, and power electronics.',
 },
 {
 icon: '🖼️',
 title: 'AI Figure Generation',
 description: 'Generate detailed technical figures with AI prompts. Create block diagrams, circuit schematics, charts, heatmaps, and experimental setup illustrations automatically.',
 },
 {
 icon: '📊',
 title: 'Table & Reference Management',
 description: 'Auto-generate formatted tables with realistic data. Create 20+ references in various formats (IEEE, APA, Vancouver). All data internally consistent across figures, tables, and text.',
 },
 {
 icon: '🎯',
 title: 'Multi-Domain Support',
 description: 'Specialized for robotics, mechatronics, AI/ML, PLC automation, power electronics, embedded systems, and IoT. Domain-specific equations, figures, and terminology.',
 },
 {
 icon: '🏆',
 title: 'SINTA Journal Support',
 description: 'Optimized for Indonesian SINTA-indexed journals with proper formatting and citation styles. Support for SINTA 1-6 indexed journals across various disciplines.',
 },
 {
 icon: '🎤',
 title: 'Conference Paper Support',
 description: 'Generate conference papers with proper formatting for international and local conferences. Abstract, paper length, and presentation-ready content.',
 },
 {
 icon: '🗂️',
 title: 'Paper Management',
 description: 'Organize all your papers in one place. Create, edit, and delete papers. Each paper has its own figures, images, and complete content.',
 },
 {
 icon: '📐',
 title: 'Format Export',
 description: 'Auto-format papers according to journal or conference standards. Export directly to DOCX ready for submission with proper formatting, equations, and figures.',
 },
 {
 icon: '🔒',
 title: 'Secure & Private',
 description: 'Login with Google. Each user only sees their own papers. Your research stays private and secure with user-specific data isolation.',
 },
 {
 icon: '📈',
 title: 'Admin Dashboard',
 description: 'Track API token usage per user. View all papers. Monitor traffic and token consumption with detailed analytics for system management.',
 },
]
</script>

<style scoped>
</style>

<style>
@keyframes cursor-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

/* 1. Animated gradient background */
.animated-gradient-bg {
  background: linear-gradient(135deg, #060f1e, #0a1628, #0d1f3c, #060f1e);
  background-size: 400% 400%;
  animation: gradShift 14s ease infinite;
}

@keyframes gradShift {
  0%   { background-position: 0% 50%; }
  50%  { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

/* 2. Hero badge shimmer */
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border-radius: 20px;
  background: rgba(232, 164, 74, 0.1);
  border: 1px solid rgba(232, 164, 74, 0.35);
  color: #fcd34d;
  font-size: 13px;
  font-weight: 500;
  position: relative;
  overflow: hidden;
}

.hero-badge::after {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 60%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.18),
    transparent
  );
  animation: shimmer 5s ease-in-out infinite;
}

@keyframes shimmer {
  0%   { left: -100%; }
  60%  { left: 150%; }
  100% { left: 150%; }
}

/* 3. Feature card stagger + hover */
.feat-card {
  opacity: 0;
  transform: translateY(24px);
  transition: opacity 0.45s ease, transform 0.45s ease, border-color 0.2s, scale 0.2s;
}

.feat-card.visible {
  opacity: 1;
  transform: translateY(0);
  transition-delay: calc(var(--stagger, 0) * 1ms);
}

.feat-card:hover {
  transform: scale(1.025);
  border-color: rgba(192, 219, 255, 0.25);
  background: rgba(255, 255, 255, 0.08);
}

/* 4. Marquee — smooth seamless loop */
.marquee-wrapper {
  overflow: hidden;
  -webkit-mask-image: linear-gradient(to right, transparent, black 10%, black 90%, transparent);
  mask-image: linear-gradient(to right, transparent, black 10%, black 90%, transparent);
}

.marquee-track {
  display: flex;
  gap: 0;
  width: max-content;
  animation: marquee 25s linear infinite;
}

.marquee-wrapper:hover .marquee-track {
  animation-play-state: paused;
}

@keyframes marquee {
  from { transform: translate3d(0, 0, 0); }
  to   { transform: translate3d(-50%, 0, 0); }
}

.marquee-item {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  white-space: nowrap;
  color: rgba(253, 251, 240, 0.7);
  font-size: 0.8rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-right: 3rem;
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 9999px;
  background: rgba(253, 251, 240, 0.5);
  flex-shrink: 0;
}

.dot.amber { background: #fbbf24; }
.dot.green { background: #34d399; }

/* 5. Accessibility */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
