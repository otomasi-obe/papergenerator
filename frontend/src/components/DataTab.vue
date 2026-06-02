<template>
  <div class="p-6 max-w-5xl mx-auto">
    <!-- Header -->
    <div class="mb-4 flex items-start justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">Data</h2>
        <p class="text-sm text-ink-600 dark:text-ink-300 mt-0.5">
          Mulai dari sumber data — unggah file (PDF / Excel / CSV / Word) atau tempel manual.
          Satu sumber bisa menghasilkan beberapa tabel, dan tiap tabel bisa menghasilkan beberapa
          grafik. Anda boleh menambah lebih dari satu sumber data.
        </p>
      </div>
      <button
        @click="openAddSource"
        class="shrink-0 px-3 py-1.5 bg-brown-600 hover:bg-brown-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-xs font-medium">
        ＋ Tambah sumber data
      </button>
    </div>

    <!-- ── Add-source panel (toggled) ────────────────────────────────── -->
    <section v-if="addingSource" class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden mb-6">
      <div class="px-4 py-3 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-850 flex items-center justify-between">
        <div class="flex gap-1.5">
          <button
            @click="sourceMode = 'upload'"
            :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              sourceMode === 'upload'
                ? 'bg-brown-600 text-cream-50 dark:bg-cream-200 dark:text-ash-900'
                : 'text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700']">
            📁 Unggah file
          </button>
          <button
            @click="sourceMode = 'manual'"
            :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              sourceMode === 'manual'
                ? 'bg-brown-600 text-cream-50 dark:bg-cream-200 dark:text-ash-900'
                : 'text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700']">
            ⌨ Input manual
          </button>
        </div>
        <button @click="closeAddSource" class="text-ink-400 hover:text-ink-600 dark:hover:text-ink-200 text-sm">✕ Tutup</button>
      </div>

      <div class="p-4 space-y-3">
        <!-- Upload -->
        <div v-if="sourceMode === 'upload'">
          <input
            ref="fileInput"
            type="file"
            accept=".pdf,.xlsx,.xls,.csv,.tsv,.doc,.docx"
            class="hidden"
            @change="onFileSelected"
          />
          <div
            class="border-2 border-dashed border-cream-400 dark:border-ash-600 rounded-xl p-6 text-center cursor-pointer hover:border-brown-500 dark:hover:border-cream-400 transition-colors"
            @click="fileInput?.click()"
            @dragover.prevent
            @drop.prevent="onFileDrop"
          >
            <p class="text-sm text-ink-700 dark:text-ink-200 font-medium">
              Klik atau seret file ke sini untuk diekstrak
            </p>
            <p class="text-xs text-ink-500 dark:text-ink-400 mt-1">
              Didukung: PDF, Excel (.xlsx/.xls), CSV/TSV, Word (.doc/.docx)
            </p>
          </div>

          <div v-if="extractState === 'loading'" class="mt-3 flex items-center gap-2 text-sm text-ink-600 dark:text-ink-300">
            <span class="inline-block w-4 h-4 border-2 border-cream-300 border-t-brown-600 rounded-full animate-spin"></span>
            Mengekstrak data dari <strong>{{ pendingFilename }}</strong>…
          </div>

          <div v-if="extractState === 'error'" class="mt-3 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-sm text-red-700 dark:text-red-300">
            <p class="font-medium">Gagal mengekstrak data</p>
            <p class="mt-0.5">{{ extractError }}</p>
            <p class="mt-1 text-xs opacity-80">
              Jika file tidak punya tabel terstruktur, gunakan <strong>Input manual</strong> untuk menempel data.
            </p>
          </div>
        </div>

        <!-- Manual paste -->
        <div v-else>
          <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">
            Tempel data (pemisah koma, tab, atau titik koma). Baris pertama = header.
          </label>
          <textarea
            v-model="manualText"
            rows="6"
            placeholder="Nama, Nilai, Tahun&#10;Metode A, 12.5, 2023&#10;Metode B, 18.2, 2024"
            class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm font-mono"
          ></textarea>
          <button
            @click="applyManual"
            class="mt-2 px-4 py-2 bg-brown-600 hover:bg-brown-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-medium">
            Tambahkan sumber data
          </button>
          <p v-if="manualError" class="mt-2 text-sm text-red-600 dark:text-red-400">{{ manualError }}</p>
        </div>
      </div>
    </section>

    <!-- ── Empty state ───────────────────────────────────────────────── -->
    <div v-if="!sources.length && !addingSource"
      class="border-2 border-dashed border-cream-300 dark:border-ash-700 rounded-xl p-10 text-center text-ink-500 dark:text-ink-400">
      <p class="text-sm">Belum ada sumber data.</p>
      <button @click="openAddSource"
        class="mt-3 px-4 py-2 bg-brown-600 hover:bg-brown-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-medium">
        ＋ Tambah sumber data
      </button>
    </div>

    <!-- ── Charts loading / error (global) ───────────────────────────── -->
    <div v-if="chartsListError" class="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-sm text-red-700 dark:text-red-300 flex items-center justify-between">
      <span>{{ chartsListError }}</span>
      <button @click="loadCharts" class="px-2.5 py-1 rounded text-xs font-medium border border-red-300 dark:border-red-700 hover:bg-red-100 dark:hover:bg-red-900/50">Coba lagi</button>
    </div>

    <!-- ── Data sources ──────────────────────────────────────────────── -->
    <section v-for="source in sources" :key="source.id"
      class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden mb-6">
      <!-- Source header -->
      <div class="px-4 py-3 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-850 flex items-center justify-between gap-2">
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-base leading-none">{{ source.type === 'manual' ? '⌨' : '📄' }}</span>
          <input v-model="source.name"
            class="font-semibold text-sm text-ink-800 dark:text-ink-100 bg-transparent border border-transparent hover:border-cream-400 dark:hover:border-ash-600 focus:border-brown-500 dark:focus:border-cream-400 focus:bg-white dark:focus:bg-ash-900 rounded px-1.5 py-0.5 outline-none truncate max-w-xs"
            :title="source.name" />
          <span class="text-xs text-ink-500 dark:text-ink-400 shrink-0 whitespace-nowrap">
            {{ source.rows.length }} baris × {{ source.columns.length }} kolom
          </span>
        </div>
        <div class="flex gap-1.5 shrink-0">
          <button @click="addTable(source)"
            class="px-2.5 py-1 rounded-lg text-xs font-medium bg-brown-600 hover:bg-brown-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900">
            ＋ Tabel
          </button>
          <button @click="removeSource(source)"
            class="px-2.5 py-1 rounded-lg text-xs font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30">
            Hapus sumber
          </button>
        </div>
      </div>

      <div class="p-4 space-y-4">
        <div v-if="!source.tables.length" class="text-center py-6 text-sm text-ink-400 dark:text-ink-500">
          Belum ada tabel. Klik <strong>＋ Tabel</strong> untuk membuat tabel dari sumber ini.
        </div>

        <!-- Tables within this source -->
        <div v-for="table in source.tables" :key="table.id"
          class="border border-cream-300 dark:border-ash-600 rounded-xl overflow-hidden">
          <!-- Table header -->
          <div class="bg-cream-100 dark:bg-ash-850 px-3 py-2 flex items-center justify-between gap-2 border-b border-cream-300 dark:border-ash-600">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-sm leading-none">🗂</span>
              <input v-model="table.name"
                class="text-sm font-semibold text-ink-700 dark:text-ink-100 bg-transparent border border-transparent hover:border-cream-400 dark:hover:border-ash-600 focus:border-brown-500 dark:focus:border-cream-400 focus:bg-white dark:focus:bg-ash-900 rounded px-1.5 py-0.5 outline-none truncate max-w-[12rem]" />
              <span class="text-xs text-ink-500 dark:text-ink-400 shrink-0 whitespace-nowrap">
                {{ table.rows.length }} × {{ table.columns.length }}
              </span>
            </div>
            <div class="flex gap-1.5 shrink-0">
              <button @click="addColumn(table)" class="px-2 py-1 rounded-lg text-xs font-medium text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700">+ Kolom</button>
              <button @click="addRow(table)" class="px-2 py-1 rounded-lg text-xs font-medium text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700">+ Baris</button>
              <button @click="newChart(table)" class="px-2 py-1 rounded-lg text-xs font-medium bg-brown-600 hover:bg-brown-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900">＋ Grafik</button>
              <button @click="removeTable(source, table)" class="px-2 py-1 rounded-lg text-xs font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30">Hapus</button>
            </div>
          </div>

          <div class="p-3 space-y-4">
            <!-- Editable grid -->
            <div class="overflow-x-auto">
              <table class="min-w-full border border-cream-300 dark:border-ash-600 text-sm">
                <thead>
                  <tr class="bg-cream-200 dark:bg-ash-700">
                    <th v-for="(_col, cIdx) in table.columns" :key="cIdx"
                      class="border border-cream-300 dark:border-ash-600 px-2 py-1 relative">
                      <input
                        v-model="table.columns[cIdx]"
                        class="w-full bg-transparent text-center font-semibold text-ink-900 dark:text-ink-50 focus:outline-none" />
                      <button v-if="table.columns.length > 1"
                        @click="removeColumn(table, cIdx)"
                        class="absolute -top-1 -right-1 text-red-400 hover:text-red-600 text-xs bg-cream-50 dark:bg-ash-800 rounded-full w-4 h-4 flex items-center justify-center shadow"
                        title="Hapus kolom">✕</button>
                    </th>
                    <th class="border border-cream-300 dark:border-ash-600 px-1 py-1 w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, rIdx) in table.rows" :key="rIdx">
                    <td v-for="(_cell, cIdx) in row" :key="cIdx" class="border border-cream-300 dark:border-ash-600 px-1 py-1">
                      <input
                        v-model="table.rows[rIdx][cIdx]"
                        class="w-full bg-transparent text-center text-ink-900 dark:text-ink-50 focus:outline-none focus:bg-cream-100 dark:focus:bg-ash-700 px-1" />
                    </td>
                    <td class="border border-cream-300 dark:border-ash-600 px-1 py-1 text-center">
                      <button @click="removeRow(table, rIdx)" class="text-red-400 hover:text-red-600 text-xs" title="Hapus baris">✕</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Chart editor for this table -->
            <div v-if="editingTableId === table.id" class="border border-cream-300 dark:border-ash-600 rounded-xl overflow-hidden">
              <div class="bg-cream-100 dark:bg-ash-850 px-4 py-2.5 flex items-center justify-between border-b border-cream-300 dark:border-ash-600">
                <span class="text-sm font-semibold text-ink-700 dark:text-ink-100">Grafik baru</span>
                <button @click="cancelEdit" class="text-ink-400 hover:text-ink-600 dark:hover:text-ink-200 text-sm">✕ Batal</button>
              </div>

              <div class="p-4 space-y-3">
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Jenis grafik</label>
                    <select v-model="form.kind"
                      class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm">
                      <option v-for="k in chartKinds" :key="k.value" :value="k.value">{{ k.label }}</option>
                    </select>
                  </div>
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Judul</label>
                    <input v-model="form.title" placeholder="Judul grafik"
                      class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm" />
                  </div>
                </div>

                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Label sumbu X</label>
                    <input v-model="form.xlabel" placeholder="Sumbu X"
                      class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm" />
                  </div>
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Label sumbu Y</label>
                    <input v-model="form.ylabel" placeholder="Sumbu Y"
                      class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm" />
                  </div>
                </div>

                <!-- Column mapping: pick X column + Y series from this table -->
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Kolom X (label / kategori)</label>
                    <select v-model.number="form.xCol"
                      class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm">
                      <option :value="-1">(indeks baris)</option>
                      <option v-for="(col, i) in table.columns" :key="i" :value="i">{{ col || `Kolom ${i + 1}` }}</option>
                    </select>
                  </div>
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Kolom Y (seri numerik)</label>
                    <div class="flex flex-wrap gap-1.5 p-2 border border-cream-300 dark:border-ash-600 rounded-lg bg-white dark:bg-ash-900 min-h-[2.5rem]">
                      <label v-for="(col, i) in table.columns" :key="i"
                        class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded cursor-pointer"
                        :class="form.yCols.includes(i) ? 'bg-brown-600 text-cream-50 dark:bg-cream-200 dark:text-ash-900' : 'bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-200'">
                        <input type="checkbox" class="hidden" :value="i" v-model="form.yCols" />
                        {{ col || `Kolom ${i + 1}` }}
                      </label>
                    </div>
                  </div>
                </div>

                <div v-if="editorError" class="p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-sm text-red-700 dark:text-red-300">
                  {{ editorError }}
                </div>

                <div class="flex gap-2">
                  <button @click="saveChart(table)" :disabled="saving"
                    class="px-4 py-2 bg-brown-600 hover:bg-brown-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-medium disabled:opacity-50">
                    {{ saving ? 'Membuat…' : 'Buat Grafik' }}
                  </button>
                  <button @click="cancelEdit"
                    class="px-4 py-2 bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-200 rounded-lg text-sm font-medium hover:bg-cream-300 dark:hover:bg-ash-600">
                    Batal
                  </button>
                </div>
              </div>
            </div>

            <!-- Charts gallery for this table -->
            <div v-if="tableCharts(table).length" class="grid sm:grid-cols-2 gap-3">
              <div v-for="(chart, idx) in tableCharts(table)" :key="chart.image_id"
                class="border border-cream-300 dark:border-ash-600 rounded-xl overflow-hidden">
                <div class="bg-cream-100 dark:bg-ash-850 px-3 py-2 flex items-center justify-between border-b border-cream-300 dark:border-ash-600">
                  <span class="text-xs font-semibold text-ink-700 dark:text-ink-100 truncate">
                    {{ chart.title || `Grafik ${idx + 1}` }} · {{ chart.kind }}
                  </span>
                  <button @click="deleteChart(table, chart.image_id)" class="text-red-400 hover:text-red-600 text-xs shrink-0">Hapus</button>
                </div>
                <div class="p-3">
                  <img :src="chart.url" :alt="chart.title || `Grafik ${idx + 1}`" class="max-w-full h-auto rounded border border-cream-300 dark:border-ash-600" />
                  <div class="mt-2 bg-cream-100 dark:bg-ash-850 border border-cream-200 dark:border-ash-600 rounded p-2">
                    <p class="text-[11px] text-ink-700 dark:text-ink-200">
                      <strong>Sisipkan:</strong>
                      <code class="bg-cream-200 dark:bg-ash-700 px-1 rounded">{{ `[CHART:${chart.image_id}]` }}</code>
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Charts not tied to any table (e.g. created before) ────────── -->
    <section v-if="orphanCharts.length"
      class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden mb-6">
      <div class="px-4 py-3 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-850">
        <span class="text-sm font-semibold text-ink-800 dark:text-ink-100">Grafik lainnya</span>
        <span class="text-xs text-ink-500 dark:text-ink-400 ml-2">(belum terkait tabel)</span>
      </div>
      <div class="p-4 grid sm:grid-cols-2 gap-3">
        <div v-for="(chart, idx) in orphanCharts" :key="chart.image_id"
          class="border border-cream-300 dark:border-ash-600 rounded-xl overflow-hidden">
          <div class="bg-cream-100 dark:bg-ash-850 px-3 py-2 flex items-center justify-between border-b border-cream-300 dark:border-ash-600">
            <span class="text-xs font-semibold text-ink-700 dark:text-ink-100 truncate">
              {{ chart.title || `Grafik ${idx + 1}` }} · {{ chart.kind }}
            </span>
            <button @click="deleteOrphanChart(chart.image_id)" class="text-red-400 hover:text-red-600 text-xs shrink-0">Hapus</button>
          </div>
          <div class="p-3">
            <img :src="chart.url" :alt="chart.title || `Grafik ${idx + 1}`" class="max-w-full h-auto rounded border border-cream-300 dark:border-ash-600" />
            <div class="mt-2 bg-cream-100 dark:bg-ash-850 border border-cream-200 dark:border-ash-600 rounded p-2">
              <p class="text-[11px] text-ink-700 dark:text-ink-200">
                <strong>Sisipkan:</strong>
                <code class="bg-cream-200 dark:bg-ash-700 px-1 rounded">{{ `[CHART:${chart.image_id}]` }}</code>
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, reactive, computed, onMounted, watch } from 'vue'
import chartsApi from '../api/charts'
import { usePaperStore } from '../stores/paper'

