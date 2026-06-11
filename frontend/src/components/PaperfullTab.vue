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

    <!-- Hidden file input for PDF/DOCX/Excel/CSV -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".pdf,.docx,.doc,.xlsx,.xls,.csv"
      multiple
      class="hidden"
      @change="onFileChange"
    />

    <!-- Generating progress card -->
    <div
      v-if="generating || activeJob"
      class="rounded-lg border border-navy-200 dark:border-navy-700 bg-navy-50 dark:bg-navy-900/30 px-3 py-3 text-xs space-y-2"
    >
      <div class="flex items-center gap-2">
        <span class="inline-block w-3 h-3 border-2 border-navy-300 border-t-navy-600 dark:border-t-cream-300 rounded-full animate-spin"></span>
        <span class="font-medium text-navy-800 dark:text-navy-200 generating-text">
          Generating
          <span class="gen-dots"><span>.</span><span>.</span><span>.</span></span>
        </span>
        <span class="ml-auto font-mono font-bold text-navy-700 dark:text-navy-300">
          {{ displayProgress }}%
        </span>
      </div>

      <!-- Progress bar -->
      <div class="h-2 rounded-full bg-navy-200 dark:bg-navy-800 overflow-hidden">
        <div
          class="h-full bg-gradient-to-r from-navy-500 to-emerald-500 dark:from-cream-300 dark:to-emerald-400 transition-all duration-1000 ease-linear"
          :style="{ width: displayProgress + '%' }"
        />
      </div>

      <div class="text-navy-700 dark:text-navy-300 truncate">
        {{ activeJob?.prompt || generatingTopic || 'Generating paper...' }}
      </div>

      <!-- Stop button -->
      <div class="flex items-center gap-2">
        <div class="flex-1 text-navy-600 dark:text-navy-400 text-[10px]">
          {{ timeElapsed }}
        </div>
        <button
          @click="stopGeneration"
          class="px-3 py-1 min-h-[32px] text-[11px] font-semibold rounded-md bg-red-600 hover:bg-red-700 text-white active:scale-95 transition-transform"
        >
          ⬛ Stop
        </button>
      </div>
    </div>

    <div>
      <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Topik paper</label>
      <textarea
        v-model="topic"
        rows="4"
        :disabled="generating || !!activeJob"
        placeholder="Masukkan topik paper (mis. 'optimasi rute AGV dengan reinforcement learning')"
        class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm disabled:opacity-50"
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

    <!-- Action buttons -->
    <div class="flex items-center gap-2">
      <button
        @click="generate"
        :disabled="!topic.trim() || generating || !!activeJob"
        class="flex-1 px-4 py-2 bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-medium disabled:opacity-50 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30"
      >
        <span v-if="generating" class="inline-flex items-center gap-1">
          <span class="w-3 h-3 border-2 border-cream-200 border-t-transparent rounded-full animate-spin"></span>
          <span class="generating-btn-text">Generating</span>
        </span>
        <span v-else>Generate</span>
      </button>

      <!-- Hidden file attach button -->
      <button
        @click="triggerFileInput"
        :disabled="generating || !!activeJob"
        class="px-3 py-2 min-h-[40px] min-w-[40px] bg-cream-100 dark:bg-ash-700 hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-700 dark:text-ink-200 rounded-lg text-sm disabled:opacity-50 active:scale-95 transition-transform"
        title="Attach file (PDF/DOCX/Excel/CSV)"
      >
        📎
      </button>
    </div>

    <!-- Reasoning / Process output (below generate button) -->
    <div
      v-if="streamingOutput && (generating || activeJob)"
      class="rounded-lg border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 overflow-hidden"
    >
      <div class="flex items-center gap-2 px-3 py-2 border-b border-cream-300 dark:border-ash-600 bg-cream-100 dark:bg-ash-700">
        <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
        <span class="text-xs font-medium text-ink-900 dark:text-ink-50">Proses Reasoning</span>
      </div>
      <div class="max-h-64 overflow-y-auto p-3">
        <pre class="text-[11px] text-ink-700 dark:text-ink-200 whitespace-pre-wrap font-mono leading-relaxed">{{ streamingOutput }}</pre>
      </div>
    </div>

    <!-- Attached files preview (small, dismissable) -->
    <div v-if="attachedFiles.length" class="flex flex-wrap gap-1.5">
      <div
        v-for="(f, i) in attachedFiles"
        :key="i"
        class="flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] bg-cream-100 dark:bg-ash-700 border border-cream-300 dark:border-ash-600 text-ink-900 dark:text-ink-50"
      >
        <span>{{ f.extracted ? '✓' : '📄' }}</span>
        <span class="truncate max-w-[140px]" :title="f.name">{{ f.name }}</span>
        <button
          @click="removeFile(i)"
          class="text-ink-500 hover:text-red-500 ml-1 active:scale-95 transition-transform"
        >✕</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { usePaperStore } from '../stores/paper'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const store = usePaperStore()
