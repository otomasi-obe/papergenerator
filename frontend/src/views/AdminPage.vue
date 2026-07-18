<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <AppHeader />

    <main class="max-w-6xl mx-auto px-4 py-8">
      <div class="mb-8 flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-ink-900 dark:text-ink-50">Admin Dashboard</h1>
          <p class="text-ink-600 dark:text-ink-300 text-sm mt-1">Monitor usage, users, and all papers</p>
        </div>
        <router-link to="/dashboard"
          class="flex items-center gap-1.5 px-4 py-2 min-h-[44px] rounded-xl bg-cream-100 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 text-sm font-medium text-ink-700 dark:text-ink-100 hover:bg-cream-200 dark:hover:bg-ash-700 hover:-translate-y-0.5 hover:shadow-md cursor-pointer transition-all duration-150 active:scale-95 active:translate-y-0 focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]">
          <span aria-hidden="true" class="transition-transform duration-150 group-hover:-translate-x-0.5">←</span> Back to Dashboard
        </router-link>
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
            class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm p-5 text-center">
            <div class="text-2xl mb-1">{{ stat.icon }}</div>
            <div class="text-2xl font-bold text-ink-900 dark:text-ink-50">{{ formatNum(stat.value) }}</div>
            <div class="text-xs text-ink-600 dark:text-ink-300 mt-1">{{ stat.label }}</div>
          </div>
        </div>

        <!-- Tabs + Search -->
        <div class="flex gap-2 mb-6 flex-wrap items-center justify-between">
          <div class="flex gap-2 flex-wrap" role="tablist" @keydown="handleTabKeydown">
            <button v-for="tab in adminTabs" :id="`admin-tab-${tab.id}`" :key="tab.id" @click="activeTab = tab.id"
              role="tab" :aria-selected="activeTab === tab.id" :aria-controls="`admin-panel-${tab.id}`"
              :class="['px-4 py-2 rounded-xl text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]',
                activeTab === tab.id ? 'bg-[var(--accent)] text-cream-50' : 'bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 text-ink-600 dark:text-ink-300 hover:bg-cream-100 dark:hover:bg-ash-700']">
              {{ tab.label }}
            </button>
          </div>
          <div class="relative">
            <input
              v-if="activeTab === 'users'"
              v-model="userSearch"
              type="text"
              placeholder="Search user..."
              class="w-56 px-4 py-2 pr-9 min-h-[40px] rounded-xl bg-white dark:bg-ash-800 border border-cream-300 dark:border-ash-700 text-sm text-ink-800 dark:text-ink-100 placeholder:text-ink-400 dark:placeholder:text-ink-500 focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]/30 focus:border-[var(--accent)] transition"
            />
            <svg v-if="activeTab === 'users'" class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400 dark:text-ink-500 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
            </svg>
            <input
              v-if="activeTab === 'papers'"
              v-model="paperSearch"
              type="text"
              placeholder="Search paper..."
              class="w-56 px-4 py-2 pr-9 min-h-[40px] rounded-xl bg-white dark:bg-ash-800 border border-cream-300 dark:border-ash-700 text-sm text-ink-800 dark:text-ink-100 placeholder:text-ink-400 dark:placeholder:text-ink-500 focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]/30 focus:border-[var(--accent)] transition"
            />
            <svg v-if="activeTab === 'papers'" class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400 dark:text-ink-500 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
            </svg>
            <input
              v-if="activeTab === 'deletelog'"
              v-model="deleteLogSearch"
              type="text"
              placeholder="Search paper id / title / email..."
              class="w-72 px-4 py-2 pr-9 min-h-[40px] rounded-xl bg-white dark:bg-ash-800 border border-cream-300 dark:border-ash-700 text-sm text-ink-800 dark:text-ink-100 placeholder:text-ink-400 dark:placeholder:text-ink-500 focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]/30 focus:border-[var(--accent)] transition"
            />
            <svg v-if="activeTab === 'deletelog'" class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400 dark:text-ink-500 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
            </svg>
          </div>
        </div>

        <!-- TAB: API Usage -->
        <div v-if="activeTab === 'usage'" id="admin-panel-usage" role="tabpanel" aria-labelledby="admin-tab-usage" class="space-y-6">
          <!-- By Endpoint -->
          <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm p-6">
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
                  <tr v-for="row in usage.by_endpoint" :key="row.endpoint" class="border-b border-cream-300 dark:border-ash-700 last:border-0 hover:bg-cream-100 dark:bg-ash-850">
                    <td class="py-2 pr-4 font-mono text-xs">{{ row.endpoint }}</td>
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
          <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm p-6">
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
                  <tr v-for="row in usage.per_user" :key="row.email" class="border-b border-cream-300 dark:border-ash-700 last:border-0 hover:bg-cream-100 dark:bg-ash-850">
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
          <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm p-6">
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
          <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
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
                  <tr v-for="p in pagedPapers" :key="p.id" class="border-b border-cream-300 dark:border-ash-700 last:border-0 hover:bg-cream-100 dark:bg-ash-850">
                    <td class="px-4 py-3">
                      <div class="font-medium text-ink-900 dark:text-ink-50 max-w-xs truncate">{{ p.title || 'Untitled' }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-300 font-mono">{{ p.id }}</div>
                    </td>
                    <td class="px-4 py-3">
                      <div class="text-ink-700 dark:text-ink-200">{{ p.user_name }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-300">{{ p.user_email }}</div>
                    </td>
                    <td class="px-4 py-3 text-right text-ink-600 dark:text-ink-300">{{ p.image_count }}</td>
                    <td class="px-4 py-3 text-right text-ink-500 dark:text-ink-300 text-xs whitespace-nowrap">
                      <span class="text-ink-600 dark:text-ink-300" title="{{ formatDate(p.updated_at).full }}">{{ formatDate(p.updated_at).relative }}</span>
                    </td>
                  </tr>
                  <tr v-if="!allPapers.length">
                    <td colspan="4" class="px-4 py-8 text-center text-ink-500 dark:text-ink-300">No papers yet</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="filteredPapers.length > PAGE_SIZE" class="flex items-center justify-between px-4 py-3 border-t border-cream-300 dark:border-ash-700 text-sm">
              <span class="text-ink-500 dark:text-ink-300">Page {{ paperPage }} / {{ totalPaperPages }} ({{ filteredPapers.length }} papers)</span>
              <div class="space-x-2">
                <button @click="paperPage = Math.max(1, paperPage - 1)" :disabled="paperPage <= 1"
                  class="px-3 py-1.5 rounded-lg border border-cream-300 dark:border-ash-700 text-xs disabled:opacity-40 disabled:cursor-not-allowed hover:bg-cream-100 dark:hover:bg-ash-700">← Prev</button>
                <button @click="paperPage = Math.min(totalPaperPages, paperPage + 1)" :disabled="paperPage >= totalPaperPages"
                  class="px-3 py-1.5 rounded-lg border border-cream-300 dark:border-ash-700 text-xs disabled:opacity-40 disabled:cursor-not-allowed hover:bg-cream-100 dark:hover:bg-ash-700">Next →</button>
              </div>
            </div>
          </div>
        </div>

        <!-- TAB: Users -->
        <div v-if="activeTab === 'users'" id="admin-panel-users" role="tabpanel" aria-labelledby="admin-tab-users">
          <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="bg-cream-50 dark:bg-ash-850 border-b border-cream-300 dark:border-ash-700">
                  <tr class="text-left text-ink-500 dark:text-ink-300 text-xs uppercase">
                    <th class="px-4 py-3">User</th>
                    <th class="px-4 py-3">Role &amp; Tier</th>
                    <th class="px-4 py-3 text-center">Status</th>
                    <th class="px-4 py-3 text-right">Quota</th>
                    <th class="px-4 py-3 text-right">Used</th>
                    <th class="px-4 py-3 text-right">Papers</th>
                    <th class="px-4 py-3 text-right">Joined</th>
                    <th class="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="u in pagedUsers" :key="u.id" class="border-b border-cream-300 dark:border-ash-700 last:border-0 hover:bg-cream-100 dark:bg-ash-850">
                    <td class="px-4 py-3">
                      <div class="font-medium text-ink-900 dark:text-ink-50">{{ u.name }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-300">{{ u.email }}</div>
                    </td>
                    <td class="px-4 py-3">
                      <div class="flex items-center gap-1.5">
                        <span :class="['text-xs px-2 py-0.5 rounded-full font-medium',
                          u.role === 'admin' ? 'bg-cream-100 dark:bg-ash-700 text-ink-900 dark:text-ink-50' : 'bg-cream-100 text-ink-600 dark:text-ink-300']">
                          {{ u.role }}
                        </span>
                        <span v-if="u.badge" :class="['inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium',
                          badgeStyle(u.badge)]">
                          <span class="w-1.5 h-1.5 rounded-full" :class="badgeDot(u.badge)"></span>
                          {{ u.badge }}
                        </span>
                      </div>
                    </td>
                    <!-- Status online dot + label -->
                    <td class="px-4 py-3 text-center">
                      <div class="flex flex-col items-center gap-0.5">
                        <span
                          :class="['inline-block w-2.5 h-2.5 rounded-full', statusDot(u.last_login).cls]"
                        ></span>
                        <span class="text-[10px] text-ink-500 dark:text-ink-400 whitespace-nowrap">
                          {{ statusDot(u.last_login).label }}
                        </span>
                      </div>
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
                  <tr v-if="!filteredUsers.length">
                    <td colspan="7" class="px-4 py-8 text-center text-ink-500 dark:text-ink-300">No users found</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="filteredUsers.length > PAGE_SIZE" class="flex items-center justify-between px-4 py-3 border-t border-cream-300 dark:border-ash-700 text-sm">
              <span class="text-ink-500 dark:text-ink-300">Page {{ userPage }} / {{ totalUserPages }} ({{ filteredUsers.length }} users)</span>
              <div class="space-x-2">
                <button @click="userPage = Math.max(1, userPage - 1)" :disabled="userPage <= 1"
                  class="px-3 py-1.5 rounded-lg border border-cream-300 dark:border-ash-700 text-xs disabled:opacity-40 disabled:cursor-not-allowed hover:bg-cream-100 dark:hover:bg-ash-700">← Prev</button>
                <button @click="userPage = Math.min(totalUserPages, userPage + 1)" :disabled="userPage >= totalUserPages"
                  class="px-3 py-1.5 rounded-lg border border-cream-300 dark:border-ash-700 text-xs disabled:opacity-40 disabled:cursor-not-allowed hover:bg-cream-100 dark:hover:bg-ash-700">Next →</button>
              </div>
            </div>
          </div>
        </div>
        <!-- TAB: Delete Log -->
        <div v-if="activeTab === 'deletelog'" id="admin-panel-deletelog" role="tabpanel" aria-labelledby="admin-tab-deletelog">
          <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="bg-cream-50 dark:bg-ash-850 border-b border-cream-300 dark:border-ash-700">
                  <tr class="text-left text-ink-500 dark:text-ink-300 text-xs uppercase">
                    <th class="px-4 py-3">Deleted At</th>
                    <th class="px-4 py-3">Paper</th>
                    <th class="px-4 py-3">Deleted By</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="l in filteredDeleteLogs" :key="l.id" class="border-b border-cream-300 dark:border-ash-700 last:border-0 hover:bg-cream-100 dark:bg-ash-850">
                    <td class="px-4 py-3 text-xs text-ink-600 dark:text-ink-300 whitespace-nowrap" :title="formatDate(l.deleted_at).full">
                      {{ formatDate(l.deleted_at).relative }}
                    </td>
                    <td class="px-4 py-3">
                      <div class="font-medium text-ink-900 dark:text-ink-50 max-w-xs truncate">{{ l.paper_title || 'Untitled' }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-300 font-mono">{{ l.paper_id }}</div>
                    </td>
                    <td class="px-4 py-3">
                      <div class="text-ink-700 dark:text-ink-200">{{ l.user_name || '—' }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-300">{{ l.user_email || '—' }}</div>
                    </td>
                  </tr>
                  <tr v-if="!filteredDeleteLogs.length">
                    <td colspan="3" class="px-4 py-8 text-center text-ink-500 dark:text-ink-300">No delete logs yet</td>
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
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import api from '../api/index.js'
import AppHeader from '../components/AppHeader.vue'
import AppDialog from '../components/AppDialog.vue'

const loading = ref(true)
const activeTab = ref('usage')
const usage = ref({ total: {}, by_endpoint: [], daily: [], per_user: [] })
const allPapers = ref([])
const allUsers = ref([])
const deleteLogs = ref([])
const stats = ref({})
const promoteTarget = ref(null)
const resetTarget = ref(null)
const toastMsg = ref('')
const _quotaTimers = []
const quotaStatus = ref({})
const userSearch = ref('')
const paperSearch = ref('')
const deleteLogSearch = ref('')
const userPage = ref(1)
const paperPage = ref(1)
const PAGE_SIZE = 50
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
  { id: 'deletelog', label: '🗑️ Delete Log' },
]

const statsCards = computed(() => [
  { icon: '👤', label: 'Total Users', value: stats.value.total_users || 0 },
  { icon: '📄', label: 'Total Papers', value: stats.value.total_papers || 0 },
  { icon: '🖼️', label: 'Total Images', value: stats.value.total_images || 0 },
  { icon: '⚡', label: 'API Calls', value: stats.value.total_api_calls || 0 },
  { icon: '🔢', label: 'Tokens Used', value: stats.value.total_tokens || 0 },
])

const maxDailyCalls = computed(() => Math.max(...(usage.value.daily || []).map(d => d.calls), 1))

const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase()
  if (!q) return allUsers.value
  return allUsers.value.filter(u =>
    (u.name || '').toLowerCase().includes(q) ||
    (u.email || '').toLowerCase().includes(q)
  )
})