const store = usePaperStore()

const paperId = computed(() => store.currentPaperId)

// ─── Model ─────────────────────────────────────────────────────────────
// A paper has many data sources. A source has many tables (each table is an
// editable grid derived from / seeded by the source). A table owns many
// charts (tracked by the backend chart `image_id`). Backend charts are
// paper-global, so the source→table→chart grouping lives here and is
// reconciled with the live chart list on load.
//
//   source = { id, name, type: 'upload'|'manual', columns[], rows[][], tables[] }
//   table  = { id, name, columns[], rows[][], chartIds: number[] }

let _uid = 0
function genId(prefix: string) {
  _uid += 1
  return `${prefix}_${Date.now().toString(36)}_${_uid}`
}

const sources = reactive<any[]>([])

// ─── Persistence ────────────────────────────────────────────────────────
const LS_KEY = computed(() => (paperId.value ? `pg_data_sources_${paperId.value}` : ''))

function persist() {
  if (!LS_KEY.value) return
  try {
    localStorage.setItem(LS_KEY.value, JSON.stringify(sources))
  } catch { /* quota — ignore */ }
}

function restore() {
  sources.splice(0, sources.length)
  if (!LS_KEY.value) return
  try {
    const raw = localStorage.getItem(LS_KEY.value)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr)) {
        arr.forEach((s) => {
          sources.push({
            id: s.id || genId('src'),
            name: s.name || 'Sumber data',
            type: s.type || 'manual',
            columns: (s.columns || []).map((c: any) => (c == null ? '' : String(c))),
            rows: (s.rows || []).map((r: any[]) => (r || []).map((c: any) => (c == null ? '' : String(c)))),
            tables: (s.tables || []).map((t: any) => ({
              id: t.id || genId('tbl'),
              name: t.name || 'Tabel',
              columns: (t.columns || []).map((c: any) => (c == null ? '' : String(c))),
              rows: (t.rows || []).map((r: any[]) => (r || []).map((c: any) => (c == null ? '' : String(c)))),
              chartIds: Array.isArray(t.chartIds) ? t.chartIds.map((n: any) => Number(n)) : [],
            })),
          })
        })
      }
    }
  } catch { /* ignore */ }

  // Legacy migration: older single-dataset format → one source + one table.
  if (!sources.length && paperId.value) {
    try {
      const legacy = localStorage.getItem(`pg_dataset_${paperId.value}`)
      if (legacy) {
        const obj = JSON.parse(legacy)
        if (obj?.columns?.length) {
          const cols = obj.columns.map((c: any) => (c == null ? '' : String(c)))
          const rows = (obj.rows || []).map((r: any[]) => (r || []).map((c: any) => (c == null ? '' : String(c))))
          sources.push({
            id: genId('src'),
            name: obj.source || 'Sumber data',
            type: obj.source === 'manual' ? 'manual' : 'upload',
            columns: cols,
            rows,
            tables: [{ id: genId('tbl'), name: 'Tabel 1', columns: [...cols], rows: rows.map((r: any[]) => [...r]), chartIds: [] }],
          })
        }
      }
    } catch { /* ignore */ }
  }
}