const auth = useAuthStore()
const topic = ref('')
const generating = ref(false)
const generatingTopic = ref('')
const loadingStatus = ref(false)
const fileInputRef = ref(null)

// Progress tracking
const displayProgress = ref(0)
let _progressTimer = null

// Streaming output
const streamingOutput = ref('')

// File attachments (hidden - text extracted and appended to prompt)
const attachedFiles = ref([]) // [{name, text, extracted}]

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
let _startTime = null
let _timeTimer = null

const timeElapsed = ref('')

// Session persistence key
const SESSION_KEY = 'paperfull_state'

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

// Save state to sessionStorage
function saveState() {
  try {
    const state = {
      topic: topic.value,
      generating: generating.value,
      generatingTopic: generatingTopic.value,
      displayProgress: displayProgress.value,
      streamingOutput: streamingOutput.value,
      startTime: _startTime,
      jobId: activeJob.value?.id || activeJob.value?.job_id || null,
      attachedFiles: attachedFiles.value.map(f => ({
        name: f.name,
        text: f.text || '',
        extracted: f.extracted || false,
      })),
      selectedFacts: selectedFacts.value,
      selectedFiles: selectedFiles.value,
      selectedTables: selectedTables.value,
    }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(state))
  } catch { /* ignore */ }
}

// Restore state from sessionStorage
function restoreState() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return
    const state = JSON.parse(raw)
    if (state.topic) topic.value = state.topic
    if (state.generatingTopic) generatingTopic.value = state.generatingTopic
    if (state.streamingOutput) streamingOutput.value = state.streamingOutput
    if (state.startTime) _startTime = state.startTime
    // Restore attached files (text-only, no File object — user can re-attach originals if needed)
    if (state.attachedFiles && state.attachedFiles.length) {
      attachedFiles.value = state.attachedFiles.map(f => ({
        name: f.name,
        file: null,
        text: f.text || '',
        extracted: f.extracted || false,
      }))
    }
    if (state.selectedFacts) selectedFacts.value = state.selectedFacts
    if (state.selectedFiles) selectedFiles.value = state.selectedFiles
    if (state.selectedTables) selectedTables.value = state.selectedTables
    if (state.generating) {
      generating.value = true
      displayProgress.value = state.displayProgress || 0
      // Start local progress ticker
      startProgressTicker()
      startTimeTracker()
    }
  } catch { /* ignore */ }
}

function clearState() {
  try { sessionStorage.removeItem(SESSION_KEY) } catch { /* ignore */ }
}

// Progress ticker: 5→95% over 15 min (900s), 10s intervals
function startProgressTicker() {
  stopProgressTicker()
  if (!_startTime) _startTime = Date.now()
  _progressTimer = setInterval(() => {
    const elapsed = (Date.now() - _startTime) / 1000
    const pct = Math.min(95, 5 + Math.floor((elapsed / 900) * 90))
    displayProgress.value = pct
    saveState()
  }, 10000)
}

function stopProgressTicker() {
  if (_progressTimer) { clearInterval(_progressTimer); _progressTimer = null }
}

function startTimeTracker() {
  stopTimeTracker()
  if (!_startTime) return
  const update = () => {
    const elapsed = Math.floor((Date.now() - _startTime) / 1000)
    const min = Math.floor(elapsed / 60)
    const sec = elapsed % 60
    timeElapsed.value = `⏱ ${min}m ${sec.toString().padStart(2, '0')}s elapsed`
  }
  update()
  _timeTimer = setInterval(update, 1000)
}

