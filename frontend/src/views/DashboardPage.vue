<template>
 <div class="min-h-screen bg-transparent dark:bg-ash-850 transition">
 <AppHeader />

 <main class="px-4 lg:px-8 py-8 max-w-7xl mx-auto">
   <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-4 mb-8">
      <div>
        <h1 class="text-2xl font-bold font-serif text-ink-900 dark:text-ink-50">My Papers</h1>
        <p class="text-ink-700 dark:text-[#7eb8e0] text-sm mt-1">
          {{ filteredPapers.length }} paper{{ filteredPapers.length === 1 ? '' : 's' }}
          <span v-if="searchQuery && filteredPapers.length !== papers.length" class="text-ink-500 dark:text-ink-400"> of {{ papers.length }}</span>
          <span v-if="lastUpdated" class="text-ink-500 dark:text-ink-400"> · Last updated {{ lastUpdated }}</span>
        </p>
      </div>
     <router-link to="/editor"
         class="flex items-center gap-2 px-5 py-2.5 min-h-[44px] bg-gradient-to-r from-cream-100 via-cream-200 to-cream-100 hover:from-cream-200 hover:via-cream-300 hover:to-cream-200 text-ink-900 dark:text-white dark:from-[#1a4470] dark:via-[#2563a8] dark:to-[#1a4470] dark:hover:from-[#1e4d80] dark:hover:via-[#2d6fb5] dark:hover:to-[#1e4d80] rounded-xl font-medium transition shadow-sm active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"
         >
           + New Paper
         </router-link>
   </div>

   <!-- Search + Sort -->
   <div v-if="papers.length > 3" class="flex flex-wrap items-center gap-3 mb-4">
     <input
       v-model="searchQuery"
       type="search"
       placeholder="Search papers..."
       class="flex-1 min-w-[200px] max-w-md px-4 py-2.5 min-h-[44px] rounded-xl border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 placeholder-ink-400 dark:placeholder-ink-500 text-sm transition focus:outline-none focus:ring-2 focus:ring-[#238f7f] focus:border-transparent"
     />
     <select
       v-model="sortBy"
       class="px-3 py-2.5 min-h-[44px] rounded-xl border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 text-sm transition focus:outline-none focus:ring-2 focus:ring-[#238f7f] focus:border-transparent"
     >
       <option value="updated">Last updated</option>
       <option value="created">Newest first</option>
       <option value="title">Title A–Z</option>
     </select>
   </div>

   <section class="flex-1 min-w-0">
   <StateView :loading="loading" :error="errorMsg" :is-empty="papers.length === 0" :on-retry="loadPapers">
   <template #loading>
   <div class="text-center py-20 text-ink-600 dark:text-[#7eb8e0]">
     <div class="text-3xl mb-3 animate-spin" aria-hidden="true">⚙️</div>
     Loading your papers...
   </div>
   </template>
   <template #empty>
    <div class="text-center py-20">
      <div class="text-6xl mb-4 animate-[float_3s_ease-in-out_infinite]" aria-hidden="true">📄</div>
      <h2 class="text-xl font-semibold text-ink-900 dark:text-ink-50 mb-2">No papers yet</h2>
      <p class="text-ink-600 dark:text-[#7eb8e0] mb-8 max-w-sm mx-auto">Start writing your first academic paper with AI-powered generation, citation management, and more.</p>
      <router-link to="/editor" class="px-8 py-3.5 min-h-[44px] inline-flex items-center gap-2 bg-gradient-to-r from-navy-600 via-navy-500 to-navy-600 hover:from-navy-500 hover:via-navy-400 hover:to-navy-500 text-white dark:from-[#1a4470] dark:via-[#2563a8] dark:to-[#1a4470] dark:hover:from-[#1e4d80] dark:hover:via-[#2d6fb5] dark:hover:to-[#1e4d80] rounded-xl font-semibold transition-all active:scale-95 shadow-lg shadow-navy-500/20 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
            Create First Paper
          </router-link>
    </div>
   </template>

   <div class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
     <article v-for="paper in filteredPapers" :key="paper.id"
      class="relative bg-white dark:bg-ash-800 rounded-2xl border border-cream-200 dark:border-ash-700 shadow-sm hover:shadow-[0_8px_30px_rgba(166,138,92,0.2)] dark:hover:shadow-[0_8px_30px_rgba(37,99,168,0.3)] transition-all duration-300 overflow-hidden group hover:border-cream-400 dark:hover:border-[#2563a8]/50 hover:-translate-y-0.5">
      <!-- Top accent bar -->
      <div class="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-amber-300 via-amber-400 to-amber-300 dark:from-[#1a4470] dark:via-[#3b82f6] dark:to-[#1a4470] opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
     <router-link :to="{ name: 'editor', params: { paperId: paper.id } }" @click="store.currentPaperId = null"
     class="block p-5 pb-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] rounded-t-2xl">
     <h3 class="font-semibold font-serif text-ink-900 dark:text-ink-50 text-base leading-snug line-clamp-3 mb-2 group-hover:text-navy-700 dark:group-hover:text-[#6db4f0] transition">
     {{ paper.title || 'Untitled Paper' }}
     </h3>
     <p v-if="paper.snippet" class="text-xs text-ink-500 dark:text-ink-400 line-clamp-2 mb-2 leading-relaxed">{{ paper.snippet }}</p>
     <div class="flex flex-wrap gap-2 text-xs">
     <span class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700 text-ink-700 dark:text-[#8ec5eb]" :title="'Updated: ' + new Date(paper.updated_at).toLocaleString('id-ID') + '\nCreated: ' + new Date(paper.created_at).toLocaleString('id-ID')">Updated {{ formatDate(paper.updated_at) }}</span>
     <span class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700 text-ink-700 dark:text-[#8ec5eb]"><span aria-hidden="true">🖼️</span> {{ paper.image_count || 0 }} image{{ paper.image_count === 1 ? '' : 's' }}</span>
     <span v-if="paper.journal" class="px-2 py-0.5 rounded-full bg-teal-50 dark:bg-teal-900/30 text-teal-800 dark:text-teal-300">{{ paper.journal }}</span>
     <span v-if="paper.section_count" class="px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300">{{ paper.section_count }} sections</span>
     </div>
     </router-link>

     <div class="flex items-center gap-2 px-4 pb-4">
          <button @click="openPaper(paper)"
          class="flex-1 px-3 py-1.5 min-h-[44px] bg-gradient-to-r from-cream-100 via-cream-200 to-cream-100 hover:from-cream-200 hover:via-cream-300 hover:to-cream-200 text-ink-900 dark:text-white dark:from-[#1a4470] dark:via-[#2563a8] dark:to-[#1a4470] dark:hover:from-[#1e4d80] dark:hover:via-[#2d6fb5] dark:hover:to-[#1e4d80] border border-transparent dark:border-[#2563a8]/40 text-xs rounded-lg transition font-medium active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"
          >
          Open
          </button>
          <button @click="copyPaper(paper)" :disabled="copying === paper.id"
          class="px-3 py-1.5 min-h-[44px] min-w-[44px] border border-cream-300 dark:border-ash-600 hover:bg-cream-100 dark:hover:bg-ash-700 text-ink-900 dark:text-ink-50 text-xs rounded-lg transition disabled:opacity-50 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"
          title="Copy paper"
          >
          {{ copying === paper.id ? '...' : 'Copy' }}
          </button>
          <button @click="confirmDelete(paper)"
          class="px-3 py-1.5 min-h-[44px] min-w-[44px] border border-red-300 dark:border-red-700 hover:bg-red-50 dark:hover:bg-red-900/30 text-red-700 dark:text-red-400 text-xs rounded-lg transition active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"
          title="Delete paper">
          Delete
          </button>
          </div>
 </article>
 </div>
 </StateView>
   </section>
 </main>

 <AppDialog v-if="deleteTarget" :open="!!deleteTarget" title="Delete Paper?" @close="deleteTarget = null">
 <p class="text-ink-700 dark:text-[#8ec5eb] text-sm">
 "<strong>{{ deleteTarget.title || 'Untitled Paper' }}</strong>" and all its images will be permanently deleted.
 </p>
 <template #actions>
 <button @click="deleteTarget = null"
 class="px-4 py-2.5 min-h-[44px] border border-cream-400 dark:border-ash-500 hover:bg-cream-100 dark:hover:bg-ash-700 text-ink-900 dark:text-ink-50 rounded-xl text-sm font-medium transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
 Cancel
 </button>
 <button @click="doDelete()"
 class="px-4 py-2.5 min-h-[44px] bg-[#c43655] hover:bg-[#c43655]/90 text-white rounded-xl text-sm font-medium transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
 Delete
 </button>
 </template>
 </AppDialog>

 <Teleport to="body">
 <div v-if="toastMsg" class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] px-4 py-2.5 rounded-lg shadow-lg text-white text-sm bg-ink-900 dark:bg-[#1a4470] dark:text-white">{{ toastMsg }}</div>
 </Teleport>

 <!-- Onboarding Wizard for new users -->
 <OnboardingWizard
 :open="showOnboarding"
 :user="auth.user"
 @complete="onOnboardingComplete"
 />

 <!-- Tour Guide overlay -->
 <TourGuide
   :active="showTour"
   :steps="tourSteps"
   @finish="onTourFinish"
   @skip="onTourFinish"
   />
   </div>
   </template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api/index.js'
import AppHeader from '../components/AppHeader.vue'
import AppDialog from '../components/AppDialog.vue'
import StateView from '../components/StateView.vue'
import OnboardingWizard from '../components/OnboardingWizard.vue'
import TourGuide from '../components/TourGuide.vue'
import { usePaperStore } from '../stores/paper.js'
import { useAuthStore } from '../stores/auth.js'
import { usePaperJobsStore } from '../stores/paperJobs.js'
import { useQuotaStore } from '../stores/quota.js'

const router = useRouter()
const route = useRoute()
const store = usePaperStore()
const auth = useAuthStore()
const jobsStore = usePaperJobsStore()
const quotaStore = useQuotaStore()

const lastUpdated = computed(() => {
  const dates = papers.value.map(p => p.updated_at).filter(Boolean).sort()
  return dates.length ? formatDate(dates[dates.length - 1]) : ''
})

// Onboarding wizard state
const showOnboarding = ref(false)
const showTour = ref(false)

// Tour steps for dashboard
const tourSteps = [
 { target: 'a[href="/editor"]', title: 'Buat Paper Baru', description: 'Klik tombol ini untuk membuat paper baru dengan AI.', position: 'bottom' },
 { target: '.grid', title: 'Daftar Paper Anda', description: 'Semua paper yang Anda buat akan muncul di sini. Klik untuk membuka.', position: 'top' },
]

// Check if user needs onboarding
async function checkOnboarding() {
 await auth.fetchMe()
 const user = auth.user
 // Show onboarding if profile is incomplete
 if (user && (!user.nickname || !user.institution)) {
 showOnboarding.value = true
 }
}

// Check if tour should run
function checkTour() {
 // Show tour if query param ?tour=1 or not done yet
 if (route.query.tour === '1' || !localStorage.getItem('pf_tour_done')) {
   showTour.value = true
   localStorage.setItem('pf_tour_done', '1')
   // Clear ?tour=1 from URL so refresh doesn't re-trigger
   if (route.query.tour === '1') {
     router.replace({ query: {} })
   }
 }
}

function onTourFinish() {
 showTour.value = false
 localStorage.setItem('pf_tour_done', '1')
}

function onOnboardingComplete() {
 showOnboarding.value = false
 // Start tour after onboarding completes
 checkTour()
}

const papers = ref([])
const loading = ref(true)
const deleteTarget = ref(null)
const searchQuery = ref('')
const sortBy = ref('updated')

const filteredPapers = computed(() => {
  let list = papers.value
  const q = searchQuery.value.toLowerCase().trim()
  if (q) {
    list = list.filter(p =>
      (p.title || '').toLowerCase().includes(q) ||
      (p.snippet || '').toLowerCase().includes(q)
    )
  }
  return [...list].sort((a, b) => {
    if (sortBy.value === 'title') return (a.title || '').localeCompare(b.title || '')
    if (sortBy.value === 'created') return new Date(b.created_at) - new Date(a.created_at)
    return new Date(b.updated_at) - new Date(a.updated_at)
  })
})
const copying = ref(null)
const errorMsg = ref('')
const toastMsg = ref('')
let toastTimer = null

function showToast(msg) {
 toastMsg.value = msg
 clearTimeout(toastTimer)
 toastTimer = setTimeout(() => { toastMsg.value = '' }, 2500)
}

async function loadPapers() {
 loading.value = true
 errorMsg.value = ''
 try {
 const res = await api.get('/api/papers')
 papers.value = res.data.papers || []
 } catch (e) {
 errorMsg.value = 'Failed to load papers'
 console.error('Failed to load papers', e)
 } finally {
 loading.value = false
 }
}

function openPaper(paper) {
 store.currentPaperId = null
 router.push({ name: 'editor', params: { paperId: paper.id } })
}

async function copyPaper(paper) {
 copying.value = paper.id
 try {
 const res = await api.get(`/api/papers/${paper.id}`)
 const data = { ...res.data }
 // Find next available copy number
 const base = (data.title || 'Untitled').replace(/ \(Copy(?: \d+)?\)$/, '')
 const existing = papers.value.filter(p => p.title?.startsWith(base + ' (Copy'))
 const copyNum = existing.length + 1
 data.title = base + (copyNum > 1 ? ` (Copy ${copyNum})` : ' (Copy)')
 delete data.id
 await api.post('/api/papers', data)
 await loadPapers()
 showToast('Paper copied')
 } catch (e) {
 showToast('Copy failed — try again')
 console.error('Copy failed', e)
 } finally {
 copying.value = null
 }
}

function confirmDelete(paper) {
 deleteTarget.value = paper
}

async function doDelete() {
 if (!deleteTarget.value) return
 try {
 const deletedId = deleteTarget.value.id
 await api.delete(`/api/papers/${deletedId}`)
 papers.value = papers.value.filter(p => p.id !== deletedId)
 // Clean stale jobs from bell dropdown immediately
 jobsStore.recentDone = jobsStore.recentDone.filter(j => j.paper_id !== deletedId)
 jobsStore.globalActiveJobs = jobsStore.globalActiveJobs.filter(j => j.paper_id !== deletedId)
 jobsStore.failedJobs = jobsStore.failedJobs.filter(j => j.paper_id !== deletedId)
 showToast('Paper deleted')
 } catch (e) {
 showToast('Delete failed — try again')
 console.error('Delete failed', e)
 } finally {
 deleteTarget.value = null
 }
}

function formatDate(iso) {
 if (!iso) return ''
 const d = new Date(iso)
 const now = new Date()
 const diff = now - d
 if (diff < 60000) return 'just now'
 if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
 if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
 if (diff < 86400000 * 7) return `${Math.floor(diff / 86400000)}d ago`
 return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

// Token Purchase
function goToTokenPurchase() {
 router.push('/tokens/purchase')
}

onMounted(async () => {
  await checkOnboarding()
  if (!showOnboarding.value) {
    checkTour()
  }
  quotaStore.fetchQuota()
  loadPapers()
})

// Reload papers whenever the route changes (e.g. navigating back from editor)
// Use a flag to avoid double-fetch on initial mount (watch fires immediately too)
let _dashMounted = false
watch(() => route.path, (newPath) => {
 if (!_dashMounted) { _dashMounted = true; return }
 if (newPath === '/dashboard') {
   loadPapers()
 }
})
onUnmounted(() => {
 clearTimeout(toastTimer)
})
</script>