watch(sources, persist, { deep: true })

// ─── Add source (upload or manual) ────────────────────────────────────
const addingSource = ref(false)
const sourceMode = ref<'upload' | 'manual'>('upload')
const fileInput = ref<HTMLInputElement | null>(null)

function openAddSource() {
  addingSource.value = true
  extractState.value = 'idle'
  extractError.value = ''
  manualText.value = ''
  manualError.value = ''
}
function closeAddSource() {
  addingSource.value = false
}

function addSourceFromData(columns: string[], rows: any[][], name: string, type: 'upload' | 'manual') {
  const cols = (columns || []).map((c) => (c == null ? '' : String(c)))
  const normRows = (rows || []).map((r) => (r || []).map((c: any) => (c == null ? '' : String(c))))
  const source = {
    id: genId('src'),
    name: name || (type === 'manual' ? 'Data manual' : 'Sumber data'),
    type,
    columns: cols,
    rows: normRows,
    tables: [
      {
        id: genId('tbl'),
        name: 'Tabel 1',
        columns: [...cols],
        rows: normRows.map((r) => [...r]),
        chartIds: [] as number[],
      },
    ],
  }
  sources.push(source)
  addingSource.value = false
}

// ─── File extraction ────────────────────────────────────────────────────
const extractState = ref<'idle' | 'loading' | 'error'>('idle')
const extractError = ref('')
const pendingFilename = ref('')