const pagedUsers = computed(() => {
  const start = (userPage.value - 1) * PAGE_SIZE
  return filteredUsers.value.slice(start, start + PAGE_SIZE)
})

const totalUserPages = computed(() => Math.max(1, Math.ceil(filteredUsers.value.length / PAGE_SIZE)))

const filteredPapers = computed(() => {
  const q = paperSearch.value.trim().toLowerCase()
  if (!q) return allPapers.value
  return allPapers.value.filter(p =>
    (p.title || '').toLowerCase().includes(q) ||
    (p.id || '').toLowerCase().includes(q)
  )
})

const pagedPapers = computed(() => {
  const start = (paperPage.value - 1) * PAGE_SIZE
  return filteredPapers.value.slice(start, start + PAGE_SIZE)
})

const totalPaperPages = computed(() => Math.max(1, Math.ceil(filteredPapers.value.length / PAGE_SIZE)))

const filteredDeleteLogs = computed(() => {
  const q = deleteLogSearch.value.trim().toLowerCase()
  if (!q) return deleteLogs.value
  return deleteLogs.value.filter(l =>
    (l.paper_id || '').toLowerCase().includes(q) ||
    (l.paper_title || '').toLowerCase().includes(q) ||
    (l.user_email || '').toLowerCase().includes(q) ||
    (l.user_name || '').toLowerCase().includes(q)
  )
})

