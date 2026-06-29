<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <AppHeader />

    <main class="max-w-6xl mx-auto px-4 py-8">
      <div class="mb-8">
        <h1 class="text-2xl font-bold text-ink-900 dark:text-ink-50">Admin Dashboard</h1>
        <p class="text-ink-600 dark:text-ink-300 text-sm mt-1">Monitor usage, users, and all papers</p>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="text-center py-20 text-ink-500 dark:text-ink-300">
        <div class="w-8 h-8 border-4 border-[var(--accent)]/20 border-t-[var(--accent)] rounded-full animate-spin mx-auto mb-3"></div>
        Loading...
      </div>

      <div v-else>
        <!-- Stats Cards -->
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <div v-for="stat in statsCards" :key="stat.label"
            class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-5 text-center">
            <div class="text-2xl mb-1">{{ stat.icon }}</div>
            <div class="text-2xl font-bold text-ink-900 dark:text-ink-50">{{ formatNum(stat.value) }}</div>
            <div class="text-xs text-ink-600 dark:text-ink-300 mt-1">{{ stat.label }}</div>
          </div>
        </div>

        <!-- Tabs -->
        <div class="flex gap-2 mb-6 flex-wrap" role="tablist" @keydown="handleTabKeydown">
          <button v-for="tab in adminTabs" :id="`admin-tab-${tab.id}`" :key="tab.id" @click="activeTab = tab.id"
            role="tab" :aria-selected="activeTab === tab.id" :aria-controls="`admin-panel-${tab.id}`"
            :class="['px-4 py-2 rounded-xl text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]',
              activeTab === tab.id ? 'bg-[var(--accent)] text-cream-50' : 'bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 text-ink-600 dark:text-ink-300 hover:bg-cream-100 dark:hover:bg-ash-700']">
            {{ tab.label }}
          </button>
        </div>

        <!-- TAB: API Usage -->
        <div v-if="activeTab === 'usage'" id="admin-panel-usage" role="tabpanel" aria-labelledby="admin-tab-usage" class="space-y-6">
          <!-- By Endpoint -->
          <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-6">
            <h3 class="font-semibold text-ink-700 dark:text-ink-200 mb-4">Usage by Endpoint</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-ink-500 dark:text-ink-300 border-b border-cream-300 dark:border-ash-700 text-xs uppercase">
                    <th class="pb-2 pr-4">Endpoint</th>
                    <th class="pb-2 pr-4 text-right">Calls</th>
                    <th class="pb-2 text-right">Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in usage.by_endpoint" :key="row.endpoint" class="border-b border-cream-300 dark:border-ash-700 last:border-0 hover:bg-cream-50 dark:bg-ash-850">
                    <td class="py-2 pr-4 font-mono text-xs bg-cream-50 dark:bg-ash-850 rounded px-2 my-1 w-fit">{{ row.endpoint }}</td>
                    <td class="py-2 pr-4 text-right text-ink-700 dark:text-ink-200">{{ formatNum(row.calls) }}</td>
                    <td class="py-2 text-right text-ink-700 dark:text-ink-200">{{ formatNum(row.tokens) }}</td>
                  </tr>
                  <tr v-if="!usage.by_endpoint?.length">
                    <td colspan="3" class="text-center py-6 text-ink-500 dark:text-ink-300">No API calls recorded yet</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Per User -->
          <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-6">
            <h3 class="font-semibold text-ink-700 dark:text-ink-200 mb-4">Usage per User</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-ink-500 dark:text-ink-300 border-b border-cream-300 dark:border-ash-700 text-xs uppercase">
                    <th class="pb-2 pr-4">User</th>
                    <th class="pb-2 pr-4 text-right">Calls</th>
                    <th class="pb-2 text-right">Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in usage.per_user" :key="row.email" class="border-b border-cream-300 dark:border-ash-700 last:border-0 hover:bg-cream-50 dark:bg-ash-850">
                    <td class="py-2 pr-4">
                      <div class="font-medium text-ink-900 dark:text-ink-50">{{ row.name }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-300">{{ row.email }}</div>
                    </td>
                    <td class="py-2 pr-4 text-right">{{ formatNum(row.calls) }}</td>
                    <td class="py-2 text-right">{{ formatNum(row.tokens) }}</td>
                  </tr>
                  <tr v-if="!usage.per_user?.length">
                    <td colspan="3" class="text-center py-6 text-ink-500 dark:text-ink-300">No usage records yet</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Daily Chart (simple bar) -->
          <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-6">
            <h3 class="font-semibold text-ink-700 dark:text-ink-200 mb-4">Daily Calls (last 30 days)</h3>
            <div v-if="usage.daily?.length" class="flex items-end gap-1 h-32">
              <div v-for="d in usage.daily" :key="d.date"
                class="flex-1 bg-[var(--accent)]/70 rounded-t min-w-[6px] hover:bg-[var(--accent)] transition-colors cursor-default relative group"
                :style="{ height: `${maxDailyCalls > 0 ? (d.calls / maxDailyCalls) * 100 : 0}%` }">
                <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 bg-ink-900 text-cream-50 text-xs rounded px-2 py-1 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                  {{ d.date }}: {{ d.calls }} calls
                </div>
              </div>
            </div>
            <p v-else class="text-center text-ink-500 dark:text-ink-300 text-sm py-8">No daily data yet</p>
          </div>
        </div>

        <!-- TAB: All Papers -->
        <div v-if="activeTab === 'papers'" id="admin-panel-papers" role="tabpanel" aria-labelledby="admin-tab-papers">
          <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="bg-cream-50 dark:bg-ash-850 border-b border-cream-300 dark:border-ash-700">
                  <tr class="text-left text-ink-500 dark:text-ink-300 text-xs uppercase">
                    <th class="px-4 py-3">Title</th>
                    <th class="px-4 py-3">User</th>
                    <th class="px-4 py-3 text-right">Images</th>
                    <th class="px-4 py-3 text-right">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in allPapers" :key="p.id" class="border-b border-cream-300 dark:border-ash-700 last:border-0 hover:bg-cream-50 dark:bg-ash-850">
                    <td class="px-4 py-3">
                      <div class="font-medium text-ink-900 dark:text-ink-50 max-w-xs truncate">{{ p.title || 'Untitled' }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-300 font-mono">{{ p.id }}</div>
                    </td>
                    <td class="px-4 py-3">
                      <div class="text-ink-700 dark:text-ink-200">{{ p.user_name }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-300">{{ p.user_email }}</div>
                    </td>
                    <td class="px-4 py-3 text-right text-ink-600 dark:text-ink-300">{{ p.image_count }}</td>
                    <td class="px-4 py-3 text-right text-ink-500 dark:text-ink-300 text-xs whitespace-nowrap">{{ formatDate(p.updated_at) }}</td>
                  </tr>
                  <tr v-if="!allPapers.length">
                    <td colspan="4" class="px-4 py-8 text-center text-ink-500 dark:text-ink-300">No papers yet</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- TAB: Users -->
        <div v-if="activeTab === 'users'" id="admin-panel-users" role="tabpanel" aria-labelledby="admin-tab-users">
          <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="bg-cream-50 dark:bg-ash-850 border-b border-cream-300 dark:border-ash-700">
                  <tr class="text-left text-ink-500 dark:text-ink-300 text-xs uppercase">
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
                  <tr v-for="u in allUsers" :key="u.id" class="border-b border-cream-300 dark:border-ash-700 last:border-0 hover:bg-cream-50 dark:bg-ash-850">
                    <td class="px-4 py-3">
                      <div class="font-medium text-ink-900 dark:text-ink-50">{{ u.name }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-300">{{ u.email }}</div>
                    </td>
                    <td class="px-4 py-3">
                      <span :class="['text-xs px-2 py-0.5 rounded-full font-medium',
                        u.role === 'admin' ? 'bg-cream-100 dark:bg-ash-700 text-ink-900 dark:text-ink-50' : 'bg-cream-100 text-ink-600 dark:text-ink-300']">
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
                        :class="['w-24 text-right tabular-nums px-2 py-1 border rounded text-xs focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]/30 focus:border-[var(--accent)]', quotaStatus[u.id] === 'ok' ? 'border-green-500' : quotaStatus[u.id] === 'err' ? 'border-red-500' : 'border-cream-300 dark:border-ash-700']"
                        title="Klik untuk edit kuota bulanan"
                      />
                      <span v-else class="text-xs text-ink-500 dark:text-ink-300">∞</span>
                    </td>
                    <td class="px-4 py-3 text-right">
                      <span class="tabular-nums text-xs"
                        :class="quotaPercent(u) >= 90 ? 'text-red-600 dark:text-red-400 font-semibold' : quotaPercent(u) >= 70 ? 'text-amber-600' : 'text-ink-600 dark:text-ink-300'">
                        {{ formatNum(u.token_used_month || 0) }}
                      </span>
                    </td>
                    <td class="px-4 py-3 text-right">{{ u.paper_count }}</td>
                    <td class="px-4 py-3 text-right text-xs text-ink-500 dark:text-ink-300">{{ formatDate(u.created_at) }}</td>
                    <td class="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                      <button v-if="u.role !== 'admin'" @click="confirmResetQuota(u)" class="text-xs text-[var(--accent)] hover:underline">Reset</button>
                      <button v-if="u.role !== 'admin'" @click="confirmPromote(u, 'admin')"
                        class="text-xs text-ink-900 dark:text-ink-50 underline hover:underline">Make Admin</button>
                      <button v-else @click="confirmPromote(u, 'user')"
                        class="text-xs text-ink-500 dark:text-ink-300 hover:underline">Demote</button>
                    </td>
                  </tr>
                  <tr v-if="!allUsers.length">
                    <td colspan="7" class="px-4 py-8 text-center text-ink-500 dark:text-ink-300">No users yet</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </main>

    <AppDialog v-if="promoteTarget" :open="!!promoteTarget" title="Confirm role change" @close="promoteTarget = null">
      <p class="text-sm text-ink-700 dark:text-ink-200">Change {{ promoteTarget.user.email }} role to {{ promoteTarget.role }}?</p>
      <template #actions>
        <button @click="promoteTarget = null" class="px-4 py-2 border border-cream-300 dark:border-ash-700 rounded-xl text-sm">Cancel</button>
        <button @click="promoteUser" class="px-4 py-2 bg-[var(--accent)] text-cream-50 rounded-xl text-sm">Confirm</button>
      </template>
    </AppDialog>

    <AppDialog v-if="resetTarget" :open="!!resetTarget" title="Reset quota?" @close="resetTarget = null">
      <p class="text-sm text-ink-700 dark:text-ink-200">Reset kuota {{ resetTarget.email }} ke 0 untuk bulan ini?</p>
      <template #actions>
        <button @click="resetTarget = null" class="px-4 py-2 border border-cream-300 dark:border-ash-700 rounded-xl text-sm">Cancel</button>
        <button @click="resetQuota" class="px-4 py-2 bg-red-600 text-white rounded-xl text-sm">Reset</button>
      </template>
    </AppDialog>

    <Teleport to="body"><div v-if="toastMsg" class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] px-4 py-2.5 rounded-lg shadow-lg text-white text-sm bg-ink-900 dark:bg-cream-200 dark:text-ash-900">{{ toastMsg }}</div></Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import api from '../api/index.js'
import AppHeader from '../components/AppHeader.vue'
import AppDialog from '../components/AppDialog.vue'

const loading = ref(true)
const activeTab = ref('usage')
const usage = ref({ total: {}, by_endpoint: [], daily: [], per_user: [] })
const allPapers = ref([])
const allUsers = ref([])
const stats = ref({})
const promoteTarget = ref(null)
const resetTarget = ref(null)
const toastMsg = ref('')
const _quotaTimers = []
const quotaStatus = ref({})
let toastTimer = null

function showToast(msg) {
  toastMsg.value = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMsg.value = '' }, 2500)
}

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