function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) extractFile(file)
  ;(e.target as HTMLInputElement).value = ''
}

function onFileDrop(e: DragEvent) {
  const file = e.dataTransfer?.files?.[0]
  if (file) extractFile(file)
}

async function extractFile(file: File) {
  if (!paperId.value) {
    extractState.value = 'error'
    extractError.value = 'Simpan paper terlebih dahulu sebelum mengunggah data.'
    return
  }
  extractState.value = 'loading'
  extractError.value = ''
  pendingFilename.value = file.name
  try {
    const parsed = await chartsApi.uploadData(paperId.value, file)
    if (!parsed.columns?.length) {
      extractState.value = 'error'
      extractError.value = 'File berhasil dibaca tapi tidak ada data tabular yang terdeteksi.'
      return
    }
    addSourceFromData(parsed.columns, parsed.rows, file.name, 'upload')
    extractState.value = 'idle'
  } catch (err: any) {
    extractState.value = 'error'
    extractError.value = err.response?.data?.error || err.message || 'Gagal mengunggah / mengekstrak file.'
  }
}

// ─── Manual paste ─────────────────────────────────────────────────────
const manualText = ref('')
const manualError = ref('')

function detectDelimiter(line: string): string {
  if (line.includes('\t')) return '\t'
  if (line.includes(';')) return ';'
  return ','
}