const BADGE_STYLES = {
  trial:   'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300',
  starter: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300',
  pro:     'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300',
  elite:   'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300',
}
const BADGE_DOTS = {
  trial:   'bg-slate-500',
  starter: 'bg-amber-500',
  pro:     'bg-blue-500',
  elite:   'bg-emerald-500',
}
function badgeStyle(b) { return BADGE_STYLES[b] || BADGE_STYLES.trial }
function badgeDot(b)   { return BADGE_DOTS[b] || BADGE_DOTS.trial }

// Online status: green Active < 5min, amber last Xm/H lalu, gray offline
function statusDot(iso) {
  if (!iso) return { cls: 'bg-ash-400 dark:bg-ash-600', label: 'Offline' }
  const diffSec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diffSec < 300) return { cls: 'bg-emerald-400', label: 'Active' }
  if (diffSec < 3600) return { cls: 'bg-amber-400', label: `last ${Math.floor(diffSec / 60)}m lalu` }
  if (diffSec < 86400) return { cls: 'bg-amber-400', label: `last ${Math.floor(diffSec / 3600)}h lalu` }
  return { cls: 'bg-ash-400 dark:bg-ash-600', label: 'Offline' }
}

watch(userSearch, () => { userPage.value = 1 })
watch(paperSearch, () => { paperPage.value = 1 })

