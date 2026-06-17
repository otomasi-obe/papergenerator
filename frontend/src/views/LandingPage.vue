<template>
  <div class="min-h-screen bg-gradient-to-br from-navy-900 via-navy-800 to-stone-900 text-cream-50">
    <!-- Navigation -->
    <nav class="flex items-center justify-between px-8 py-5 max-w-7xl mx-auto">
      <div class="flex items-center gap-2.5">
        <img :src="logoWithText" alt="PaperFull" class="h-9 object-contain" />
        <span class="text-xs bg-cream-300/20 text-cream-200 px-2 py-0.5 rounded-full font-medium ml-1">Multi-Journal</span>
      </div>
      <router-link to="/login"
        class="flex items-center gap-2 px-5 py-2.5 bg-cream-50 text-navy-800 rounded-full font-medium hover:bg-cream-100 transition-colors shadow-lg text-sm active:scale-95 transition-transform"
      >
        Sign In
      </router-link>
    </nav>

    <main>
    <!-- Hero -->
    <section class="relative max-w-6xl mx-auto px-8 pt-16 pb-20">
      <div class="grid lg:grid-cols-2 gap-12 items-center">
        <div class="text-center lg:text-left">
          <div class="inline-flex items-center gap-2 text-cream-200 text-sm font-medium bg-cream-300/10 border border-cream-300/30 rounded-full px-4 py-1.5 mb-6">
            <span class="w-1.5 h-1.5 bg-cream-300 rounded-full animate-pulse"></span>
            AI-Powered Academic Paper Writing
          </div>
          <h1 class="text-5xl md:text-6xl font-extrabold mb-6 leading-tight font-serif">
            Generate Papers for
            <span class="bg-gradient-to-r from-cream-200 to-cream-400 bg-clip-text text-transparent">Journal</span>
            <br />or Conference
          </h1>
          <p class="text-lg text-cream-200/70 max-w-xl mx-auto lg:mx-0 mb-10 leading-relaxed">
            Generate publication-ready papers for IEEE, international journals, SINTA-indexed journals, and conferences. Auto-format with LaTeX formulas, figures, tables, and references — export to DOCX ready for submission.
          </p>
          <div class="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
            <router-link to="/login"
              class="flex items-center justify-center gap-3 px-8 py-4 bg-cream-50 text-navy-800 rounded-xl font-semibold hover:bg-cream-100 transition-all shadow-2xl text-base active:scale-95 transition-transform"
            >
              Get Started
            </router-link>
            <a href="#features" class="flex items-center justify-center gap-2 px-8 py-4 border border-cream-300/40 rounded-xl text-cream-200 hover:border-cream-200 hover:text-cream-50 transition-colors text-base">
              Learn More →
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

    <!-- Trust Strip -->
    <section class="relative">
      <img :src="trustStrip" alt="" aria-hidden="true"
        class="absolute inset-0 w-full h-full object-cover opacity-25" />
      <div class="absolute inset-0 bg-gradient-to-r from-navy-900/85 via-navy-900/70 to-navy-900/85"></div>
      <div class="relative max-w-6xl mx-auto px-8 py-12">
        <p class="text-center text-cream-200 text-sm uppercase tracking-[0.2em] mb-8">
          Trusted across disciplines · IEEE · SINTA · International Journals · Conferences
        </p>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          <div>
            <div class="text-3xl font-bold text-white">100+</div>
            <div class="text-cream-300 text-sm">Domain topics</div>
          </div>
          <div>
            <div class="text-3xl font-bold text-white">20+</div>
            <div class="text-cream-300 text-sm">Citation styles</div>
          </div>
          <div>
            <div class="text-3xl font-bold text-white">4000+</div>
            <div class="text-cream-300 text-sm">Words per paper</div>
          </div>
          <div>
            <div class="text-3xl font-bold text-white">DOCX</div>
            <div class="text-cream-300 text-sm">Submission-ready</div>
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
        <div v-for="feature in features" :key="feature.title"
          class="bg-white/5 border border-white/10 rounded-2xl p-6 hover:bg-white/8 transition-colors">
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
          class="inline-flex items-center gap-3 px-8 py-4 bg-navy-500 hover:bg-navy-400 text-white rounded-xl font-semibold transition-colors shadow-lg active:scale-95 transition-transform"
        >
          Start Writing for Free
        </router-link>
      </div>
    </section>

    </main>

    <button
      v-if="showBackToTop"
      type="button"
      class="fixed bottom-6 right-6 z-50 rounded-full px-4 py-3 text-white shadow-2xl transition-colors hover:brightness-110 focus:outline-none focus:ring-4 focus:ring-[#238f7f]/40 active:scale-95 transition-transform"
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
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
const logoWithText = '/assets/logo-with-text.png'
const landingHero = '/assets/landing-page.jpg'
const featureIllustration = '/assets/feature-illustration.jpg'
const trustStrip = '/assets/trust-strip-bg.jpg'

const scrollY = ref(0)
const showBackToTop = computed(() => scrollY.value > 520)

function updateScrollY() {
  scrollY.value = window.scrollY
}

function backToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(() => {
  updateScrollY()
  window.addEventListener('scroll', updateScrollY, { passive: true })
})

onUnmounted(() => {
  window.removeEventListener('scroll', updateScrollY)
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
