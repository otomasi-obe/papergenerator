<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-navy-800 dark:text-ash-100">Charts</h2>
      <button @click="showEditor = true"
        class="px-4 py-2 bg-navy-600 dark:bg-cream-200 text-cream-50 dark:text-ash-900 rounded-lg hover:bg-navy-700 dark:hover:bg-cream-100 text-sm font-medium active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
        + Add Chart
      </button>
    </div>

    <p class="text-sm text-navy-500 dark:text-ash-200 mb-4">
      Create charts from your data. Reference in sections with
      <code class="bg-cream-200 dark:bg-ash-700 text-navy-800 dark:text-ash-100 px-1 rounded">[CHART:chart-1]</code>
    </p>

    <div v-if="loading" class="text-center py-12 text-navy-400 dark:text-ash-300">
      <p>Loading charts...</p>
    </div>

    <div v-else-if="charts.length === 0 && !showEditor"
      class="text-center py-12 text-navy-400 dark:text-ash-300">
      <svg class="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
      <p>No charts yet. Click "Add Chart" to create one.</p>
    </div>

    <div v-if="showEditor" class="border border-cream-200 dark:border-ash-700 rounded-xl mb-6 overflow-hidden bg-cream-50 dark:bg-ash-800">
      <div class="bg-cream-100 dark:bg-ash-700 px-4 py-3 flex items-center justify-between border-b border-cream-200 dark:border-ash-700">
        <span class="text-sm font-semibold text-navy-700 dark:text-ash-100">
          {{ editingChart ? 'Edit Chart' : 'New Chart' }}
        </span>
          <button @click="cancelEdit"
          class="text-navy-400 dark:text-ash-300 hover:text-navy-600 dark:hover:text-ash-100 text-sm">✕ Cancel</button>
      </div>

      <div class="p-4 space-y-4">
        <div>
            <label class="block text-xs text-navy-500 dark:text-ash-200 mb-1">Chart Type</label>
          <select v-model="chartForm.kind"
            class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-navy-900 dark:text-ash-100 rounded text-sm">
            <option value="line">Line Chart</option>
            <option value="bar">Bar Chart</option>
            <option value="scatter">Scatter Plot</option>
            <option value="pie">Pie Chart</option>
            <option value="hist">Histogram</option>
            <option value="box">Box Plot</option>
            <option value="heatmap">Heatmap</option>
          </select>
        </div>

        <div>
            <label class="block text-xs text-navy-500 dark:text-ash-200 mb-1">Title</label>
          <input v-model="chartForm.title" placeholder="Chart title"
            class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-navy-900 dark:text-ash-100 rounded text-sm" />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-navy-500 dark:text-ash-200 mb-1">X-axis Label</label>
          <input v-model="chartForm.xlabel" placeholder="X-axis"
            class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-navy-900 dark:text-ash-100 rounded text-sm" />
          </div>
          <div>
            <label class="block text-xs text-navy-500 dark:text-ash-200 mb-1">Y-axis Label</label>
          <input v-model="chartForm.ylabel" placeholder="Y-axis"
            class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-navy-900 dark:text-ash-100 rounded text-sm" />
          </div>
        </div>

        <div>
            <label class="block text-xs text-navy-500 dark:text-ash-200 mb-2">Data Input Method</label>
          <div class="flex gap-2 mb-3">
             <button @click="dataInputMethod = 'manual'"
              :class="['px-3 py-1.5 rounded text-sm', dataInputMethod === 'manual' ? 'bg-navy-600 text-white' : 'bg-cream-200 dark:bg-ash-700 text-navy-700 dark:text-ash-200']">
              Manual Entry
            </button>
            <button @click="dataInputMethod = 'upload'"
              :class="['px-3 py-1.5 rounded text-sm', dataInputMethod === 'upload' ? 'bg-navy-600 text-white' : 'bg-cream-200 dark:bg-ash-700 text-navy-700 dark:text-ash-200']">
              Upload File
            </button>
          </div>

          <div v-if="dataInputMethod === 'manual'">
            <label class="block text-xs text-navy-500 dark:text-ash-200 mb-1">Data (JSON format)</label>
          <textarea v-model="dataJson" rows="6" placeholder='{"data": [[1,2,3]], "series_labels": ["Series 1"], "x_data": ["A","B","C"]}'
              class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-navy-900 dark:text-ash-100 rounded text-sm font-mono"></textarea>
            <p class="text-xs text-navy-400 dark:text-ash-300 mt-1">
              Format: data (required), series_labels (optional), x_data (optional)
            </p>
          </div>

          <div v-else>
            <input type="file" @change="handleFileUpload" accept=".csv,.tsv,.xlsx,.xls"
              class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-navy-900 dark:text-ash-100 rounded text-sm" />
            <p class="text-xs text-navy-400 dark:text-ash-300 mt-1">
              Upload CSV, TSV, or Excel file
            </p>
            <div v-if="uploadedData" class="mt-2 p-2 bg-cream-100 dark:bg-ash-700 rounded text-xs dark:text-ash-100">
              <p class="font-semibold">Uploaded: {{ uploadedData.filename }}</p>
              <p>{{ uploadedData.n_rows }} rows, {{ uploadedData.columns.length }} columns</p>
            </div>
          </div>
        </div>

        <div v-if="error" class="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {{ error }}
        </div>

        <div class="flex gap-2">
          <button @click="saveChart" :disabled="saving"
            class="px-4 py-2 bg-navy-600 dark:bg-cream-200 text-white dark:text-ash-900 rounded hover:bg-navy-700 dark:hover:bg-cream-100 text-sm font-medium disabled:opacity-50 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
            {{ saving ? 'Saving...' : (editingChart ? 'Update Chart' : 'Create Chart') }}
          </button>
          <button @click="cancelEdit"
            class="px-4 py-2 bg-cream-200 dark:bg-ash-700 text-navy-700 dark:text-ash-200 rounded hover:bg-cream-300 dark:hover:bg-ash-600 text-sm font-medium focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
            Cancel
          </button>
        </div>
      </div>
    </div>

    <div v-for="chart in charts" :key="chart.image_id"
      class="border border-cream-200 dark:border-ash-700 rounded-xl mb-4 overflow-hidden">
      <div class="bg-cream-100 dark:bg-ash-700 px-4 py-3 flex items-center justify-between border-b border-cream-200 dark:border-ash-700">
        <span class="text-sm font-semibold text-navy-700 dark:text-ash-100">
          {{ chart.kind }} - {{ chart.original_name }}
        </span>
        <div class="flex gap-2">
          <button @click="editChart(chart)"
             class="text-navy-600 dark:text-ash-300 hover:text-navy-800 dark:hover:text-ash-100 text-sm">Edit</button>
          <button @click="deleteChart(chart.image_id)"
            class="text-red-400 dark:text-red-300 hover:text-red-600 dark:hover:text-red-200 text-sm">Delete</button>
        </div>
      </div>

      <div class="p-4">
        <img :src="chart.url" :alt="chart.original_name" class="max-w-full h-auto rounded border border-cream-300 dark:border-ash-600" />
        <div class="mt-3 bg-cream-100 dark:bg-ash-700 border border-cream-200 dark:border-ash-700 rounded p-2">
            <p class="text-xs text-navy-700 dark:text-ash-200">
            <strong>Usage:</strong> Insert <code class="bg-cream-200 dark:bg-ash-600 px-1 rounded">[CHART:{{ chart.image_id }}]</code> in section content.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import chartsApi, { type Chart, type ChartSpec } from '../api/charts'