function applyManual() {
  manualError.value = ''
  const text = manualText.value.trim()
  if (!text) {
    manualError.value = 'Teks kosong.'
    return
  }
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== '')
  if (lines.length < 1) {
    manualError.value = 'Tidak ada baris yang valid.'
    return
  }
  const delim = detectDelimiter(lines[0])
  const parsed = lines.map((l) => l.split(delim).map((c) => c.trim()))
  const cols = parsed[0]
  const rows = parsed.slice(1)
  if (!rows.length) {
    manualError.value = 'Butuh minimal satu baris data di bawah header.'
    return
  }
  const width = cols.length
  const normRows = rows.map((r) => {
    const copy = r.slice(0, width)
    while (copy.length < width) copy.push('')
    return copy
  })
  manualText.value = ''
  addSourceFromData(cols, normRows, 'Data manual', 'manual')
}

function removeSource(source: any) {
  if (!confirm(`Hapus sumber "${source.name}" beserta semua tabel & grafiknya?`)) return
  // Delete backend charts tied to this source's tables.
  source.tables.forEach((t: any) => (t.chartIds || []).forEach((id: number) => backendDeleteChart(id)))
  const idx = sources.indexOf(source)
  if (idx >= 0) sources.splice(idx, 1)
}

// ─── Tables ───────────────────────────────────────────────────────────
function addTable(source: any) {
  source.tables.push({
    id: genId('tbl'),
    name: `Tabel ${source.tables.length + 1}`,
    columns: source.columns.length ? [...source.columns] : ['Kolom 1'],
    rows: source.rows.length
      ? source.rows.map((r: any[]) => [...r])
      : [new Array(source.columns.length || 1).fill('')],
    chartIds: [] as number[],
  })
}