function stopTimeTracker() {
  if (_timeTimer) { clearInterval(_timeTimer); _timeTimer = null }
}

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

// File handling
function triggerFileInput() {
  if (fileInputRef.value) fileInputRef.value.click()
}

function onFileChange(event) {
  const files = event.target.files
  if (!files || !files.length) return
  for (const file of files) {
    attachedFiles.value.push({
      name: file.name,
      file: file,
      text: '',
      extracted: false,
    })
  }
  // Reset input so same file can be selected again
  event.target.value = ''
}

function removeFile(index) {
  attachedFiles.value.splice(index, 1)
}

// Extract text from file on frontend (for PDF/DOCX we send to backend)
// For CSV/Excel we can try client-side, but for simplicity we send all to backend

async function checkActiveJob() {
  if (!store.currentPaperId) return
  try {
    const { usePaperJobsStore } = await import('../stores/paperJobs.js')
    const jobsStore = usePaperJobsStore()
    await jobsStore.fetchActive(store.currentPaperId)
    const job = jobsStore.activeByPaper[store.currentPaperId]
    activeJob.value = (job && job.id) ? job : null
    
    // If we have an active job but local state doesn't know about it,
    // sync from server state
    if (activeJob.value && !generating.value) {
      generating.value = true
      generatingTopic.value = activeJob.value.prompt || ''
      displayProgress.value = activeJob.value.progress || 5
      _startTime = activeJob.value.started_at ? new Date(activeJob.value.started_at).getTime() : Date.now()
      startProgressTicker()
      startTimeTracker()
      saveState()
      // Start SSE polling for streaming output
      startSSEPolling(activeJob.value.id)
    }
    
    // If job finished but local state still shows generating
    if (!activeJob.value && generating.value) {
      finishGeneration()
    }
    
    // If job is done (progress >= 100 or status is done)
    if (activeJob.value && (activeJob.value.progress >= 100 || activeJob.value.status === 'done')) {
      finishGeneration()
    }
  } catch {
    activeJob.value = null
  }
}

// SSE polling for streaming output
let _sseCtrl = null
function startSSEPolling(jobId) {
  stopSSEPolling()
  _sseCtrl = new AbortController()
  
  const poll = async () => {
    if (!_sseCtrl || _sseCtrl.signal.aborted) return
    try {
      const res = await fetch(`/api/job/${jobId}/stream`, {
        signal: _sseCtrl.signal,
        credentials: 'include',
        headers: { 'Accept': 'text/event-stream' },
      })
      if (!res.ok) return
      
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.stage) {
                streamingOutput.value += `[${data.stage}] ${data.status || ''}\n`
                if (data.percent) {
                  displayProgress.value = Math.max(displayProgress.value, data.percent)
                }
              }
              if (data.status === 'complete') {
                finishGeneration()
                return
              }
              if (data.status === 'cancelled') {
                cancelGeneration()
                return
              }
            } catch { /* skip malformed */ }
          }
        }
      }
    } catch { /* aborted or network error */ }
  }
  
  poll()
}

function stopSSEPolling() {
  if (_sseCtrl) { _sseCtrl.abort(); _sseCtrl = null }
}

function finishGeneration() {
  generating.value = false
  displayProgress.value = 100
  generatingTopic.value = ''
  _startTime = null
  stopProgressTicker()
  stopTimeTracker()
  stopSSEPolling()
  timeElapsed.value = ''
  clearState()
  // Reload paper in store
  if (store.currentPaperId) {
    store.loadPaperFromDb(store.currentPaperId)
  }
}

function cancelGeneration() {
  generating.value = false
  generatingTopic.value = ''
  _startTime = null
  stopProgressTicker()
  stopTimeTracker()
  stopSSEPolling()
  timeElapsed.value = ''
  streamingOutput.value += '\n[Dibatalkan oleh pengguna]\n'
  clearState()
  setTimeout(() => { streamingOutput.value = '' }, 3000)
}

// Watch for paper change to reload status
watch(() => store.currentPaperId, (newId) => {
  if (newId) {
    loadStatus()
    checkActiveJob()
  }
})

onMounted(() => {
  restoreState()
  checkActiveJob()
  loadStatus()
  _pollTimer = setInterval(checkActiveJob, 4000)
})

