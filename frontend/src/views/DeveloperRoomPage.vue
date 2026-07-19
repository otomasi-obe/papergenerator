<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <AppHeader />

    <main class="max-w-7xl mx-auto px-4 py-8">
      <!-- Header -->
      <div class="mb-8 flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-ink-900 dark:text-ink-50">Developer Room</h1>
          <p class="text-ink-600 dark:text-ink-300 text-sm mt-1">Internal debugging & system monitoring (restricted access)</p>
        </div>
        <router-link to="/dashboard"
          class="flex items-center gap-1.5 px-4 py-2 min-h-[44px] rounded-xl bg-cream-100 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 text-sm font-medium text-ink-700 dark:text-ink-100 hover:bg-cream-200 dark:hover:bg-ash-700 hover:-translate-y-0.5 hover:shadow-md cursor-pointer transition-all duration-150 active:scale-95 active:translate-y-0 focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]">
          <span aria-hidden="true" class="transition-transform duration-150 group-hover:-translate-x-0.5">←</span> Back to Dashboard
        </router-link>
      </div>

      <!-- Stats Cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div v-for="stat in statsCards" :key="stat.label" class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm p-5 text-center">
          <div class="text-2xl mb-1">{{ stat.icon }}</div>
          <div class="text-2xl font-bold text-ink-900 dark:text-ink-50">{{ formatNum(stat.value) }}</div>
          <div class="text-xs text-ink-600 dark:text-ink-300 mt-1">{{ stat.label }}</div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="flex gap-2 mb-6 flex-wrap" role="tablist">
        <button v-for="tab in devTabs" :id="`dev-tab-${tab.id}`" :key="tab.id" @click="activeTab = tab.id"
          role="tab" :aria-selected="activeTab === tab.id" :aria-controls="`dev-panel-${tab.id}`"
          :class="['px-4 py-2 rounded-xl text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]',
            activeTab === tab.id ? 'bg-[var(--accent)] text-cream-50' : 'bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 text-ink-600 dark:text-ink-300 hover:bg-cream-100 dark:hover:bg-ash-700']">
          {{ tab.icon }} {{ tab.label }}
        </button>
      </div>

      <!-- Tab Panels -->
      <!-- System Tab -->
      <div v-if="activeTab === 'system'" id="dev-panel-system" role="tabpanel" aria-labelledby="dev-tab-system" class="space-y-6">
        <!-- Version Info -->
        <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-850">
            <h2 class="font-semibold text-ink-900 dark:text-ink-50">Version & Build</h2>
          </div>
          <div class="p-5 space-y-3 text-sm" v-if="versionInfo">
            <div class="flex justify-between">
              <span class="text-ink-600 dark:text-ink-300">Frontend Version</span>
              <span class="font-mono text-ink-900 dark:text-ink-50">{{ versionInfo.version }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-ink-600 dark:text-ink-300">Build Date</span>
              <span class="font-mono text-ink-900 dark:text-ink-50">{{ versionInfo.buildDate }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-ink-600 dark:text-ink-300">Git Commit</span>
              <span class="font-mono text-ink-900 dark:text-ink-50">{{ versionInfo.commit }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-ink-600 dark:text-ink-300">Environment</span>
              <span class="font-mono text-ink-900 dark:text-ink-50">{{ versionInfo.env }}</span>
            </div>
          </div>
        </div>

        <!-- System Health -->
        <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-850">
            <h2 class="font-semibold text-ink-900 dark:text-ink-50">System Health</h2>
          </div>
          <div class="p-5 space-y-4" v-if="health">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div v-for="h in health.services" :key="h.name" class="p-4 rounded-xl" :class="h.status === 'ok' ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'">
                <div class="font-medium text-ink-900 dark:text-ink-50">{{ h.name }}</div>
                <div class="text-sm" :class="h.status === 'ok' ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'">
                  {{ h.status === 'ok' ? '✓ Healthy' : '✗ ' + (h.error || 'Unhealthy') }}
                </div>
                <div v-if="h.latency" class="text-xs text-ink-500 dark:text-ink-400 mt-1">{{ h.latency }}ms</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Jobs / Queue Tab -->
      <div v-if="activeTab === 'jobs'" id="dev-panel-jobs" role="tabpanel" aria-labelledby="dev-tab-jobs" class="space-y-6">
        <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-850 flex items-center justify-between">
            <h2 class="font-semibold text-ink-900 dark:text-ink-50">Background Jobs (RQ)</h2>
            <button @click="loadJobs" :disabled="loadingJobs" class="px-3 py-1.5 text-xs rounded-lg bg-[var(--accent)] text-cream-50 hover:opacity-90 disabled:opacity-50">Refresh</button>
          </div>
          <div class="p-5" v-if="jobs.length > 0">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="text-left text-ink-500 dark:text-ink-300 text-xs uppercase">
                  <tr>
                    <th class="px-4 py-3">Job ID</th>
                    <th class="px-4 py-3">Paper ID</th>
                    <th class="px-4 py-3">Kind</th>
                    <th class="px-4 py-3">Status</th>
                    <th class="px-4 py-3">Progress</th>
                    <th class="px-4 py-3">Stage</th>
                    <th class="px-4 py-3">Started</th>
                    <th class="px-4 py-3">Updated</th>
                    <th class="px-4 py-3">Error</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-cream-200 dark:divide-ash-700">
                  <tr v-for="job in jobs" :key="job.id" class="hover:bg-cream-50 dark:hover:bg-ash-700/50">
                    <td class="px-4 py-3 font-mono text-xs text-ink-700 dark:text-ink-200">{{ job.id.slice(0, 12) }}…</td>
                    <td class="px-4 py-3 font-mono text-xs text-ink-700 dark:text-ink-200">{{ job.paper_id || '—' }}</td>
                    <td class="px-4 py-3"><span class="px-2 py-0.5 rounded text-xs bg-cream-100 dark:bg-ash-700 text-ink-700 dark:text-ink-200">{{ job.kind }}</span></td>
                    <td class="px-4 py-3">
                      <span class="px-2 py-0.5 rounded text-xs" :class="jobStatusClass(job.status)">
                        {{ job.status }}
                      </span>
                    </td>
                    <td class="px-4 py-3">
                      <div class="w-24 h-2 rounded-full bg-cream-200 dark:bg-ash-700 overflow-hidden">
                        <div class="h-full transition-all duration-300 bg-blue-500" :style="{ width: (job.progress || 0) + '%' }"></div>
                      </div>
                      <span class="text-xs text-ink-500 dark:text-ink-400 ml-1">{{ job.progress || 0 }}%</span>
                    </td>
                    <td class="px-4 py-3 text-ink-600 dark:text-ink-300">{{ job.stage || '—' }}</td>
                    <td class="px-4 py-3 text-ink-600 dark:text-ink-300">{{ formatDate(job.started_at) }}</td>
                    <td class="px-4 py-3 text-ink-600 dark:text-ink-300">{{ formatDate(job.updated_at) }}</td>
                    <td class="px-4 py-3 text-red-600 dark:text-red-400 max-w-xs truncate" :title="job.error">{{ job.error || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <!-- Pagination -->
            <div v-if="jobsTotalPages > 1" class="flex items-center justify-between gap-2 mt-4 flex-wrap">
              <button @click="jobsPage = 1" :disabled="jobsPage <= 1" class="px-2 py-1 rounded text-[10px] font-medium border transition-colors" :class="jobsPage === 1 ? 'bg-navy-700 text-cream-50 border-navy-700' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700'">
                ««
              </button>
              <button @click="jobsPage--" :disabled="jobsPage <= 1" class="px-2 py-1 rounded text-[10px] font-medium border transition-colors" :class="jobsPage === 1 ? 'bg-navy-700 text-cream-50 border-navy-700' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700'">
                «
              </button>
              <span class="text-xs text-ink-600 dark:text-ink-300">Page {{ jobsPage }} of {{ jobsTotalPages }}</span>
              <button @click="jobsPage++" :disabled="jobsPage >= jobsTotalPages" class="px-2 py-1 rounded text-[10px] font-medium border transition-colors" :class="jobsPage === jobsTotalPages ? 'bg-navy-700 text-cream-50 border-navy-700' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700'">
                »
              </button>
              <button @click="jobsPage = jobsTotalPages" :disabled="jobsPage >= jobsTotalPages" class="px-2 py-1 rounded text-[10px] font-medium border transition-colors" :class="jobsPage === jobsTotalPages ? 'bg-navy-700 text-cream-50 border-navy-700' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700'">
                »»
              </button>
            </div>
          </div>
          <div v-else class="p-5 text-center text-ink-500 dark:text-ink-400">No jobs found</div>
        </div>
      </div>

      <!-- Image Jobs Tab -->
      <div v-if="activeTab === 'image-jobs'" id="dev-panel-image-jobs" role="tabpanel" aria-labelledby="dev-tab-image-jobs" class="space-y-6">
        <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-850 flex items-center justify-between">
            <h2 class="font-semibold text-ink-900 dark:text-ink-50">Image Generation Jobs</h2>
            <div class="flex items-center gap-2">
              <span class="text-xs text-ink-500 dark:text-ink-400" v-if="!loadingImageJobs">Auto-refresh 3s</span>
              <button @click="loadImageJobs" :disabled="loadingImageJobs" class="px-3 py-1.5 text-xs rounded-lg bg-[var(--accent)] text-cream-50 hover:opacity-90 disabled:opacity-50">Refresh</button>
            </div>
          </div>
          <div class="p-5" v-if="imageJobs.length > 0">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="text-left text-ink-500 dark:text-ink-300 text-xs uppercase">
                  <tr>
                    <th class="px-4 py-3">Job ID</th>
                    <th class="px-4 py-3">Paper ID</th>
                    <th class="px-4 py-3">Model</th>
                    <th class="px-4 py-3">Status</th>
                    <th class="px-4 py-3">Queue Pos</th>
                    <th class="px-4 py-3">Progress</th>
                    <th class="px-4 py-3">Created</th>
                    <th class="px-4 py-3">Started</th>
                    <th class="px-4 py-3">Finished</th>
                    <th class="px-4 py-3">Prompt</th>
                    <th class="px-4 py-3">Error</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-cream-200 dark:divide-ash-700">
                  <tr v-for="job in imageJobs" :key="job.id" class="hover:bg-cream-50 dark:hover:bg-ash-700/50">
                    <td class="px-4 py-3 font-mono text-xs text-ink-700 dark:text-ink-200">{{ job.id.slice(0, 12) }}…</td>
                    <td class="px-4 py-3 font-mono text-xs text-ink-700 dark:text-ink-200">{{ job.paper_id }}</td>
                    <td class="px-4 py-3">
                      <span class="px-2 py-0.5 rounded text-xs bg-cream-100 dark:bg-ash-700 text-ink-700 dark:text-ink-200">{{ job.worker || '—' }}</span>
                    </td>
                    <td class="px-4 py-3">
                      <span class="px-2 py-0.5 rounded text-xs" :class="imageJobStatusClass(job.status)">
                        {{ job.status }}
                      </span>
                    </td>
                    <td class="px-4 py-3 text-ink-600 dark:text-ink-300">{{ job.queue_position >= 0 ? job.queue_position : '—' }}</td>
                    <td class="px-4 py-3">
                      <div class="w-32 h-2 rounded-full bg-cream-200 dark:bg-ash-700 overflow-hidden">
                        <div class="h-full transition-all duration-300" :style="{ width: imageJobProgress(job) + '%' }" :class="job.status === 'done' ? 'bg-green-500' : job.status === 'running' ? 'bg-blue-500' : job.status === 'queued' ? 'bg-amber-500' : job.status === 'error' ? 'bg-red-500' : 'bg-gray-400'"></div>
                      </div>
                      <span class="text-xs text-ink-500 dark:text-ink-400 ml-1">{{ imageJobProgress(job) }}%</span>
                    </td>
                    <td class="px-4 py-3 text-ink-600 dark:text-ink-300">{{ formatDate(job.created_at) }}</td>
                    <td class="px-4 py-3 text-ink-600 dark:text-ink-300">{{ formatDate(job.started_at) }}</td>
                    <td class="px-4 py-3 text-ink-600 dark:text-ink-300">{{ formatDate(job.finished_at) }}</td>
                    <td class="px-4 py-3 text-ink-500 dark:text-ink-400 max-w-xs truncate" :title="job.prompt">{{ job.prompt }}</td>
                    <td class="px-4 py-3 text-red-600 dark:text-red-400 max-w-xs truncate" :title="job.error">{{ job.error || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <!-- Pagination -->
            <div v-if="imageJobsTotalPages > 1" class="flex items-center justify-between gap-2 mt-4 flex-wrap">
              <button @click="imageJobsPage = 1" :disabled="imageJobsPage <= 1" class="px-2 py-1 rounded text-[10px] font-medium border transition-colors" :class="imageJobsPage === 1 ? 'bg-navy-700 text-cream-50 border-navy-700' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700'">
                ««
              </button>
              <button @click="imageJobsPage--" :disabled="imageJobsPage <= 1" class="px-2 py-1 rounded text-[10px] font-medium border transition-colors" :class="imageJobsPage === 1 ? 'bg-navy-700 text-cream-50 border-navy-700' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700'">
                «
              </button>
              <span class="text-xs text-ink-600 dark:text-ink-300">Page {{ imageJobsPage }} of {{ imageJobsTotalPages }}</span>
              <button @click="imageJobsPage++" :disabled="imageJobsPage >= imageJobsTotalPages" class="px-2 py-1 rounded text-[10px] font-medium border transition-colors" :class="imageJobsPage === imageJobsTotalPages ? 'bg-navy-700 text-cream-50 border-navy-700' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700'">
                »
              </button>
              <button @click="imageJobsPage = imageJobsTotalPages" :disabled="imageJobsPage >= imageJobsTotalPages" class="px-2 py-1 rounded text-[10px] font-medium border transition-colors" :class="imageJobsPage === imageJobsTotalPages ? 'bg-navy-700 text-cream-50 border-navy-700' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700'">
                »»
              </button>
            </div>
          </div>
          <div v-else class="p-5 text-center text-ink-500 dark:text-ink-400">No image jobs found</div>
        </div>
      </div>

      <!-- Database Tab -->
      <div v-if="activeTab === 'db'" id="dev-panel-db" role="tabpanel" aria-labelledby="dev-tab-db" class="space-y-6">
        <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-850 flex items-center justify-between">
            <h2 class="font-semibold text-ink-900 dark:text-ink-50">Database Stats</h2>
            <button @click="loadDbStats" :disabled="loadingDb" class="px-3 py-1.5 text-xs rounded-lg bg-[var(--accent)] text-cream-50 hover:opacity-90 disabled:opacity-50">Refresh</button>
          </div>
          <div class="p-5 space-y-4" v-if="dbStats">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div v-for="stat in dbStats.tables" :key="stat.name" class="p-4 rounded-xl bg-cream-50 dark:bg-ash-700/50">
                <div class="font-medium text-ink-900 dark:text-ink-50">{{ stat.name }}</div>
                <div class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-1">{{ formatNum(stat.count) }}</div>
                <div class="text-xs text-ink-500 dark:text-ink-400">rows</div>
              </div>
            </div>
            <div class="pt-4 border-t border-cream-200 dark:border-ash-700">
              <div class="font-medium text-ink-900 dark:text-ink-50 mb-2">Table Sizes</div>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead class="text-left text-ink-500 dark:text-ink-300 text-xs uppercase">
                    <tr>
                      <th class="px-4 py-2">Table</th>
                      <th class="px-4 py-2">Size</th>
                      <th class="px-4 py-2">Rows</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-cream-200 dark:divide-ash-700">
                    <tr v-for="stat in dbStats.tables" :key="stat.name" class="hover:bg-cream-50 dark:hover:bg-ash-700/50">
                      <td class="px-4 py-2 font-mono text-ink-700 dark:text-ink-200">{{ stat.name }}</td>
                      <td class="px-4 py-2 text-ink-600 dark:text-ink-300">{{ stat.size }}</td>
                      <td class="px-4 py-2 text-ink-600 dark:text-ink-300">{{ formatNum(stat.count) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Cache/Redis Tab -->
      <div v-if="activeTab === 'cache'" id="dev-panel-cache" role="tabpanel" aria-labelledby="dev-tab-cache" class="space-y-6">
        <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-850 flex items-center justify-between">
            <h2 class="font-semibold text-ink-900 dark:text-ink-50">Redis Cache</h2>
            <button @click="loadCache" :disabled="loadingCache" class="px-3 py-1.5 text-xs rounded-lg bg-[var(--accent)] text-cream-50 hover:opacity-90 disabled:opacity-50">Refresh</button>
          </div>
          <div class="p-5 space-y-4" v-if="cacheInfo">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div class="p-4 rounded-xl bg-cream-50 dark:bg-ash-700/50">
                <div class="text-ink-600 dark:text-ink-400 text-sm">Connected</div>
                <div class="text-2xl font-bold" :class="cacheInfo.connected ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'">{{ cacheInfo.connected ? 'Yes' : 'No' }}</div>
              </div>
              <div class="p-4 rounded-xl bg-cream-50 dark:bg-ash-700/50">
                <div class="text-ink-600 dark:text-ink-400 text-sm">Used Memory</div>
                <div class="text-2xl font-bold text-ink-900 dark:text-ink-50">{{ cacheInfo.used_memory }}</div>
              </div>
              <div class="p-4 rounded-xl bg-cream-50 dark:bg-ash-700/50">
                <div class="text-ink-600 dark:text-ink-400 text-sm">Keys</div>
                <div class="text-2xl font-bold text-ink-900 dark:text-ink-50">{{ cacheInfo.keys }}</div>
              </div>
              <div class="p-4 rounded-xl bg-cream-50 dark:bg-ash-700/50">
                <div class="text-ink-600 dark:text-ink-400 text-sm">Hit Rate</div>
                <div class="text-2xl font-bold text-ink-900 dark:text-ink-50">{{ cacheInfo.hit_rate }}%</div>
              </div>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div v-for="ks in cacheInfo.keyspaces" :key="ks.db" class="p-4 rounded-xl bg-cream-50 dark:bg-ash-700/50">
                <div class="font-medium text-ink-900 dark:text-ink-50">{{ ks.db.toUpperCase() }}</div>
                <div class="text-sm text-ink-600 dark:text-ink-300 mt-1">{{ ks.keys }} keys</div>
                <div class="text-xs text-ink-500 dark:text-ink-400">{{ ks.expires }} expires</div>
                <div class="text-xs text-ink-500 dark:text-ink-400">Avg TTL: {{ ks.avg_ttl }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Feature Flags Tab -->
      <div v-if="activeTab === 'flags'" id="dev-panel-flags" role="tabpanel" aria-labelledby="dev-tab-flags" class="space-y-6">
        <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-850 flex items-center justify-between">
            <h2 class="font-semibold text-ink-900 dark:text-ink-50">Feature Flags</h2>
            <button @click="loadFlags" :disabled="loadingFlags" class="px-3 py-1.5 text-xs rounded-lg bg-[var(--accent)] text-cream-50 hover:opacity-90 disabled:opacity-50">Refresh</button>
          </div>
          <div class="p-5 space-y-3" v-if="flags.length > 0">
            <div v-for="flag in flags" :key="flag.key" class="flex items-center justify-between p-4 rounded-xl bg-cream-50 dark:bg-ash-700/50">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg flex items-center justify-center" :class="flag.enabled ? 'bg-green-100 dark:bg-green-900/30' : 'bg-red-100 dark:bg-red-900/30'">
                  <svg class="w-5 h-5" :class="flag.enabled ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="flag.enabled ? 'M5 13l4 4L19 7' : 'M6 18L18 6M6 6l12 12'" />
                  </svg>
                </div>
                <div>
                  <div class="font-medium text-ink-900 dark:text-ink-50">{{ flag.key }}</div>
                  <div class="text-xs text-ink-500 dark:text-ink-400">{{ flag.description }}</div>
                </div>
              </div>
              <button @click="toggleFlag(flag)" class="px-3 py-1.5 text-xs rounded-lg transition" :class="flag.enabled ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50' : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 hover:bg-green-200 dark:hover:bg-green-900/50'">
                {{ flag.enabled ? 'Disable' : 'Enable' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Maintenance Banner Detail (shown when MAINTENANCE_MODE is enabled) -->
        <div v-if="maintenanceFlag?.enabled" class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden border-amber-200 dark:border-amber-800">
          <div class="px-5 py-4 border-b border-cream-300 dark:border-ash-700 bg-amber-50 dark:bg-amber-900/20">
            <h2 class="font-semibold text-ink-900 dark:text-ink-50 flex items-center gap-2">
              <span>🛠️</span> Maintenance Banner Settings
            </h2>
          </div>
          <div class="p-5 space-y-4">
            <div class="flex items-center gap-3">
              <label class="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" v-model="maintEnabled" class="w-5 h-5 rounded border-navy-500 bg-cream-100 dark:bg-ash-700 text-navy-500 focus:ring-navy-500" />
                <span class="text-sm text-ink-700 dark:text-ink-200">Enable Maintenance Banner</span>
              </label>
              <span class="px-2 py-0.5 text-xs rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">MAINTENANCE_MODE is ON</span>
            </div>
            <div v-if="maintEnabled" class="space-y-3 pl-7">
              <div>
                <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Message (HTML allowed)</label>
                <textarea v-model="maintMessage" rows="4" class="w-full px-3 py-2 text-sm border border-cream-300 dark:border-ash-700 rounded-lg bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-100"></textarea>
              </div>
              <div class="flex items-center gap-3">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="radio" v-model="maintTheme" value="dark" class="w-4 h-4 text-navy-500 border-navy-500 focus:ring-navy-500" />
                  <span class="text-sm text-ink-700 dark:text-ink-200">Dark theme</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="radio" v-model="maintTheme" value="light" class="w-4 h-4 text-navy-500 border-navy-500 focus:ring-navy-500" />
                  <span class="text-sm text-ink-700 dark:text-ink-200">Light theme</span>
                </label>
              </div>
              <button @click="saveMaintenance" class="px-4 py-2 text-sm rounded-lg bg-[var(--accent)] text-cream-50 hover:opacity-90 transition mt-2">Save Banner</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Dev Access Tab -->
      <div v-if="activeTab === 'dev-access'" id="dev-panel-dev-access" role="tabpanel" aria-labelledby="dev-tab-dev-access" class="space-y-6">
        <div class="bg-white dark:bg-ash-800 rounded-2xl border shadow-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-850">
            <h2 class="font-semibold text-ink-900 dark:text-ink-50">Dev Room Access</h2>
          </div>
          <div class="p-5 space-y-4">
            <div v-if="devError" class="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">{{ devError }}</div>
            <div v-if="devSuccess" class="p-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 text-sm">{{ devSuccess }}</div>

            <!-- Add Dev Form -->
            <div class="p-4 rounded-xl bg-cream-50 dark:bg-ash-700/50">
              <h3 class="font-medium text-ink-900 dark:text-ink-50 mb-3">Grant Dev Access</h3>
              <div class="flex gap-2">
                <input
                  v-model="newDevEmail"
                  type="email"
                  placeholder="partner@email.com"
                  class="flex-1 px-3 py-2 text-sm border border-cream-300 dark:border-ash-700 rounded-lg bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-100 focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]"
                  @keydown.enter="addDev"
                />
                <button
                  @click="addDev"
                  :disabled="addingDev || !newDevEmail.trim()"
                  class="px-4 py-2 text-sm rounded-lg bg-[var(--accent)] text-cream-50 hover:opacity-90 disabled:opacity-50 transition"
                >
                  <span v-if="addingDev" class="flex items-center gap-1.5"><svg class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/></svg> Adding...</span>
                  <span v-else>Add Dev</span>
                </button>
              </div>
            </div>

            <!-- Dev List -->
            <div v-if="developers.length > 0">
              <h3 class="font-medium text-ink-900 dark:text-ink-50 mb-3">Current Developers ({{ developers.length }})</h3>
              <div class="space-y-2">
                <div v-for="dev in developers" :key="dev.id" class="flex items-center justify-between p-3 rounded-xl bg-cream-50 dark:bg-ash-700/50">
                  <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-[var(--accent)] flex items-center justify-center text-cream-50 font-medium text-sm">{{ dev.email.charAt(0).toUpperCase() }}</div>
                    <div>
                      <div class="font-medium text-ink-900 dark:text-ink-50">{{ dev.email }}</div>
                      <div class="text-xs text-ink-500 dark:text-ink-400">{{ dev.name }} · {{ dev.role }}</div>
                    </div>
                  </div>
                  <button
                    @click="removeDev(dev.email)"
                    :disabled="removingDevId === dev.id"
                    class="px-3 py-1.5 text-xs rounded-lg bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50 disabled:opacity-50 transition"
                  >
                    <span v-if="removingDevId === dev.id" class="flex items-center gap-1.5"><svg class="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/></svg></span>
                    <span v-else>Remove</span>
                  </button>
                </div>
              </div>
            </div>
            <div v-else class="text-center text-ink-500 dark:text-ink-400 py-4">No developers with dev access yet</div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import AppHeader from '../components/AppHeader.vue'
import api from '../api/index.js'

const activeTab = ref<'system' | 'jobs' | 'image-jobs' | 'db' | 'cache' | 'flags' | 'dev-access'>('system')
const loadingJobs = ref(false)
const loadingDb = ref(false)
const loadingCache = ref(false)
const loadingFlags = ref(false)
const loadingImageJobs = ref(false)

const statsCards = ref([
  { label: 'Papers', value: 0, icon: '📄' },
  { label: 'Users', value: 0, icon: '👥' },
  { label: 'Active Jobs', value: 0, icon: '⚙️' },
  { label: 'Cache Keys', value: 0, icon: '🗄️' },
])

const devTabs = [
  { id: 'system' as const, label: 'System', icon: '🖥️' },
  { id: 'jobs' as const, label: 'Jobs', icon: '⚙️' },
  { id: 'image-jobs' as const, label: 'Image Jobs', icon: '🖼️' },
  { id: 'db' as const, label: 'Database', icon: '🗃️' },
  { id: 'cache' as const, label: 'Cache', icon: '🗄️' },
  { id: 'flags' as const, label: 'Flags', icon: '🚩' },
  { id: 'dev-access' as const, label: 'Dev Access', icon: '👥' },
]

const versionInfo = ref<{ version: string; buildDate: string; commit: string; env: string } | null>(null)
const health = ref<{ services: { name: string; status: string; latency?: number; error?: string }[] } | null>(null)
const jobs = ref<any[]>([])
const dbStats = ref<{ tables: { name: string; count: number; size: string }[] } | null>(null)
const cacheInfo = ref<{ connected: boolean; used_memory: string; keys: number; hit_rate: number; keyspaces: { db: string; keys: number; expires: number; avg_ttl: string }[] } | null>(null)
const flags = ref<{ key: string; enabled: boolean; description: string }[]>([])
const imageJobs = ref<any[]>([])
let imageJobsTimer: ReturnType<typeof setInterval> | null = null

// Maintenance banner (synced with MAINTENANCE_MODE flag)
const maintEnabled = ref(false)
const maintMessage = ref('')
const maintTheme = ref<'dark' | 'light'>('dark')

// Computed: find MAINTENANCE_MODE flag
const maintenanceFlag = computed(() => flags.value.find(f => f.key === 'MAINTENANCE_MODE'))

// Sync maintEnabled with flag when flags load
watch(maintenanceFlag, (flag) => {
  if (flag) maintEnabled.value = flag.enabled
}, { immediate: true })

function formatNum(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('id-ID', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return '—' }
}

function jobStatusClass(status: string): string {
  switch (status) {
    case 'finished': return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
    case 'failed': return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
    case 'started': return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
    case 'queued': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
    default: return 'bg-cream-100 dark:bg-ash-700 text-ink-700 dark:text-ink-200'
  }
}

function imageJobStatusClass(status: string): string {
  switch (status) {
    case 'done': return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
    case 'error': return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
    case 'running': return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
    case 'queued': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
    case 'cancelled': return 'bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-300'
    default: return 'bg-cream-100 dark:bg-ash-700 text-ink-700 dark:text-ink-200'
  }
}

function imageJobProgress(job: any): number {
  if (job.status === 'done') return 100
  if (job.status === 'queued') return 5
  if (job.status === 'running') return 60
  if (job.status === 'error' || job.status === 'cancelled') return 0
  return 0
}

async function loadAll() {
  await Promise.all([
    loadVersion(),
    loadHealth(),
    loadJobs(),
    loadDbStats(),
    loadCache(),
    loadFlags(),
    loadMaintenance(),
    loadDevList(),
  ])
}

async function loadMaintenance() {
  try {
    const res = await api.get('/api/dev/maintenance-banner/public')
    const data = res.data
    maintEnabled.value = data.enabled || false
    maintMessage.value = data.message || ''
    maintTheme.value = data.theme || 'dark'
  } catch (e) {
    console.error('Failed to load maintenance banner', e)
  }
}

async function saveMaintenance() {
  try {
    await api.post('/api/dev/maintenance-banner', {
      enabled: maintEnabled.value,
      message: maintMessage.value,
      theme: maintTheme.value,
    })
    // Refresh flags to sync MAINTENANCE_MODE state
    await loadFlags()
    // Emit event so MaintenanceBanner component updates immediately
    window.dispatchEvent(new Event('maintenance-banner-updated'))
  } catch (e) {
    console.error('Failed to save maintenance banner', e)
  }
}

// Dev Access management
const developers = ref<{ id: number; email: string; name: string; role: string }[]>([])
const newDevEmail = ref('')
const addingDev = ref(false)
const removingDevId = ref<number | null>(null)
const devError = ref('')
const devSuccess = ref('')

async function loadDevList() {
  try {
    const res = await api.get('/api/dev/list')
    developers.value = res.data.developers || []
  } catch (e: any) {
    devError.value = e?.response?.data?.error || 'Failed to load dev list'
  }
}

async function addDev() {
  const email = newDevEmail.value.trim().toLowerCase()
  if (!email) { devError.value = 'Email required'; return }
  addingDev.value = true
  devError.value = ''
  devSuccess.value = ''
  try {
    const res = await api.post('/api/dev/add', { email })
    devSuccess.value = res.data.message || `Added ${email}`
    newDevEmail.value = ''
    await loadDevList()
    // Refresh user state so header badge updates if self
    const auth = JSON.parse(localStorage.getItem('pg_user') || 'null')
    if (auth?.email === email) {
      window.location.reload()
    }
  } catch (e: any) {
    devError.value = e?.response?.data?.error || 'Failed to add dev'
  } finally {
    addingDev.value = false
  }
}

async function removeDev(email: string) {
  removingDevId.value = -(developers.value.findIndex(d => d.email === email) + 1)
  devError.value = ''
  devSuccess.value = ''
  try {
    const res = await api.post('/api/dev/remove', { email })
    devSuccess.value = res.data.message || `Removed ${email}`
    await loadDevList()
  } catch (e: any) {
    devError.value = e?.response?.data?.error || 'Failed to remove dev'
  } finally {
    removingDevId.value = null
  }
}

async function loadVersion() {
  try {
    const res = await api.get('/api/dev/version')
    versionInfo.value = res.data
  } catch (e) {
    console.error('Failed to load version', e)
  }
}

async function loadHealth() {
  try {
    const res = await api.get('/api/dev/health')
    health.value = res.data
  } catch (e) {
    console.error('Failed to load health', e)
  }
}

const jobsPage = ref(1)
const jobsTotalPages = ref(1)
const imageJobsPage = ref(1)
const imageJobsTotalPages = ref(1)

async function loadJobs() {
  loadingJobs.value = true
  try {
    const res = await api.get(`/api/dev/jobs?page=${jobsPage.value}&per_page=50`)
    jobs.value = res.data.jobs || []
    jobsTotalPages.value = res.data.pagination?.total_pages || 1
    statsCards.value[2].value = jobs.value.filter(j => j.status === 'started').length
  } catch (e) {
    console.error('Failed to load jobs', e)
  } finally {
    loadingJobs.value = false
  }
}

let jobsTimer: ReturnType<typeof setInterval> | null = null

function startJobsPolling() {
  stopJobsPolling()
  loadJobs()
  jobsTimer = setInterval(loadJobs, 3000)
}

function stopJobsPolling() {
  if (jobsTimer) { clearInterval(jobsTimer); jobsTimer = null }
}

async function loadImageJobs() {
  loadingImageJobs.value = true
  try {
    const res = await api.get(`/api/dev/image-jobs?page=${imageJobsPage.value}&per_page=50`)
    imageJobs.value = res.data.jobs || []
    imageJobsTotalPages.value = res.data.pagination?.total_pages || 1
    statsCards.value[2].value = imageJobs.value.filter(j => j.status === 'running' || j.status === 'queued').length
  } catch (e) {
    console.error('Failed to load image jobs', e)
  } finally {
    loadingImageJobs.value = false
  }
}

function startImageJobsPolling() {
  stopImageJobsPolling()
  loadImageJobs()
  imageJobsTimer = setInterval(loadImageJobs, 3000)
}

function stopImageJobsPolling() {
  if (imageJobsTimer) { clearInterval(imageJobsTimer); imageJobsTimer = null }
}

async function loadDbStats() {
  loadingDb.value = true
  try {
    const res = await api.get('/api/dev/db/stats')
    dbStats.value = res.data
    statsCards.value[0].value = (dbStats.value?.tables?.find(t => t.name === 'papers')?.count || 0)
    statsCards.value[1].value = (dbStats.value?.tables?.find(t => t.name === 'users')?.count || 0)
  } catch (e) {
    console.error('Failed to load db stats', e)
  } finally {
    loadingDb.value = false
  }
}

async function loadCache() {
  loadingCache.value = true
  try {
    const res = await api.get('/api/dev/cache')
    cacheInfo.value = res.data
    statsCards.value[3].value = cacheInfo.value?.keys || 0
  } catch (e) {
    console.error('Failed to load cache', e)
  } finally {
    loadingCache.value = false
  }
}

async function loadFlags() {
  loadingFlags.value = true
  try {
    const res = await api.get('/api/dev/flags')
    flags.value = res.data.flags || []
  } catch (e) {
    console.error('Failed to load flags', e)
  } finally {
    loadingFlags.value = false
  }
}

async function toggleFlag(flag: { key: string; enabled: boolean }) {
  try {
    await api.post('/api/dev/flags/toggle', { key: flag.key, enabled: !flag.enabled })
    flag.enabled = !flag.enabled
  } catch (e) {
    console.error('Failed to toggle flag', e)
  }
}

onMounted(async () => {
  await loadAll()
  // Start polling when jobs or image-jobs tab is active
  watch(activeTab, (tab) => {
    if (tab === 'image-jobs') {
      startImageJobsPolling()
      stopJobsPolling()
      imageJobsPage.value = 1
    } else if (tab === 'jobs') {
      startJobsPolling()
      stopImageJobsPolling()
      jobsPage.value = 1
    } else {
      stopImageJobsPolling()
      stopJobsPolling()
    }
  }, { immediate: true })
})

onUnmounted(() => {
  stopImageJobsPolling()
  stopJobsPolling()
})
</script>