function removeTable(source: any, table: any) {
  if (!confirm(`Hapus "${table.name}" beserta grafiknya?`)) return
  ;(table.chartIds || []).forEach((id: number) => backendDeleteChart(id))
  const idx = source.tables.indexOf(table)
  if (idx >= 0) source.tables.splice(idx, 1)
}

function addColumn(table: any) {
  table.columns.push(`Kolom ${table.columns.length + 1}`)
  table.rows.forEach((r: any[]) => r.push(''))
}
function removeColumn(table: any, cIdx: number) {
  if (table.columns.length <= 1) return
  table.columns.splice(cIdx, 1)
  table.rows.forEach((r: any[]) => r.splice(cIdx, 1))
}
function addRow(table: any) {
  table.rows.push(new Array(table.columns.length).fill(''))
}
function removeRow(table: any, rIdx: number) {
  table.rows.splice(rIdx, 1)
}

// ─── Charts ───────────────────────────────────────────────────────────
const chartKinds = [
  { value: 'line', label: 'Line' },
  { value: 'bar', label: 'Bar' },
  { value: 'scatter', label: 'Scatter' },
  { value: 'pie', label: 'Pie' },
  { value: 'hist', label: 'Histogram' },
  { value: 'box', label: 'Box plot' },
  { value: 'heatmap', label: 'Heatmap' },
]

