<template>
  <div class="space-y-4">
    <div class="flex items-center gap-2">
      <img src="/assets/logo.png" alt="Paperfull" class="h-8 w-8 rounded-md object-contain" />
      <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">Paperfull</h2>
    </div>

    <p class="text-sm text-ink-600 dark:text-ink-300">
      Buat paper utuh dari sebuah topik. AI akan menghasilkan kerangka, mengisi section, lalu
      menyimpannya ke paper aktif.
    </p>

    <!-- Active job banner (non-blocking) -->
    <div v-if="activeJob" class="rounded-lg border border-navy-200 dark:border-navy-700 bg-navy-50 dark:bg-navy-900/30 px-3 py-2 text-xs">
      <div class="flex items-center gap-2 mb-1">
        <span class="inline-block w-3 h-3 border-2 border-navy-300 border-t-navy-600 dark:border-t-cream-300 rounded-full animate-spin"></span>
        <span class="font-medium text-navy-800 dark:text-navy-200">Paper sedang diproses</span>
      </div>
      <div class="h-1 rounded-full bg-navy-200 dark:bg-navy-800 overflow-hidden">
        <div class="h-full bg-navy-500 dark:bg-cream-300 transition-all"
             :style="{ width: (activeJob.progress || 0) + '%' }" />
      </div>
      <div class="mt-1 text-navy-700 dark:text-navy-300 truncate">
        {{ activeJob.prompt || 'Generating...' }}
      </div>
      <p class="mt-1 text-navy-600 dark:text-navy-400">Progress lengkap ada di lonceng 🔔 di atas.</p>
    </div>

    <div>
      <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Topik paper</label>
      <textarea
        v-model="topic"
        rows="4"
        placeholder="Masukkan topik paper (mis. 'optimasi rute AGV dengan reinforcement learning')"
        class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm"
      ></textarea>
    </div>

    <!-- Context from Chat Session -->
    <div v-if="hasContext" class="space-y-3 border border-cream-300 dark:border-ash-600 rounded-lg p-3 bg-cream-50/50 dark:bg-ash-800/30">
      <div class="flex items-center gap-2">
        <span class="text-lg">🧠</span>
        <h3 class="text-sm font-medium text-ink-900 dark:text-ink-50">Context dari Planning Session</h3>
        <button 
          @click="loadStatus" 
          class="ml-auto text-xs text-navy-600 dark:text-navy-300 hover:underline"
          :disabled="loadingStatus"
        >
          {{ loadingStatus ? 'Loading...' : 'Refresh' }}
        </button>
      </div>

      <!-- Facts -->
      <div v-if="factsCount > 0" class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-medium text-ink-700 dark:text-ink-200">
            Facts ({{ factsCount }})
          </label>
          <button 
            @click="toggleAllFacts" 
            class="text-xs text-navy-600 dark:text-navy-300 hover:underline"
          >
            {{ allFactsSelected ? 'Unselect All' : 'Select All' }}
          </button>
        </div>
        <div class="space-y-1 max-h-32 overflow-y-auto">
          <label 
            v-for="(factData, key) in statusData.facts" 
            :key="key"
            class="flex items-start gap-2 text-xs cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-700 p-1 rounded"
          >
            <input 
              type="checkbox" 
              v-model="selectedFacts" 
              :value="key"
              class="mt-0.5 rounded"
            />
            <span class="flex-1">
              <span class="font-medium text-ink-900 dark:text-ink-50">{{ key }}:</span>
              <span class="text-ink-600 dark:text-ink-300 ml-1">{{ factData.value }}</span>
            </span>
          </label>
        </div>
      </div>

      <!-- Files -->
      <div v-if="filesCount > 0" class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-medium text-ink-700 dark:text-ink-200">
            Files ({{ filesCount }})
          </label>
          <button 
            @click="toggleAllFiles" 
            class="text-xs text-navy-600 dark:text-navy-300 hover:underline"
          >
            {{ allFilesSelected ? 'Unselect All' : 'Select All' }}
          </button>
        </div>
        <div class="space-y-1 max-h-32 overflow-y-auto">
          <label 
            v-for="(file, idx) in statusData.files" 
            :key="idx"
            class="flex items-center gap-2 text-xs cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-700 p-1 rounded"
          >
            <input 
              type="checkbox" 
              v-model="selectedFiles" 
              :value="file.filename"
              class="rounded"
            />
            <span class="text-ink-900 dark:text-ink-50">{{ file.filename }}</span>
          </label>
        </div>
      </div>

      <!-- Tables -->
      <div v-if="tablesCount > 0" class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-medium text-ink-700 dark:text-ink-200">
            Tables ({{ tablesCount }})
          </label>
          <button 
            @click="toggleAllTables" 
            class="text-xs text-navy-600 dark:text-navy-300 hover:underline"
          >
            {{ allTablesSelected ? 'Unselect All' : 'Select All' }}
          </button>
        </div>
        <div class="space-y-1 max-h-32 overflow-y-auto">
          <label 
            v-for="(table, idx) in statusData.tables" 
            :key="idx"
            class="flex items-start gap-2 text-xs cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-700 p-1 rounded"
          >
            <input 
              type="checkbox" 
              v-model="selectedTables" 
              :value="table.name"
              class="mt-0.5 rounded"
            />
            <span class="flex-1">
              <span class="font-medium text-ink-900 dark:text-ink-50">{{ table.name }}</span>
              <span v-if="table.rows" class="text-ink-600 dark:text-ink-300 ml-1">({{ table.rows }} rows)</span>
            </span>
          </label>
        </div>
      </div>

      <p v-if="!hasContext" class="text-xs text-ink-500 dark:text-ink-400 italic">
        Belum ada context dari chat session. Mulai chat untuk mengumpulkan informasi.
      </p>
    </div>

    <button
      @click="generate"
      :disabled="!topic.trim() || generating"
      class="w-full px-4 py-2 bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-medium disabled:opacity-50 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30"
    >
      {{ generating ? 'Mengirim...' : 'Generate' }}
    </button>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { usePaperStore } from '../stores/paper'
