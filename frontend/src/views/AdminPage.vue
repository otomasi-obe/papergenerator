<template>
  <div class="min-h-screen bg-gray-50">
    <AppHeader />

    <main class="max-w-6xl mx-auto px-4 py-8">
      <div class="mb-8">
        <h1 class="text-2xl font-bold text-gray-800">Admin Dashboard</h1>
        <p class="text-gray-500 text-sm mt-1">Monitor usage, users, and all papers</p>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="text-center py-20 text-gray-400">
        <div class="w-8 h-8 border-4 border-blue-200 border-t-blue-500 rounded-full animate-spin mx-auto mb-3"></div>
        Loading...
      </div>

      <div v-else>
        <!-- Stats Cards -->
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <div v-for="stat in statsCards" :key="stat.label"
            class="bg-white rounded-2xl border shadow-sm p-5 text-center">
            <div class="text-2xl mb-1">{{ stat.icon }}</div>
            <div class="text-2xl font-bold text-gray-800">{{ formatNum(stat.value) }}</div>
            <div class="text-xs text-gray-500 mt-1">{{ stat.label }}</div>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex gap-2 mb-6 flex-wrap">
          <button v-for="tab in adminTabs" :key="tab.id" @click="activeTab = tab.id"
            :class="['px-4 py-2 rounded-xl text-sm font-medium transition-colors',
              activeTab === tab.id ? 'bg-blue-600 text-white' : 'bg-white border text-gray-600 hover:bg-gray-50']">
            {{ tab.label }}
          </button>
        </div>

        <!-- TAB: API Usage -->
        <div v-if="activeTab === 'usage'" class="space-y-6">
          <!-- By Endpoint -->
          <div class="bg-white rounded-2xl border shadow-sm p-6">
            <h3 class="font-semibold text-gray-700 mb-4">Usage by Endpoint</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-gray-400 border-b text-xs uppercase">
                    <th class="pb-2 pr-4">Endpoint</th>
                    <th class="pb-2 pr-4 text-right">Calls</th>
                    <th class="pb-2 text-right">Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in usage.by_endpoint" :key="row.endpoint" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="py-2 pr-4 font-mono text-xs bg-gray-50 rounded px-2 my-1 w-fit">{{ row.endpoint }}</td>
                    <td class="py-2 pr-4 text-right text-gray-700">{{ formatNum(row.calls) }}</td>
                    <td class="py-2 text-right text-gray-700">{{ formatNum(row.tokens) }}</td>
                  </tr>
                  <tr v-if="!usage.by_endpoint?.length">
                    <td colspan="3" class="text-center py-6 text-gray-400">No API calls recorded yet</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Per User -->
          <div class="bg-white rounded-2xl border shadow-sm p-6">
            <h3 class="font-semibold text-gray-700 mb-4">Usage per User</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-gray-400 border-b text-xs uppercase">
                    <th class="pb-2 pr-4">User</th>
                    <th class="pb-2 pr-4 text-right">Calls</th>
                    <th class="pb-2 text-right">Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in usage.per_user" :key="row.email" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="py-2 pr-4">
                      <div class="font-medium text-gray-800">{{ row.name }}</div>
                      <div class="text-xs text-gray-400">{{ row.email }}</div>
                    </td>
                    <td class="py-2 pr-4 text-right">{{ formatNum(row.calls) }}</td>
                    <td class="py-2 text-right">{{ formatNum(row.tokens) }}</td>
                  </tr>
                  <tr v-if="!usage.per_user?.length">
                    <td colspan="3" class="text-center py-6 text-gray-400">No usage records yet</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Daily Chart (simple bar) -->
          <div class="bg-white rounded-2xl border shadow-sm p-6">
            <h3 class="font-semibold text-gray-700 mb-4">Daily Calls (last 30 days)</h3>
            <div v-if="usage.daily?.length" class="flex items-end gap-1 h-32">
              <div v-for="d in usage.daily" :key="d.date"
                class="flex-1 bg-blue-400 rounded-t min-w-[6px] hover:bg-blue-500 transition-colors cursor-default relative group"
                :style="{ height: `${maxDailyCalls > 0 ? (d.calls / maxDailyCalls) * 100 : 0}%` }">
                <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 bg-gray-800 text-white text-xs rounded px-2 py-1 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                  {{ d.date }}: {{ d.calls }} calls
                </div>
              </div>
            </div>
            <p v-else class="text-center text-gray-400 text-sm py-8">No daily data yet</p>
          </div>
        </div>

        <!-- TAB: All Papers -->
        <div v-if="activeTab === 'papers'">
          <div class="bg-white rounded-2xl border shadow-sm overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="bg-gray-50 border-b">
                  <tr class="text-left text-gray-400 text-xs uppercase">
                    <th class="px-4 py-3">Title</th>
                    <th class="px-4 py-3">User</th>
                    <th class="px-4 py-3 text-right">Images</th>
                    <th class="px-4 py-3 text-right">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in allPapers" :key="p.id" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="px-4 py-3">
                      <div class="font-medium text-gray-800 max-w-xs truncate">{{ p.title || 'Untitled' }}</div>
                      <div class="text-xs text-gray-400 font-mono">{{ p.id }}</div>
                    </td>
                    <td class="px-4 py-3">
                      <div class="text-gray-700">{{ p.user_name }}</div>
                      <div class="text-xs text-gray-400">{{ p.user_email }}</div>
                    </td>
                    <td class="px-4 py-3 text-right text-gray-600">{{ p.image_count }}</td>
                    <td class="px-4 py-3 text-right text-gray-400 text-xs whitespace-nowrap">{{ formatDate(p.updated_at) }}</td>
                  </tr>
                  <tr v-if="!allPapers.length">
                    <td colspan="4" class="px-4 py-8 text-center text-gray-400">No papers yet</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- TAB: Users -->
        <div v-if="activeTab === 'users'">
          <div class="bg-white rounded-2xl border shadow-sm overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="bg-gray-50 border-b">
                  <tr class="text-left text-gray-400 text-xs uppercase">
                    <th class="px-4 py-3">User</th>
                    <th class="px-4 py-3">Role</th>
                    <th class="px-4 py-3 text-right">Quota</th>
                    <th class="px-4 py-3 text-right">Used</th>
                    <th class="px-4 py-3 text-right">Papers</th>
                    <th class="px-4 py-3 text-right">Joined</th>
                    <th class="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="u in allUsers" :key="u.id" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="px-4 py-3">
                      <div class="font-medium text-gray-800">{{ u.name }}</div>
                      <div class="text-xs text-gray-400">{{ u.email }}</div>
                    </td>
                    <td class="px-4 py-3">
                      <span :class="['text-xs px-2 py-0.5 rounded-full font-medium',
                        u.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600']">
                        {{ u.role }}
                      </span>
                    </td>
                    <!-- Quota inline edit -->
                    <td class="px-4 py-3 text-right">
                      <input
                        v-if="u.role !== 'admin'"
                        type="number"
                        :value="u.token_quota_monthly ?? 50000"
                        @blur="saveQuota(u, $event.target.value)"
                        @keyup.enter="$event.target.blur()"
                        min="0" step="1000"
                        class="w-24 text-right tabular-nums px-2 py-1 border border-gray-200 rounded text-xs focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-500"
                        title="Klik untuk edit kuota bulanan"
                      />
                      <span v-else class="text-xs text-gray-400">∞</span>
                    </td>
                    <td class="px-4 py-3 text-right">
                      <span class="tabular-nums text-xs"
                        :class="quotaPercent(u) >= 90 ? 'text-red-600 font-semibold' : quotaPercent(u) >= 70 ? 'text-amber-600' : 'text-gray-600'">
                        {{ formatNum(u.token_used_month || 0) }}
                      </span>
                    </td>
                    <td class="px-4 py-3 text-right">{{ u.paper_count }}</td>
                    <td class="px-4 py-3 text-right text-xs text-gray-400">{{ formatDate(u.created_at) }}</td>
                    <td class="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                      <button v-if="u.role !== 'admin'" @click="resetQuota(u)" class="text-xs text-blue-600 hover:underline">Reset</button>
                      <button v-if="u.role !== 'admin'" @click="promoteUser(u, 'admin')"
                        class="text-xs text-purple-600 hover:underline">Make Admin</button>
                      <button v-else @click="promoteUser(u, 'user')"
                        class="text-xs text-gray-400 hover:underline">Demote</button>
                    </td>
                  </tr>
                  <tr v-if="!allUsers.length">
                    <td colspan="7" class="px-4 py-8 text-center text-gray-400">No users yet</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/index.js'