const route = useRoute()
const paperId = computed(() => route.params.paperId as string)

const charts = ref<Chart[]>([])
const loading = ref(false)
const showEditor = ref(false)
const editingChart = ref<Chart | null>(null)
const saving = ref(false)
const error = ref('')
const dataInputMethod = ref<'manual' | 'upload'>('manual')
const dataJson = ref('')
const uploadedData = ref<any>(null)

const chartForm = ref<ChartSpec>({
  kind: 'line',
  title: '',
  xlabel: '',
  ylabel: '',
  data: [],
  series_labels: [],
  x_data: []
})

async function loadCharts() {
  loading.value = true
  error.value = ''
  try {
    const response = await chartsApi.list(paperId.value)
    charts.value = response.charts
  } catch (e: any) {
    error.value = e.response?.data?.error || 'Failed to load charts'
  } finally {
    loading.value = false
  }
}

async function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  error.value = ''
  try {
    uploadedData.value = await chartsApi.uploadData(paperId.value, file)
    dataJson.value = JSON.stringify({
      data: uploadedData.value.rows.map((row: any[]) => row.map(v => parseFloat(v) || 0)),
      series_labels: uploadedData.value.columns,
      x_data: uploadedData.value.rows.map((_: any, i: number) => `Row ${i + 1}`)
    }, null, 2)
  } catch (e: any) {
    error.value = e.response?.data?.error || 'Failed to upload file'
  }
}

async function saveChart() {
  error.value = ''
  
  let parsedData
  try {
    parsedData = JSON.parse(dataJson.value || '{}')
  } catch (e) {
    error.value = 'Invalid JSON format'
    return
  }

  if (!chartForm.value.title) {
    error.value = 'Title is required'
    return
  }

  if (!parsedData.data || !Array.isArray(parsedData.data) || parsedData.data.length === 0) {
    error.value = 'Data is required and must be a non-empty array'
    return
  }

  const spec: ChartSpec = {
    kind: chartForm.value.kind,
    title: chartForm.value.title,
    xlabel: chartForm.value.xlabel,
    ylabel: chartForm.value.ylabel,
    data: parsedData.data,
    series_labels: parsedData.series_labels || [],
    x_data: parsedData.x_data || undefined
  }

  saving.value = true
  try {
    if (editingChart.value) {
      await chartsApi.update(paperId.value, editingChart.value.image_id, spec)
    } else {
      await chartsApi.create(paperId.value, spec)
    }
    await loadCharts()
    cancelEdit()
  } catch (e: any) {
    error.value = e.response?.data?.error || 'Failed to save chart'
  } finally {
    saving.value = false
  }
}

function editChart(chart: Chart) {
  editingChart.value = chart
  chartForm.value.kind = chart.kind as any
  showEditor.value = true
}

async function deleteChart(chartId: number) {
  if (!confirm('Are you sure you want to delete this chart?')) return

  error.value = ''
  try {
    await chartsApi.delete(paperId.value, chartId)
    await loadCharts()
  } catch (e: any) {
    error.value = e.response?.data?.error || 'Failed to delete chart'
  }
}

function cancelEdit() {
  showEditor.value = false
  editingChart.value = null
  chartForm.value = {
    kind: 'line',
    title: '',
    xlabel: '',
    ylabel: '',
    data: [],
    series_labels: [],
    x_data: []
  }
  dataJson.value = ''
  uploadedData.value = null
  error.value = ''
}

onMounted(() => {
  loadCharts()
})
</script>