function formatNum(n) {
  if (!n) return '0'
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

function formatDate(iso) {
  if (!iso) return { relative: '', full: '' }
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now - d
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  let relative = ''
  if (diffSec < 60) relative = 'now'
  else if (diffMin < 60) relative = `${diffMin}m ago`
  else if (diffHour < 24) relative = `${diffHour}h ago`
  else if (diffDay < 7) relative = `${diffDay}d ago`
  else relative = d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })

  const full = d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) + ' ' + d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

  return { relative, full }
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

async function loadAll(opts = {}) {
  const { silent = false } = opts
  if (!silent) loading.value = true
  try {
    const results = await Promise.allSettled([
      api.get('/api/admin/usage'),
      api.get('/api/admin/papers'),
      api.get('/api/admin/users?limit=1000'),
      api.get('/api/admin/stats'),
      api.get('/api/admin/delete-log?limit=500'),
    ])
    const [usageRes, papersRes, usersRes, statsRes, deleteLogRes] = results.map((r) =>
      r.status === 'fulfilled' ? r.value : { data: null }
    )
    if (usageRes?.data) usage.value = usageRes.data
    if (papersRes?.data?.papers) allPapers.value = papersRes.data.papers
    if (usersRes?.data?.users) allUsers.value = usersRes.data.users
    if (statsRes?.data) stats.value = statsRes.data
    if (deleteLogRes?.data?.logs) deleteLogs.value = deleteLogRes.data.logs
  } catch (e) {
    console.error('Failed to load admin data', e)
  } finally {
    if (!silent) loading.value = false
  }
}

onMounted(() => {
  loadAll()
  // auto-refresh tiap 30 detik, silent (tanpa loading blink)
  if (_refreshTimer) clearInterval(_refreshTimer)
  _refreshTimer = setInterval(() => loadAll({ silent: true }), 30_000)
})

onBeforeUnmount(() => { if (_refreshTimer) clearInterval(_refreshTimer); _quotaTimers.forEach(clearTimeout) })
</script>