import AppHeader from '../components/AppHeader.vue'

const loading = ref(true)
const activeTab = ref('usage')
const usage = ref({ total: {}, by_endpoint: [], daily: [], per_user: [] })
const allPapers = ref([])
const allUsers = ref([])
const stats = ref({})

const adminTabs = [
  { id: 'usage', label: '📊 API Usage' },
  { id: 'papers', label: '📄 All Papers' },
  { id: 'users', label: '👤 Users' },
]

const statsCards = computed(() => [
  { icon: '👤', label: 'Total Users', value: stats.value.total_users || 0 },
  { icon: '📄', label: 'Total Papers', value: stats.value.total_papers || 0 },
  { icon: '🖼️', label: 'Total Images', value: stats.value.total_images || 0 },
  { icon: '⚡', label: 'API Calls', value: stats.value.total_api_calls || 0 },
  { icon: '🔢', label: 'Tokens Used', value: stats.value.total_tokens || 0 },
])

const maxDailyCalls = computed(() => Math.max(...(usage.value.daily || []).map(d => d.calls), 1))

function formatNum(n) {
  if (!n) return '0'
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

async function promoteUser(user, role) {
  try {
    await api.post(`/api/admin/users/${user.id}/promote`, { role })
    user.role = role
  } catch (e) {
    console.error('Promote failed', e)
  }
}

// rofiq.txt: admin set quota per user inline + reset.
async function saveQuota(user, value) {
  const v = parseInt(value, 10)
  if (!Number.isFinite(v) || v < 0) return
  if (v === user.token_quota_monthly) return
  try {
    const res = await api.patch(`/api/admin/users/${user.id}/quota`, {
      token_quota_monthly: v,
    })
    if (res?.data?.user) Object.assign(user, res.data.user)
  } catch (e) {
    console.error('saveQuota failed', e)
  }
}

async function resetQuota(user) {
  if (!confirm(`Reset kuota ${user.email} ke 0 untuk bulan ini?`)) return
  try {
    const res = await api.post(`/api/admin/users/${user.id}/reset-quota`)
    if (res?.data?.user) Object.assign(user, res.data.user)
  } catch (e) {
    console.error('resetQuota failed', e)
  }
}

function quotaPercent(u) {
  const q = u.token_quota_monthly || 0
  const used = u.token_used_month || 0
  if (q <= 0) return 0
  return Math.min(100, (used / q) * 100)
}

let _refreshTimer = null

async function loadAll() {
  loading.value = true
  try {
    const [usageRes, papersRes, usersRes, statsRes] = await Promise.all([
      api.get('/api/admin/usage'),
      api.get('/api/admin/papers'),
      api.get('/api/admin/users'),
      api.get('/api/admin/stats'),
    ])
    usage.value = usageRes.data
    allPapers.value = papersRes.data.papers || []
    allUsers.value = usersRes.data.users || []
    stats.value = statsRes.data
  } catch (e) {
    console.error('Failed to load admin data', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAll()
  // rofiq.txt: auto-refresh tiap 30 detik agar admin pantau usage real-time.
  _refreshTimer = setInterval(loadAll, 30_000)
})

import { onBeforeUnmount } from 'vue'
onBeforeUnmount(() => { if (_refreshTimer) clearInterval(_refreshTimer) })
</script>