function confirmPromote(user, role) {
  promoteTarget.value = { user, role }
}

async function promoteUser() {
  if (!promoteTarget.value) return
  const { user, role } = promoteTarget.value
  try {
    await api.post(`/api/admin/users/${user.id}/promote`, { role })
    user.role = role
    showToast('Role updated')
  } catch (e) {
    showToast('Role update failed')
    console.error('Promote failed', e)
  } finally {
    promoteTarget.value = null
  }
}

function handleTabKeydown(e) {
  if (!['ArrowRight', 'ArrowLeft'].includes(e.key)) return
  e.preventDefault()
  const i = adminTabs.findIndex(t => t.id === activeTab.value)
  const next = e.key === 'ArrowRight' ? (i + 1) % adminTabs.length : (i - 1 + adminTabs.length) % adminTabs.length
  activeTab.value = adminTabs[next].id
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
    quotaStatus.value[user.id] = 'ok'
  } catch (e) {
    quotaStatus.value[user.id] = 'err'
    console.error('saveQuota failed', e)
  } finally {
    _quotaTimers.push(setTimeout(() => { delete quotaStatus.value[user.id] }, 1000))
  }
}

function confirmResetQuota(user) {
  resetTarget.value = user
}

async function resetQuota() {
  if (!resetTarget.value) return
  const user = resetTarget.value
  try {
    const res = await api.post(`/api/admin/users/${user.id}/reset-quota`)
    if (res?.data?.user) Object.assign(user, res.data.user)
    showToast('Quota reset')
  } catch (e) {
    showToast('Quota reset failed')
    console.error('resetQuota failed', e)
  } finally {
    resetTarget.value = null
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
    const results = await Promise.allSettled([
      api.get('/api/admin/usage'),
      api.get('/api/admin/papers'),
      api.get('/api/admin/users'),
      api.get('/api/admin/stats'),
    ])
    const [usageRes, papersRes, usersRes, statsRes] = results.map((r) =>
      r.status === 'fulfilled' ? r.value : { data: null }
    )
    if (usageRes?.data) usage.value = usageRes.data
    if (papersRes?.data?.papers) allPapers.value = papersRes.data.papers
    if (usersRes?.data?.users) allUsers.value = usersRes.data.users
    if (statsRes?.data) stats.value = statsRes.data
  } catch (e) {
    console.error('Failed to load admin data', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAll()
  // auto-refresh tiap 30 detik agar admin pantau usage real-time.
  if (_refreshTimer) clearInterval(_refreshTimer)
  _refreshTimer = setInterval(loadAll, 30_000)
})

onBeforeUnmount(() => { if (_refreshTimer) clearInterval(_refreshTimer); _quotaTimers.forEach(clearTimeout) })
</script>
