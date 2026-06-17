<template>
  <!-- FAQ analytics chart — shows top questions asked to AI -->
  <div class="faq-chart rounded-xl border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 p-4">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-100">
        {{ title }}
      </h3>
      <span class="text-xs text-ink-600 dark:text-ink-300">{{ periodLabel }}</span>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex items-center justify-center py-8">
      <div class="w-5 h-5 border-2 border-navy-400 border-t-transparent rounded-full animate-spin"></div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="text-xs text-red-600 dark:text-red-400 py-4 text-center">
      {{ error }}
    </div>

    <!-- Empty state -->
    <div v-else-if="!data.length" class="text-xs text-ink-600 dark:text-ink-300 py-8 text-center">
      Belum ada data pertanyaan.
    </div>

    <!-- Chart -->
    <div v-else class="chart-wrapper" style="height: 320px;">
      <Bar :data="chartData" :options="chartOptions" />
    </div>

    <!-- Legend / total -->
    <div v-if="data.length" class="mt-3 flex items-center justify-between text-xs text-ink-600 dark:text-ink-300">
      <span>Total pertanyaan: <strong class="text-ink-900 dark:text-ink-100">{{ totalQuestions }}</strong></span>
      <span>Top {{ Math.min(data.length, maxItems) }} dari {{ data.length }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { computed, ref, onMounted } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  Title,
  Tooltip,
  Legend,
  BarElement,
  CategoryScale,
  LinearScale,
} from 'chart.js'

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale)

interface FaqItem {
  question: string
  count: number
}

interface Props {
  title?: string
  period?: 'day' | 'week' | 'month' | 'all'
  maxItems?: number
  /** Pre-fetched data; if not provided, component fetches on mount */
  data?: FaqItem[]
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Pertanyaan Paling Sering Diajukan',
  period: 'month',
  maxItems: 10,
  data: () => [],
})

const loading = ref(false)
const error = ref('')

const periodLabel = computed(() => {
  const map = { day: 'Hari ini', week: '7 hari terakhir', month: '30 hari terakhir', all: 'Semua waktu' }
  return map[props.period] || map.month
})

const chartData = computed(() => {
  const items = (props.data || []).slice(0, props.maxItems)
  // Truncate long questions for display
  const labels = items.map(i => {
    const q = i.question
    return q.length > 50 ? q.slice(0, 47) + '...' : q
  })
  const counts = items.map(i => i.count)

  return {
    labels,
    datasets: [
      {
        label: 'Jumlah ditanyakan',
        data: counts,
        backgroundColor: 'rgba(59, 130, 246, 0.6)',
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 1,
        borderRadius: 4,
        maxBarThickness: 28,
      },
    ],
  }
})

const chartOptions = computed(() => ({
  indexAxis: 'y' as const,
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        title: (items: any[]) => {
          const idx = items[0]?.dataIndex
          return (props.data || [])[idx]?.question || ''
        },
        label: (item: any) => `${item.raw} kali ditanyakan`,
      },
    },
  },
  scales: {
    x: {
      beginAtZero: true,
      grid: { color: 'rgba(0,0,0,0.05)' },
      ticks: { precision: 0 },
    },
    y: {
      grid: { display: false },
      ticks: { font: { size: 11 } },
    },
  },
}))

const totalQuestions = computed(() => {
  return (props.data || []).reduce((sum, i) => sum + i.count, 0)
})
</script>