const charts = ref<any[]>([])
const chartsLoading = ref(false)
const chartsListError = ref('')
const editingTableId = ref<string | null>(null)
const saving = ref(false)
const editorError = ref('')

const form = reactive({
  kind: 'line',
  title: '',
  xlabel: '',
  ylabel: '',
  xCol: -1,
  yCols: [] as number[],
})

// Charts that belong to a given table (in order, only those that still exist).
function tableCharts(table: any) {
  const byId = new Map(charts.value.map((c) => [c.image_id, c]))
  return (table.chartIds || []).map((id: number) => byId.get(id)).filter(Boolean)
}

// Charts present on the backend but not assigned to any table.
const orphanCharts = computed(() => {
  const assigned = new Set<number>()
  sources.forEach((s) => s.tables.forEach((t: any) => (t.chartIds || []).forEach((id: number) => assigned.add(id))))
  return charts.value.filter((c) => !assigned.has(c.image_id))
})

function isFiniteNumber(v: any): boolean {
  if (v === '' || v == null) return false
  return Number.isFinite(Number(v))
}

function defaultYCols(table: any): number[] {
  const cols: number[] = []
  for (let c = 0; c < table.columns.length; c++) {
    if (c === form.xCol) continue
    const numericCount = table.rows.reduce((n: number, r: any[]) => n + (isFiniteNumber(r[c]) ? 1 : 0), 0)
    if (numericCount > 0 && numericCount >= table.rows.length / 2) cols.push(c)
  }
  return cols.length ? cols : table.columns.map((_: any, i: number) => i).filter((i: number) => i !== form.xCol)
}