import api from '../api'

const store = usePaperStore()
const topic = ref('')
const generating = ref(false)
const loadingStatus = ref(false)

// Status data from chat session
const statusData = ref({
  facts: {},
  files: [],
  tables: [],
  notes: []
})

// Selected items
const selectedFacts = ref([])
const selectedFiles = ref([])
const selectedTables = ref([])

let _pollTimer = null
const activeJob = ref(null)

// Computed properties
const factsCount = computed(() => Object.keys(statusData.value.facts || {}).length)
const filesCount = computed(() => (statusData.value.files || []).length)
const tablesCount = computed(() => (statusData.value.tables || []).length)
const hasContext = computed(() => factsCount.value > 0 || filesCount.value > 0 || tablesCount.value > 0)

const allFactsSelected = computed(() => {
  const total = factsCount.value
  return total > 0 && selectedFacts.value.length === total
})

const allFilesSelected = computed(() => {
  const total = filesCount.value
  return total > 0 && selectedFiles.value.length === total
})

const allTablesSelected = computed(() => {
  const total = tablesCount.value
  return total > 0 && selectedTables.value.length === total
})

// Load status from API
async function loadStatus() {
  if (!store.currentPaperId) return
  
  loadingStatus.value = true
  try {
    const res = await api.get(`/api/papers/${store.currentPaperId}/status`)
    if (res.data) {
      statusData.value = res.data
      
      // Auto-select all items by default
      selectedFacts.value = Object.keys(res.data.facts || {})
      selectedFiles.value = (res.data.files || []).map(f => f.filename)
      selectedTables.value = (res.data.tables || []).map(t => t.name)
    }
  } catch (err) {
    console.warn('Failed to load status:', err)
  } finally {
    loadingStatus.value = false
  }
}

// Toggle functions
function toggleAllFacts() {
  if (allFactsSelected.value) {
    selectedFacts.value = []
  } else {
    selectedFacts.value = Object.keys(statusData.value.facts || {})
  }
}

function toggleAllFiles() {
  if (allFilesSelected.value) {
    selectedFiles.value = []
  } else {
    selectedFiles.value = (statusData.value.files || []).map(f => f.filename)
  }
}

function toggleAllTables() {
  if (allTablesSelected.value) {
    selectedTables.value = []
  } else {
    selectedTables.value = (statusData.value.tables || []).map(t => t.name)
  }
}

async function checkActiveJob() {
  if (!store.currentPaperId) return
  try {
    const { usePaperJobsStore } = await import('../stores/paperJobs.js')
    const jobsStore = usePaperJobsStore()
    await jobsStore.fetchActive(store.currentPaperId)
    const job = jobsStore.activeByPaper[store.currentPaperId]
    activeJob.value = (job && job.id) ? job : null
  } catch {
    activeJob.value = null
  }
}

// Watch for paper change to reload status
watch(() => store.currentPaperId, (newId) => {
  if (newId) {
    loadStatus()
  }
})

onMounted(() => {
  checkActiveJob()
  loadStatus()
  _pollTimer = setInterval(checkActiveJob, 5000)
})

onUnmounted(() => {
  if (_pollTimer) clearInterval(_pollTimer)
})

async function generate() {
  if (!store.currentPaperId) {
    store.showToast('Simpan paper dulu sebelum generate.', 'error')
    return
  }
  const t = topic.value.trim()
  if (!t) return
  
  generating.value = true
  try {
    // Use modern endpoint with status context support
    const payload = {
      prompt: t,
      include_status: true
    }
    
    // Only send selections if user has deselected some items
    // (empty array = user unchecked all, null/undefined = use all)
    if (hasContext.value) {
      const allFactKeys = Object.keys(statusData.value.facts || {})
      const allFileNames = (statusData.value.files || []).map(f => f.filename)
      const allTableNames = (statusData.value.tables || []).map(t => t.name)
      
      // Only send if not all selected (to optimize payload)
      if (selectedFacts.value.length > 0 && selectedFacts.value.length < allFactKeys.length) {
        payload.selected_facts = selectedFacts.value
      }
      if (selectedFiles.value.length > 0 && selectedFiles.value.length < allFileNames.length) {
        payload.selected_files = selectedFiles.value
      }
      if (selectedTables.value.length > 0 && selectedTables.value.length < allTableNames.length) {
        payload.selected_tables = selectedTables.value
      }
    }
    
    const res = await api.post(`/api/papers/${store.currentPaperId}/generate`, payload)
    
    if (res.data?.job_id) {
      store.showToast('Paper generation started! Check the bell icon for progress.', 'info')
    } else {
      throw new Error(res.data?.error || 'Failed to start generation')
    }
  } catch (err) {
    store.showToast('Error: ' + (err.response?.data?.error || err.message), 'error')
  } finally {
    generating.value = false
    checkActiveJob()
  }
}
</script>