onUnmounted(() => {
  if (_pollTimer) clearInterval(_pollTimer)
  stopProgressTicker()
  stopTimeTracker()
  stopSSEPolling()
})

async function stopGeneration() {
  const jobId = activeJob.value?.id || activeJob.value?.job_id
  if (!jobId) return
  try {
    await api.post(`/api/job/${jobId}/cancel`)
    cancelGeneration()
    activeJob.value = null
  } catch (err) {
    console.warn('Failed to cancel job:', err)
  }
}

async function generate() {
  // Prevent double-generate on the same paper
  if (generating.value) {
    store.showToast('Sedang generating, tunggu sampai selesai.', 'warning')
    return
  }
  if (!store.currentPaperId) {
    store.showToast('Simpan paper dulu sebelum generate.', 'error')
    return
  }
  const t = topic.value.trim()
  if (!t) return
  
  generating.value = true
  generatingTopic.value = t
  displayProgress.value = 0
  streamingOutput.value = ''
  _startTime = Date.now()
  startProgressTicker()
  startTimeTracker()
  saveState()
  
  try {
    // Build prompt with file attachments
    let finalPrompt = t
    if (attachedFiles.value.length) {
      // Send files via FormData for backend extraction
      const formData = new FormData()
      formData.append('prompt', t)
      formData.append('paper_id', store.currentPaperId)
      formData.append('language', auth.user?.preferred_language || 'id')
      
      // Include status context
      if (hasContext.value) {
        const allFactKeys = Object.keys(statusData.value.facts || {})
        const allFileNames = (statusData.value.files || []).map(f => f.filename)
        const allTableNames = (statusData.value.tables || []).map(tb => tb.name)
        
        if (selectedFacts.value.length > 0 && selectedFacts.value.length < allFactKeys.length) {
          formData.append('selected_facts', JSON.stringify(selectedFacts.value))
        }
        if (selectedFiles.value.length > 0 && selectedFiles.value.length < allFileNames.length) {
          formData.append('selected_files', JSON.stringify(selectedFiles.value))
        }
        if (selectedTables.value.length > 0 && selectedTables.value.length < allTableNames.length) {
          formData.append('selected_tables', JSON.stringify(selectedTables.value))
        }
      }
      
      // Attach files
      for (const af of attachedFiles.value) {
        if (af.file) {
          formData.append('files', af.file)
          af.extracted = true
        }
      }
      
      const res = await api.post(`/api/papers/${store.currentPaperId}/generate`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      
      if (res.data?.job_id) {
        store.showToast('Paper generation started!', 'info')
        // Start SSE polling
        startSSEPolling(res.data.job_id)
      } else {
        throw new Error(res.data?.error || 'Failed to start generation')
      }
    } else {
      // Standard JSON request
      const payload = {
        prompt: t,
        paper_id: store.currentPaperId,
        include_status: true,
        language: auth.user?.preferred_language || 'id',
      }
      
      if (hasContext.value) {
        const allFactKeys = Object.keys(statusData.value.facts || {})
        const allFileNames = (statusData.value.files || []).map(f => f.filename)
        const allTableNames = (statusData.value.tables || []).map(tb => tb.name)
        
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
        store.showToast('Paper generation started!', 'info')
        // Start SSE polling
        startSSEPolling(res.data.job_id)
      } else {
        throw new Error(res.data?.error || 'Failed to start generation')
      }
    }
  } catch (err) {
    store.showToast('Error: ' + (err.response?.data?.error || err.message), 'error')
    generating.value = false
    stopProgressTicker()
    stopTimeTracker()
    stopSSEPolling()
    clearState()
  } finally {
    checkActiveJob()
  }
}
</script>

<style scoped>
@keyframes gen-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes gen-dots-blink {
  0%, 20% { opacity: 0; }
  40% { opacity: 1; }
  60%, 100% { opacity: 0; }
}

.generating-text {
  animation: gen-pulse 1.5s ease-in-out infinite;
}

.generating-btn-text {
  animation: gen-pulse 1.5s ease-in-out infinite;
}

.gen-dots {
  display: inline-flex;
  gap: 0;
}

.gen-dots span {
  font-weight: bold;
  animation: gen-dots-blink 1.4s ease-in-out infinite;
}

.gen-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.gen-dots span:nth-child(3) {
  animation-delay: 0.4s;
}
</style>