function newChart(table: any) {
  editorError.value = ''
  form.kind = 'line'
  form.title = ''
  form.xlabel = table.columns[0] || ''
  form.ylabel = ''
  const firstTextCol = table.columns.findIndex(
    (_c: any, i: number) => table.rows.some((r: any[]) => r[i] !== '' && !isFiniteNumber(r[i]))
  )
  form.xCol = firstTextCol
  form.yCols = defaultYCols(table)
  editingTableId.value = table.id
}

function cancelEdit() {
  editingTableId.value = null
  editorError.value = ''
}

function buildSpec(table: any) {
  const xCol = form.xCol
  const yCols = form.yCols.length ? form.yCols : defaultYCols(table)
  if (!yCols.length) {
    throw new Error('Pilih minimal satu kolom Y (seri numerik).')
  }
  const data = yCols.map((c) => table.rows.map((r: any[]) => Number(r[c]) || 0))
  const series_labels = yCols.map((c) => table.columns[c] || `Seri ${c + 1}`)
  const x_data = xCol >= 0 ? table.rows.map((r: any[]) => r[xCol]) : table.rows.map((_r: any, i: number) => `${i + 1}`)
  return {
    kind: form.kind,
    title: form.title || 'Grafik',
    xlabel: form.xlabel || '',
    ylabel: form.ylabel || '',
    data,
    series_labels,
    x_data,
  }
}

async function saveChart(table: any) {
  editorError.value = ''
  if (!paperId.value) {
    editorError.value = 'Simpan paper terlebih dahulu.'
    return
  }
  if (!form.title.trim()) {
    editorError.value = 'Judul grafik wajib diisi.'
    return
  }
  let spec
  try {
    spec = buildSpec(table)
  } catch (e: any) {
    editorError.value = e.message
    return
  }
  saving.value = true
  try {
    const created = await chartsApi.create(paperId.value, spec)
    if (created?.image_id != null && !table.chartIds.includes(created.image_id)) {
      table.chartIds.push(created.image_id)
    }
    await loadCharts()
    editingTableId.value = null
  } catch (err: any) {
    editorError.value = err.response?.data?.error || err.message || 'Gagal membuat grafik.'
  } finally {
    saving.value = false
  }
}

async function backendDeleteChart(chartId: number) {
  if (!paperId.value) return
  try {
    await chartsApi.delete(paperId.value, chartId)
  } catch { /* best-effort */ }
}

async function deleteChart(table: any, chartId: number) {
  if (!confirm('Hapus grafik ini?')) return
  await backendDeleteChart(chartId)
  const idx = table.chartIds.indexOf(chartId)
  if (idx >= 0) table.chartIds.splice(idx, 1)
  await loadCharts()
}

async function deleteOrphanChart(chartId: number) {
  if (!confirm('Hapus grafik ini?')) return
  await backendDeleteChart(chartId)
  await loadCharts()
}

async function loadCharts() {
  if (!paperId.value) return
  chartsLoading.value = true
  chartsListError.value = ''
  try {
    const res = await chartsApi.list(paperId.value)
    charts.value = res.charts || []
    // Drop references to charts that no longer exist on the backend.
    const liveIds = new Set(charts.value.map((c) => c.image_id))
    sources.forEach((s) =>
      s.tables.forEach((t: any) => {
        t.chartIds = (t.chartIds || []).filter((id: number) => liveIds.has(id))
      })
    )
  } catch (err: any) {
    chartsListError.value = err.response?.data?.error || err.message || 'Gagal memuat grafik.'
  } finally {
    chartsLoading.value = false
  }
}

watch(paperId, () => {
  restore()
  loadCharts()
})

onMounted(() => {
  restore()
  loadCharts()
})
</script>
