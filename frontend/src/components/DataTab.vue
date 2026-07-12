<template>
  <div class="p-6 max-w-5xl mx-auto">
    <!-- Header -->
    <div class="mb-4">
      <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50 flex items-center gap-2"><svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>Data</h2>
      <p class="text-sm text-ink-600 dark:text-ink-300 mt-0.5">
        Unggah file data — AI akan mengekstrak, memformat, menganalisis, dan membuat grafik secara otomatis.
        Anda bisa mengedit tabel setelah data ditampilkan.
      </p>
    </div>

    <!-- ── Data Extraction Prompt + Upload ───────────────────────────── -->
    <section class="mb-6">
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".pdf,.xlsx,.xls,.csv,.tsv,.doc,.docx,.pptx,.ppt"
        class="hidden"
        @change="onFileSelected"
      />

      <!-- Prompt box -->
      <div class="mb-3">
        <label class="block text-sm font-medium text-ink-700 dark:text-ink-200 mb-1.5">
          Instruksi untuk AI (opsional)
        </label>
        <textarea
          v-model="extractPrompt"
          rows="2"
          placeholder="Contoh: Buat tabel perbandingan akurasi metode, fokus pada 3 metode terbaik, tampilkan dalam format yang mudah dipahami..."
          class="w-full px-3 py-2 border border-cream-400 dark:border-ash-600 rounded-lg text-sm bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 focus:border-navy-500 dark:focus:border-cream-400 focus:outline-none resize-none"
          :disabled="extractState === 'loading'"
        ></textarea>
      </div>

      <!-- Dropzone with "Data Baru" button -->
      <div class="flex gap-3">
        <div
          class="flex-1 border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors"
          :class="extractState === 'loading'
            ? 'border-navy-400 dark:border-cream-400 bg-navy-50 dark:bg-navy-900/20'
            : 'border-cream-400 dark:border-ash-600 hover:border-navy-500 dark:hover:border-cream-400'"
          @click="extractState !== 'loading' && fileInput?.click()"
          @dragover.prevent
          @drop.prevent="onFileDrop"
        >
          <div v-if="extractState === 'loading'" class="flex items-center justify-center gap-2 text-sm text-ink-600 dark:text-ink-300">
            <span class="inline-block w-4 h-4 border-2 border-cream-300 dark:border-ash-600 border-t-navy-600 dark:border-t-cream-300 rounded-full animate-spin"></span>
            Memproses {{ pendingFiles.length }} file…
          </div>
          <div v-else>
            <p class="text-sm text-ink-700 dark:text-ink-200 font-medium">
              Klik atau seret file ke sini untuk diekstrak
            </p>
            <p class="text-xs text-ink-500 dark:text-ink-300 mt-1">
              Didukung: PDF, Excel (.xlsx/.xls), CSV/TSV, Word (.doc/.docx), PowerPoint (.pptx)
            </p>
            <p v-if="pendingFiles.length" class="text-xs text-navy-600 dark:text-cream-300 mt-2">
              📎 {{ pendingFiles.length }} file siap diunggah
            </p>
          </div>
        </div>

        <div class="flex flex-col gap-2">
          <button
            @click="fileInput?.click()"
            :disabled="extractState === 'loading'"
            class="px-4 py-2 bg-navy-600 hover:bg-navy-700 disabled:opacity-50 disabled:cursor-not-allowed text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-medium transition-colors"
          >
            📁 Data Baru
          </button>
          <button
            v-if="pendingFiles.length && extractState !== 'loading'"
            @click="startExtraction"
            class="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors"
          >
            ▶ Mulai Ekstrak
          </button>
          <button
            v-if="extractState === 'loading'"
            @click="cancelExtraction"
            class="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-medium transition-colors"
          >
            ⏹ Batal
          </button>
          <button
            v-if="!pendingFiles.length && extractPrompt.trim() && extractState !== 'loading'"
            @click="startTextExtraction"
            class="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors"
          >
            ✨ Generate dari Teks
          </button>
        </div>
      </div>

      <!-- Pending files list -->
      <div v-if="pendingFiles.length && extractState !== 'loading'" class="mt-3 p-3 bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-lg">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium text-ink-700 dark:text-ink-200">File yang akan diproses:</span>
          <button @click="clearPendingFiles" class="text-xs text-red-500 dark:text-red-400 hover:text-red-600 dark:hover:text-red-300">✕ Hapus semua</button>
        </div>
        <div class="space-y-1">
          <div v-for="(file, idx) in pendingFiles" :key="idx" class="flex items-center justify-between text-xs text-ink-600 dark:text-ink-300">
            <span class="truncate max-w-xs">📄 {{ file.name }}</span>
            <button @click="removePendingFile(idx)" class="text-red-400 hover:text-red-500 dark:text-red-400">✕</button>
          </div>
        </div>
      </div>

      <!-- Worker Progress -->
      <div v-if="extractState === 'loading'" class="mt-4 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-xl">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium text-blue-900 dark:text-blue-100">{{ extractProgress.message || 'Memproses data...' }}</span>
          <span class="text-xs text-blue-700 dark:text-blue-300">{{ extractProgress.progress || 0 }}%</span>
        </div>
        <div class="w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
          <div
            class="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-300"
            :style="{ width: (extractProgress.progress || 0) + '%' }"
          ></div>
        </div>
        <div v-if="extractProgress.stage" class="mt-2 text-xs text-blue-700 dark:text-blue-300">
          Tahap: {{ extractProgress.stage === 'extracting' ? 'Ekstraksi file' :
                     extractProgress.stage === 'ai_formatting' ? 'AI memformat data' :
                     extractProgress.stage === 'generating_charts' ? 'Membuat grafik' :
                     extractProgress.stage === 'finalizing' ? 'Menyimpan hasil' :
                     extractProgress.stage === 'starting' ? 'Memulai...' :
                     extractProgress.stage === 'complete' ? 'Selesai' :
                     extractProgress.stage === 'queued' ? 'Mengantri...' :
                     extractProgress.stage }}
        </div>
      </div>

      <div v-if="extractState === 'error'" class="mt-3 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-sm text-red-700 dark:text-red-300">
        <p class="font-medium">Gagal mengekstrak data</p>
        <p class="mt-0.5">{{ extractError }}</p>
      </div>
    </section>

    <!-- ── Charts loading / error ─────────────────────────────────────── -->
    <div v-if="chartsListError" class="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-sm text-red-700 dark:text-red-300 flex items-center justify-between">
      <span>{{ chartsListError }}</span>
      <button @click="loadCharts" class="px-2.5 py-1 rounded text-xs font-medium border border-red-300 dark:border-red-700 hover:bg-red-100 dark:hover:bg-red-900/50">Coba lagi</button>
    </div>

    <!-- ── AI Processing Summary ───────────────────────────────────────── -->
    <section v-if="aiSummary" class="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-xl shadow-sm overflow-hidden mb-6">
      <div class="px-4 py-3 border-b border-blue-200 dark:border-blue-700 bg-blue-100 dark:bg-blue-900/30 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-base">📊</span>
          <span class="font-semibold text-sm text-blue-900 dark:text-blue-100">Hasil Pemrosesan AI</span>
        </div>
        <button @click="aiSummary = null"
          class="text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 rounded-lg text-xs px-2 py-1">✕ Tutup</button>
      </div>

      <div class="p-4 space-y-3">
        <!-- Data Overview -->
        <div class="bg-white dark:bg-ash-800 rounded-lg p-3 border border-blue-200 dark:border-blue-700">
          <h4 class="text-sm font-semibold text-ink-900 dark:text-ink-50 mb-2 flex items-center gap-1.5">
            <span>📋</span> Informasi Data
          </h4>
          <p class="text-xs text-ink-700 dark:text-ink-200">{{ aiSummary.data_overview }}</p>
          <div class="mt-2 flex gap-3 text-xs text-ink-600 dark:text-ink-300">
            <span v-if="aiSummary.charts_created > 0" class="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded">
              ✓ {{ aiSummary.charts_created }} grafik dibuat
            </span>
          </div>
        </div>

        <!-- Analisa -->
        <div v-if="aiSummary.analysis" class="bg-white dark:bg-ash-800 rounded-lg p-3 border border-blue-200 dark:border-blue-700">
          <h4 class="text-sm font-semibold text-ink-900 dark:text-ink-50 mb-2 flex items-center gap-1.5">
            <span>💡</span> Analisa Data
          </h4>
          <p class="text-xs text-ink-700 dark:text-ink-200 leading-relaxed">{{ aiSummary.analysis }}</p>
        </div>
      </div>
    </section>

    <!-- ── 2-column layout: data list (left) + detail (right) ──────── -->
    <div class="grid lg:grid-cols-[280px,1fr] gap-4">
      <!-- Data list (left sidebar) -->
      <aside class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden">
        <div class="px-3 py-2 border-b border-cream-300 dark:border-ash-700 text-xs font-semibold text-ink-700 dark:text-ink-200 bg-cream-100 dark:bg-ash-850">
          {{ sources.length }} data{{ sources.length === 1 ? '' : 's' }}
        </div>
        <div v-if="!sources.length" class="px-3 py-12 text-center text-xs text-ink-500 dark:text-ink-300">
          Belum ada data.<br/>Upload file di atas untuk mulai ekstraksi.
        </div>
        <ul v-else class="divide-y divide-cream-200 dark:divide-ash-700 max-h-[60vh] overflow-y-auto">
          <li
            v-for="src in sources"
            :key="src.id"
            :class="[
              'group px-3 py-2 cursor-pointer flex items-start gap-2 transition-colors',
              activeSourceId === src.id ? 'bg-cream-200 dark:bg-ash-700' : 'hover:bg-cream-100 dark:hover:bg-ash-700',
            ]"
            @click="activeSourceId = src.id"
          >
            <span class="text-base leading-none pt-0.5">{{ src.type === 'manual' ? '⌨' : '📄' }}</span>
            <div class="min-w-0 flex-1">
              <div :class="['text-xs truncate', activeSourceId === src.id ? 'text-ink-900 dark:text-ink-50 font-semibold' : 'text-ink-700 dark:text-ink-100 font-medium']" :title="src.name">
                {{ src.name }}
              </div>
              <div class="text-[10px] text-ink-500 dark:text-ink-300 mt-0.5 flex items-center gap-1.5">
                <span>{{ (src.tables || []).length }} tabel</span>
                <span v-if="(src.chartImages || []).length">· {{ (src.chartImages || []).length }} grafik</span>
                <span v-if="src.analysis || src.aiAnalysis" class="px-1 py-0 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-[9px]">analisa</span>
              </div>
              <div class="text-[10px] text-ink-400 dark:text-ink-500 mt-0.5">
                {{ (src.rows || []).length }} × {{ (src.columns || []).length }}
              </div>
            </div>
            <button
              @click.stop="confirmDeleteSource(src)"
              class="opacity-0 group-hover:opacity-100 text-ink-400 dark:text-ink-300 hover:text-rose-500 text-xs px-1"
              title="Hapus"
            >🗑</button>
          </li>
        </ul>
      </aside>

      <!-- Detail pane (right) -->
      <section class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden min-h-[60vh]">
        <!-- No selection -->
        <div v-if="!activeSource" class="flex items-center justify-center h-full min-h-[40vh] text-sm text-ink-400 dark:text-ink-500">
          Pilih data dari daftar di kiri untuk melihat detail.
        </div>
        <!-- Active source detail -->
        <div v-else>
          <div class="px-4 py-3 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-850 flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-base leading-none">{{ activeSource.type === 'manual' ? '⌨' : '📄' }}</span>
              <input v-model="activeSource.name"
                class="font-semibold text-sm text-ink-800 dark:text-ink-100 bg-transparent border border-transparent hover:border-cream-400 dark:hover:border-ash-600 focus:border-navy-500 dark:focus:border-cream-400 focus:bg-white dark:focus:bg-ash-900 rounded px-1.5 py-0.5 outline-none truncate max-w-xs"
                :title="activeSource.name" />
              <span class="text-xs text-ink-500 dark:text-ink-300 shrink-0 whitespace-nowrap">
                {{ activeSource.rows.length }} baris × {{ activeSource.columns.length }} kolom
              </span>
            </div>
            <div class="flex gap-1.5 shrink-0">
              <button @click="addTable(activeSource)"
                class="px-2.5 py-1 rounded-lg text-xs font-medium bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                ＋ Tabel
              </button>
            </div>
          </div>
          <div class="p-4 space-y-4">
            <!-- Analysis summary -->
            <div v-if="activeSource.analysis || activeSource.aiAnalysis" class="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg p-3">
              <h4 class="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-1 flex items-center gap-1.5"><span>💡</span> Analisa Data</h4>
              <p class="text-xs text-ink-700 dark:text-ink-200 leading-relaxed whitespace-pre-wrap">{{ activeSource.analysis || activeSource.aiAnalysis }}</p>
            </div>
            <div v-if="!activeSource.tables.length" class="text-center py-6 text-sm text-ink-400 dark:text-ink-500">
              Belum ada tabel. Klik <strong>＋ Tabel</strong> untuk membuat tabel dari sumber ini.
            </div>
            <!-- Tables within active source -->
            <div v-for="table in activeSource.tables" :key="table.id"
              class="border border-cream-300 dark:border-ash-600 rounded-xl overflow-hidden">
          <div class="bg-cream-100 dark:bg-ash-850 px-3 py-2 flex items-center justify-between gap-2 border-b border-cream-300 dark:border-ash-600">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-sm leading-none">🗂</span>
              <input v-model="table.name"
                class="text-sm font-semibold text-ink-700 dark:text-ink-100 bg-transparent border border-transparent hover:border-cream-400 dark:hover:border-ash-600 focus:border-navy-500 dark:focus:border-cream-400 focus:bg-white dark:focus:bg-ash-900 rounded px-1.5 py-0.5 outline-none truncate max-w-[12rem]" />
              <span class="text-xs text-ink-500 dark:text-ink-300 shrink-0 whitespace-nowrap">
                {{ table.rows.length }} × {{ table.columns.length }}
              </span>
            </div>
            <div class="flex gap-1.5 shrink-0">
              <button @click="addColumn(table)" class="px-2 py-1 rounded-lg text-xs font-medium text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700">+ Kolom</button>
              <button @click="addRow(table)" class="px-2 py-1 rounded-lg text-xs font-medium text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700">+ Baris</button>
              <button @click="newChart(table)" class="px-2 py-1 rounded-lg text-xs font-medium bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">＋ Grafik</button>
              <button v-if="table.chartIds?.length" @click="updateAllCharts(table)"
                class="px-2 py-1 rounded-lg text-xs font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30">🔄 Update All</button>
              <button @click="confirmDeleteTable(activeSource, table)" class="px-2 py-1 rounded-lg text-xs font-medium text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30">Hapus</button>
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
                        class="absolute -top-1 -right-1 text-red-400 hover:text-red-600 dark:hover:text-red-300 dark:text-red-400 text-xs bg-cream-50 dark:bg-ash-800 rounded-full w-4 h-4 flex items-center justify-center shadow"
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
                      <button @click="removeRow(table, rIdx)" class="text-red-400 dark:text-red-300 hover:text-red-600 dark:hover:text-red-200 text-xs" title="Hapus baris">✕</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- ═══════════ CHART EDITOR v2 ═══════════ -->
            <div v-if="editingTableId === table.id" class="border border-cream-300 dark:border-ash-600 rounded-xl overflow-hidden">
              <div class="bg-cream-100 dark:bg-ash-850 px-4 py-2.5 flex items-center justify-between border-b border-cream-300 dark:border-ash-600">
                <span class="text-sm font-semibold text-ink-700 dark:text-ink-100">Grafik baru</span>
                <button @click="cancelEdit" class="text-ink-400 hover:text-ink-600 dark:hover:text-ink-200 text-sm">✕ Batal</button>
              </div>

              <div class="p-4 space-y-4">
                <!-- Tab: Data | Style -->
                <div class="flex gap-1 border-b border-cream-300 dark:border-ash-600 pb-2">
                  <button @click="editorTab = 'data'"
                    :class="['px-3 py-1.5 rounded-t text-xs font-medium transition-colors',
                      editorTab === 'data' ? 'bg-navy-600 text-cream-50 dark:bg-cream-200 dark:text-ash-900' : 'text-ink-600 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-ash-700']">
                    📊 Data & Tipe
                  </button>
                  <button @click="editorTab = 'style'"
                    :class="['px-3 py-1.5 rounded-t text-xs font-medium transition-colors',
                      editorTab === 'style' ? 'bg-navy-600 text-cream-50 dark:bg-cream-200 dark:text-ash-900' : 'text-ink-600 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-ash-700']">
                    🎨 Tampilan
                  </button>
                </div>

                <!-- ── Data & Type tab ── -->
                <div v-if="editorTab === 'data'" class="space-y-4">
                  <!-- Title -->
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Judul grafik</label>
                    <input v-model="form.title" placeholder="Contoh: Perbandingan Performa Metode"
                      class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm" />
                  </div>

                  <!-- Axis labels -->
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

                  <!-- Column mapping -->
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
                          class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded cursor-pointer transition-colors"
                          :class="form.yCols.includes(i) ? 'bg-navy-600 text-cream-50 dark:bg-cream-200 dark:text-ash-900' : 'bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-300 dark:hover:bg-ash-600'">
                          <input type="checkbox" class="hidden" :value="i" v-model="form.yCols" />
                          {{ col || `Kolom ${i + 1}` }}
                        </label>
                      </div>
                    </div>
                  </div>

                  <!-- Chart type picker (visual grid) -->
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-2">Jenis grafik</label>

                    <!-- Category filters -->
                    <div class="flex gap-1.5 mb-2">
                      <button v-for="cat in chartCategories" :key="cat"
                        @click="chartCategoryFilter = chartCategoryFilter === cat ? '' : cat"
                        :class="['px-2 py-1 rounded text-xs font-medium transition-colors',
                          chartCategoryFilter === cat ? 'bg-navy-600 text-cream-50' : 'bg-cream-200 dark:bg-ash-700 text-ink-600 dark:text-ink-300 hover:bg-cream-300 dark:hover:bg-ash-600']">
                        {{ cat }}
                      </button>
                      <button v-if="chartCategoryFilter"
                        @click="chartCategoryFilter = ''"
                        class="px-2 py-1 rounded text-xs text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30">
                        ✕
                      </button>
                    </div>

                    <div class="grid grid-cols-4 sm:grid-cols-6 gap-2">
                      <button v-for="info in filteredChartKinds" :key="info.key"
                        @click="form.kind = info.key"
                        class="flex flex-col items-center gap-1 p-2 rounded-lg border-2 transition-all text-center"
                        :class="form.kind === info.key
                          ? 'border-navy-600 bg-navy-50 dark:bg-navy-900/30 dark:border-cream-200 shadow-sm'
                          : 'border-cream-300 dark:border-ash-600 hover:border-navy-400 dark:hover:border-cream-400 bg-white dark:bg-ash-800'">
                        <span class="text-lg">{{ info.icon }}</span>
                        <span class="text-[10px] leading-tight font-medium text-ink-700 dark:text-ink-200">{{ info.label }}</span>
                      </button>
                    </div>
                  </div>
                </div>

                <!-- ── Style tab ── -->
                <div v-if="editorTab === 'style'" class="space-y-4">
                  <!-- Color palette -->
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-2">Palet warna</label>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      <button v-for="(colors, name) in colorPalettes" :key="name"
                        @click="form.color_palette = name"
                        class="flex flex-col gap-1 p-2 rounded-lg border-2 transition-all"
                        :class="form.color_palette === name
                          ? 'border-navy-600 dark:border-cream-200 bg-navy-50 dark:bg-navy-900/30'
                          : 'border-cream-300 dark:border-ash-600 hover:border-navy-400 bg-white dark:bg-ash-800'">
                        <div class="flex gap-0.5 h-3 rounded overflow-hidden">
                          <span v-for="(c, ci) in colors.slice(0, 8)" :key="ci"
                            class="flex-1 rounded-sm" :style="{ backgroundColor: c }"></span>
                        </div>
                        <span class="text-[10px] font-medium text-ink-600 dark:text-ink-300 capitalize">{{ name }}</span>
                      </button>
                    </div>
                  </div>

                  <!-- Theme -->
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Tema</label>
                    <div class="flex gap-1.5">
                      <button v-for="t in themeOptions" :key="t.value"
                        @click="form.theme = t.value"
                        :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                          form.theme === t.value ? 'bg-navy-600 text-cream-50 dark:bg-cream-200 dark:text-ash-900' : 'bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-300 dark:hover:bg-ash-600']">
                        {{ t.label }}
                      </button>
                    </div>
                  </div>

                  <!-- Toggles -->
                  <div class="grid grid-cols-2 gap-3">
                    <label class="flex items-center gap-2 text-xs text-ink-700 dark:text-ink-200 cursor-pointer">
                      <input type="checkbox" v-model="form.show_grid" class="rounded" />
                      Tampilkan grid
                    </label>
                    <label class="flex items-center gap-2 text-xs text-ink-700 dark:text-ink-200 cursor-pointer">
                      <input type="checkbox" v-model="form.show_legend" class="rounded" />
                      Tampilkan legend
                    </label>
                    <label class="flex items-center gap-2 text-xs text-ink-700 dark:text-ink-200 cursor-pointer">
                      <input type="checkbox" v-model="form.show_data_labels" class="rounded" />
                      Label data di grafik
                    </label>
                  </div>

                  <!-- Sizes -->
                  <div class="grid grid-cols-3 gap-3">
                    <div>
                      <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Ukuran font</label>
                      <input type="number" v-model.number="form.font_size" min="8" max="18"
                        class="w-full px-2 py-1.5 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded text-sm" />
                    </div>
                    <div>
                      <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Rotasi label X</label>
                      <input type="number" v-model.number="form.rotation_x" min="0" max="90"
                        class="w-full px-2 py-1.5 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded text-sm" />
                    </div>
                    <div>
                      <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">DPI output</label>
                      <select v-model.number="form.dpi"
                        class="w-full px-2 py-1.5 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded text-sm">
                        <option :value="120">120 (standar)</option>
                        <option :value="150">150 (bagus)</option>
                        <option :value="200">200 (tinggi)</option>
                        <option :value="300">300 (cetak)</option>
                      </select>
                    </div>
                  </div>

                  <!-- Legend position -->
                  <div>
                    <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Posisi legend</label>
                    <div class="flex gap-1.5 flex-wrap">
                      <button v-for="pos in legendPositions" :key="pos"
                        @click="form.legend_position = pos"
                        :class="['px-2 py-1 rounded text-xs font-medium transition-colors',
                          form.legend_position === pos ? 'bg-navy-600 text-cream-50' : 'bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-200']">
                        {{ pos }}
                      </button>
                    </div>
                  </div>
                </div>

                <!-- ── LIVE PREVIEW ── -->
                <div class="border border-cream-300 dark:border-ash-600 rounded-xl overflow-hidden">
                  <div class="bg-cream-100 dark:bg-ash-850 px-3 py-2 flex items-center justify-between border-b border-cream-300 dark:border-ash-600">
                    <span class="text-xs font-semibold text-ink-700 dark:text-ink-100">Preview</span>
                    <button @click="refreshPreview(table)"
                      :disabled="previewLoading"
                      class="px-2 py-0.5 rounded text-xs font-medium bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 disabled:opacity-50 active:scale-95 transition-transform">
                      {{ previewLoading ? '⏳ …' : '🔄 Refresh' }}
                    </button>
                  </div>
                  <div class="p-3 bg-white dark:bg-ash-900 flex items-center justify-center min-h-[200px]">
                    <div v-if="previewLoading" class="flex items-center gap-2 text-sm text-ink-500">
                      <span class="inline-block w-4 h-4 border-2 border-cream-300 border-t-navy-600 rounded-full animate-spin"></span>
                      Memuat preview…
                    </div>
                    <div v-else-if="previewError" class="text-sm text-red-500 dark:text-red-400 p-2">{{ previewError }}</div>
                    <img v-else-if="previewImage" :src="previewImage" class="max-w-full h-auto rounded" />
                    <div v-else class="text-xs text-ink-400 dark:text-ink-500 text-center">
                      <p>Klik <strong>🔄 Refresh</strong> untuk melihat preview grafik.</p>
                      <p class="mt-1">Pilih jenis grafik dan kolom data terlebih dahulu.</p>
                    </div>
                  </div>
                </div>

                <!-- Error -->
                <div v-if="editorError" class="p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg text-sm text-red-700 dark:text-red-300">
                  {{ editorError }}
                </div>

                <!-- Actions -->
                <div class="flex gap-2">
                  <button @click="saveChart(table)" :disabled="saving"
                    class="px-4 py-2 bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-medium disabled:opacity-50 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                    {{ saving ? 'Membuat…' : '✓ Buat Grafik' }}
                  </button>
                  <button @click="refreshPreview(table)"
                    class="px-4 py-2 bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-200 rounded-lg text-sm font-medium hover:bg-cream-300 dark:hover:bg-ash-600 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                    🔄 Preview
                  </button>
                  <button @click="cancelEdit"
                    class="px-4 py-2 bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-200 rounded-lg text-sm font-medium hover:bg-cream-300 dark:hover:bg-ash-600 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
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
                  <div class="flex gap-1.5 shrink-0">
                    <button @click="updateChart(table, chart.image_id)"
                      :disabled="updatingCharts.has(chart.image_id)"
                      class="text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-200 text-xs disabled:opacity-50">
                      {{ updatingCharts.has(chart.image_id) ? '⏳' : '🔄' }} Update
                    </button>
                    <button @click="confirmDeleteChart(table, chart.image_id, chart.title || `Grafik ${idx + 1}`)"
                      class="text-red-400 dark:text-red-300 hover:text-red-600 dark:hover:text-red-200 text-xs shrink-0">Hapus</button>
                  </div>
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
      </div>
    </section>
    </div>
    <!-- END 2-column grid -->

    <!-- ── Charts not tied to any table ────────────────────────────── -->
    <section v-if="orphanCharts.length"
      class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden mb-6">
      <div class="px-4 py-3 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-850">
        <span class="text-sm font-semibold text-ink-800 dark:text-ink-100">Grafik lainnya</span>
        <span class="text-xs text-ink-500 dark:text-ink-300 ml-2">(belum terkait tabel)</span>
      </div>
      <div class="p-4 grid sm:grid-cols-2 gap-3">
        <div v-for="(chart, idx) in orphanCharts" :key="chart.image_id"
          class="border border-cream-300 dark:border-ash-600 rounded-xl overflow-hidden">
          <div class="bg-cream-100 dark:bg-ash-850 px-3 py-2 flex items-center justify-between border-b border-cream-300 dark:border-ash-600">
            <span class="text-xs font-semibold text-ink-700 dark:text-ink-100 truncate">
              {{ chart.title || `Grafik ${idx + 1}` }} · {{ chart.kind }}
            </span>
            <button @click="confirmDeleteOrphan(chart.image_id, chart.title || `Grafik ${idx + 1}`)" class="text-red-400 dark:text-red-300 hover:text-red-600 dark:hover:text-red-200 text-xs shrink-0">Hapus</button>
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

    <!-- ── Delete Chart Dialog ─────────────────────────────────────────── -->
    <AppDialog v-if="deleteChartTarget" :open="!!deleteChartTarget" title="Hapus grafik?" @close="deleteChartTarget = null">
      <p class="text-sm text-ink-700 dark:text-ink-200">Hapus "{{ deleteChartTarget.title }}"?</p>
      <template #actions>
        <button @click="deleteChartTarget = null" class="px-3 py-1.5 text-xs rounded border border-cream-300 dark:border-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700">Batal</button>
        <button @click="executeDeleteChart" class="px-3 py-1.5 text-xs rounded bg-rose-600 hover:bg-rose-700 text-white">Hapus</button>
      </template>
    </AppDialog>

    <AppDialog v-if="deleteOrphanTarget" :open="!!deleteOrphanTarget" title="Hapus grafik?" @close="deleteOrphanTarget = null">
      <p class="text-sm text-ink-700 dark:text-ink-200">Hapus "{{ deleteOrphanTarget.title }}"?</p>
      <template #actions>
        <button @click="deleteOrphanTarget = null" class="px-3 py-1.5 text-xs rounded border border-cream-300 dark:border-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700">Batal</button>
        <button @click="executeDeleteOrphan" class="px-3 py-1.5 text-xs rounded bg-rose-600 hover:bg-rose-700 text-white">Hapus</button>
      </template>
    </AppDialog>

    <AppDialog v-if="deleteSourceTarget" :open="!!deleteSourceTarget" title="Hapus sumber data?" @close="deleteSourceTarget = null">
      <p class="text-sm text-ink-700 dark:text-ink-200">
        Hapus sumber <strong>"{{ deleteSourceTarget.source.name }}"</strong> beserta semua tabel dan grafiknya?
      </p>
      <template #actions>
        <button @click="deleteSourceTarget = null" class="px-3 py-1.5 text-xs rounded border border-cream-300 dark:border-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700">Batal</button>
        <button @click="executeDeleteSource" class="px-3 py-1.5 text-xs rounded bg-rose-600 hover:bg-rose-700 text-white">Hapus</button>
      </template>
    </AppDialog>

    <AppDialog v-if="deleteTableTarget" :open="!!deleteTableTarget" title="Hapus tabel?" @close="deleteTableTarget = null">
      <p class="text-sm text-ink-700 dark:text-ink-200">
        Hapus tabel <strong>"{{ deleteTableTarget.table.name }}"</strong> beserta grafiknya?
      </p>
      <template #actions>
        <button @click="deleteTableTarget = null" class="px-3 py-1.5 text-xs rounded border border-cream-300 dark:border-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700">Batal</button>
        <button @click="executeDeleteTable" class="px-3 py-1.5 text-xs rounded bg-rose-600 hover:bg-rose-700 text-white">Hapus</button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import chartsApi, { type AIFormatResult } from '../api/charts'
import { usePaperStore } from '../stores/paper'
import { useUserStateStore } from '../stores/userState'
import AppDialog from './AppDialog.vue'

const store = usePaperStore()
const paperId = computed(() => store.currentPaperId)
const userState = useUserStateStore()

// ─── Model ─────────────────────────────────────────────────────────────
let _uid = 0
function genId(prefix: string) {
  _uid += 1
  return `${prefix}_${Date.now().toString(36)}_${_uid}`
}

const sources = reactive<any[]>([])
const activeSourceId = ref<string | null>(null)

// Auto-select first source if none selected
const activeSource = computed(() => {
  if (activeSourceId.value) {
    const found = sources.find(s => s.id === activeSourceId.value)
    if (found) return found
  }
  // Auto-select first if available
  return sources.length > 0 ? sources[0] : null
})

// Keep activeSourceId in sync
watch(activeSourceId, (id) => {
  if (id && !sources.find(s => s.id === id) && sources.length > 0) {
    activeSourceId.value = sources[0].id
  }
})

// ─── Persistence ────────────────────────────────────────────────────────
const LS_KEY = computed(() => (paperId.value ? `pg_data_sources_${paperId.value}` : ''))

function persist() {
  if (!LS_KEY.value) return
  try {
    localStorage.setItem(LS_KEY.value, JSON.stringify(sources))
  } catch { /* quota */ }
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
              analysis: t.analysis || '',
              description: t.description || '',
              chartIds: Array.isArray(t.chartIds) ? t.chartIds.map((n: any) => Number(n)) : [],
            })),
            analysis: s.analysis || s.aiAnalysis || '',
            aiAnalysis: s.aiAnalysis || s.analysis || '',
            chartImages: s.chartImages || [],
          })
        })
      }
    }
  } catch { /* ignore */ }

  // Legacy migration
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

// ─── Chart kinds from backend ───────────────────────────────────────────
const chartKindsMap = ref<Record<string, any>>({
  line:          { label: "Line Chart",        icon: "📈", category: "basic" },
  bar:           { label: "Bar Chart",         icon: "📊", category: "basic" },
  scatter:       { label: "Scatter Plot",      icon: "⚬",  category: "basic" },
  pie:           { label: "Pie Chart",         icon: "🥧", category: "basic" },
  hist:          { label: "Histogram",         icon: "📊", category: "basic" },
  box:           { label: "Box Plot",          icon: "📦", category: "basic" },
  heatmap:       { label: "Heatmap",           icon: "🗺", category: "basic" },
  area:          { label: "Area Chart",        icon: "📈", category: "advanced" },
  stacked_bar:   { label: "Stacked Bar",       icon: "📊", category: "advanced" },
  stacked_area:  { label: "Stacked Area",      icon: "📈", category: "advanced" },
  donut:         { label: "Donut Chart",       icon: "🍩", category: "advanced" },
  hbar:          { label: "Horizontal Bar",    icon: "📊", category: "advanced" },
  radar:         { label: "Radar / Polar",     icon: "🕸", category: "advanced" },
  waterfall:     { label: "Waterfall",         icon: "💧", category: "advanced" },
  bubble:        { label: "Bubble Chart",      icon: "🫧", category: "advanced" },
  violin:        { label: "Violin Plot",       icon: "🎻", category: "statistical" },
  combo:         { label: "Combo (Bar+Line)",  icon: "📉", category: "advanced" },
})

const chartCategories = ['basic', 'advanced', 'statistical']
const chartCategoryFilter = ref('')

// ─── AI formatting result summary (shown after auto-processing) ──────────
const aiSummary = ref<{ data_overview: string; analysis: string; charts_created: number } | null>(null)

const filteredChartKinds = computed(() => {
  const entries = Object.entries(chartKindsMap.value).map(([key, info]) => ({ key, ...info }))
  if (chartCategoryFilter.value) {
    return entries.filter(e => e.category === chartCategoryFilter.value)
  }
  return entries
})

// ─── Color palettes from backend ────────────────────────────────────────
const colorPalettes = ref<Record<string, string[]>>({
  academic:  ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#65a30d"],
  vibrant:   ["#ef4444", "#3b82f6", "#22c55e", "#eab308", "#a855f7", "#ec4899", "#14b8a6", "#f97316"],
  pastel:    ["#93c5fd", "#86efac", "#fca5a5", "#fde047", "#c4b5fd", "#f9a8d4", "#67e8f9", "#fdba74"],
  monochrome:["#1e293b", "#475569", "#64748b", "#94a3b8", "#cbd5e1", "#334155", "#78716c", "#a8a29e"],
  warm:      ["#dc2626", "#ea580c", "#d97706", "#ca8a04", "#f97316", "#ef4444", "#b91c1c", "#c2410c"],
  cool:      ["#2563eb", "#0891b2", "#7c3aed", "#4f46e5", "#0d9488", "#2dd4bf", "#6366f1", "#8b5cf6"],
  earth:     ["#92400e", "#166534", "#854d0e", "#1e3a5f", "#78350f", "#365314", "#7c2d12", "#134e4a"],
  ocean:     ["#0c4a6e", "#0e7490", "#155e75", "#164e63", "#0369a1", "#0284c7", "#06b6d4", "#22d3ee"],
})

const themeOptions = [
  { value: 'clean', label: 'Clean' },
  { value: 'minimal', label: 'Minimal' },
  { value: 'dark', label: 'Dark' },
  { value: 'classic', label: 'Classic' },
]

const legendPositions = ['best', 'upper right', 'upper left', 'lower right', 'lower left', 'center']

// ─── Load kinds & palettes from backend ─────────────────────────────────
async function loadMeta() {
  if (!paperId.value) return
  try {
    const kindsRes = await chartsApi.getKinds(paperId.value)
    if (kindsRes.kinds) chartKindsMap.value = kindsRes.kinds
  } catch { /* use defaults for kinds */ }
  try {
    const palettesRes = await chartsApi.getPalettes(paperId.value)
    if (palettesRes.palettes) colorPalettes.value = palettesRes.palettes
  } catch { /* use defaults for palettes */ }
}

// ─── Add source ─────────────────────────────────────────────────────────
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
    tables: [{
      id: genId('tbl'),
      name: 'Tabel 1',
      columns: [...cols],
      rows: normRows.map((r) => [...r]),
      chartIds: [] as number[],
    }],
  }
  sources.push(source)
  addingSource.value = false
}


// ─── Save extraction results to sources (for PaperfullTab "Dari Data") ────
function saveExtractionToSources(result: any) {
  if (!result || !result.tables?.length) return
  
  // Build source entry from extraction result
  const allTables = result.tables.map((t: any, i: number) => ({
    id: genId('tbl'),
    name: t.name || `Tabel ${i + 1}`,
    columns: t.columns || [],
    rows: (t.rows || []).map((r: any[]) => r.map((c: any) => (c == null ? '' : String(c)))),
    analysis: t.analysis || '',
    description: t.description || '',
    chartIds: [] as number[],
  }))

  // Build chart image references
  const chartImages = (result.charts || []).map((c: any) => ({
    path: c.url || '',
    title: c.title || 'Grafik',
    kind: c.kind || 'bar',
    imageId: c.image_id,
    tableIndex: c.table_index ?? 0,
  }))

  // Link charts to tables based on table_index from AI
  allTables.forEach((tbl: any, idx: number) => {
    tbl.chartIds = chartImages
      .filter((c: any) => c.tableIndex === idx)
      .map((c: any) => c.imageId)
  })

  // Summary / analysis text
  const analysis = result.summary?.analysis || result.summary?.data_overview || ''

  const sourceName = result.file_names?.join(', ') || 'Hasil Ekstraksi Data'
  
  // Merge columns/rows from first table for quick access
  const firstTable = allTables[0] || { columns: [], rows: [] }

  const source = {
    id: genId('src'),
    name: sourceName,
    type: 'upload',
    columns: firstTable.columns,
    rows: firstTable.rows,
    tables: allTables,
    analysis,
    aiAnalysis: analysis,
    chartImages,
  }

  sources.push(source)
  // Notify PaperfullTab that new data analysis is available
  window.dispatchEvent(new CustomEvent('data-sources-updated'))
}


// ─── File extraction (async worker) ─────────────────────────────────────
// Persist job ID per-paper so we can resume monitoring after navigation
const LS_DATA_JOB_KEY = (pid: string) => `pg_data_job_${pid}`

const extractState = ref<'idle' | 'loading' | 'error'>('idle')
const extractError = ref('')
const pendingFiles = ref<File[]>([])

// Persisted state via userState store (per-paper)
const extractPrompt = computed({
  get: () => userState.get('data.extract_prompt', paperId.value, ''),
  set: (val) => userState.set('data.extract_prompt', paperId.value, val),
})
const extractProgress = ref<{ progress: number; message: string; stage: string }>({ progress: 0, message: '', stage: '' })
let currentJobId: string | null = null
let eventSource: EventSource | null = null

function onFileSelected(e: Event) {
  const files = Array.from((e.target as HTMLInputElement).files || [])
  if (files.length) {
    pendingFiles.value.push(...files)
  }
  ;(e.target as HTMLInputElement).value = ''
}

function onFileDrop(e: DragEvent) {
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length) {
    pendingFiles.value.push(...files)
  }
}

function removePendingFile(idx: number) {
  pendingFiles.value.splice(idx, 1)
}

function clearPendingFiles() {
  pendingFiles.value = []
}

async function startExtraction() {
  if (!paperId.value) {
    extractState.value = 'error'
    extractError.value = 'Simpan paper terlebih dahulu sebelum mengunggah data.'
    return
  }

  if (!pendingFiles.value.length) {
    extractState.value = 'error'
    extractError.value = 'Pilih file terlebih dahulu.'
    return
  }

  extractState.value = 'loading'
  extractError.value = ''
  extractProgress.value = { progress: 0, message: 'Memulai...', stage: 'queued' }

  const formData = new FormData()
  formData.append('prompt', extractPrompt.value)
  for (const file of pendingFiles.value) {
    formData.append('files', file)
  }

  try {
    // Get CSRF token from cookie (same pattern as other API calls)
    const csrf = (document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/) || [])[1] || ''
    const res = await fetch(`/api/papers/${paperId.value}/data-jobs`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: {
        'X-CSRF-TOKEN': csrf,
      },
    })

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.error || 'Gagal memulai job')
    }

    const data = await res.json()
    currentJobId = data.job_id

    // Save job ID per-paper so we can resume after navigation
    if (paperId.value) localStorage.setItem(LS_DATA_JOB_KEY(paperId.value), currentJobId)

    // Start SSE stream for progress
    // Close any existing EventSource first to prevent connection leaks
    closeEventSource()
    // Get access token from cookie (access_token_cookie is the JWT, csrf_access_token is CSRF protection)
    // Cookie-based auth: backend falls through to access_token_cookie when no query token
    // (No JWT in URL — avoids leaking tokens in logs/history)
    eventSource = new EventSource(`/api/data-jobs/${currentJobId}/stream`)

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        extractProgress.value = {
          progress: payload.progress || 0,
          message: payload.message || '',
          stage: payload.stage || '',
        }

        if (payload.status === 'done') {
          // Job completed successfully
          extractState.value = 'idle'
          pendingFiles.value = []
          extractPrompt.value = ''
          // Clear saved job ID
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          // Save extracted tables/charts to sources (for PaperfullTab "Dari Data" picker)
          saveExtractionToSources(payload.result)
          // Reload charts to show new data
          loadCharts()
          // Show success message
          aiSummary.value = {
            data_overview: `Berhasil memproses ${payload.result?.tables?.length || 0} tabel dan ${payload.result?.charts?.length || 0} grafik.`,
            analysis: payload.message || '',
            charts_created: payload.result?.charts?.length || 0,
          }
          closeEventSource()
        } else if (payload.status === 'error') {
          extractState.value = 'error'
          extractError.value = payload.error || 'Gagal memproses data'
          // Clear saved job ID
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          closeEventSource()
        } else if (payload.status === 'cancelled') {
          extractState.value = 'idle'
          // Clear saved job ID
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          closeEventSource()
        }
      } catch (e) {
        console.error('Failed to parse SSE event:', e)
      }
    }

    eventSource.onerror = async () => {
      // SSE connection dropped. Check job status via API to get actual error.
      closeEventSource()
      
      if (!currentJobId) {
        extractState.value = 'error'
        extractError.value = 'Koneksi terputus.'
        return
      }
      
      try {
        const csrf = (document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/) || [])[1] || ''
        const res = await fetch(`/api/data-jobs/${currentJobId}`, {
          credentials: 'include',
          headers: { 'X-CSRF-TOKEN': csrf },
        })
        const data = await res.json()
        
        if (data.status === 'error') {
          extractState.value = 'error'
          extractError.value = data.error || 'Gagal memproses data'
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
        } else if (data.status === 'done') {
          // Job completed while SSE was disconnected
          extractState.value = 'idle'
          pendingFiles.value = []
          extractPrompt.value = ''
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          saveExtractionToSources(data.result)
          loadCharts()
          aiSummary.value = {
            data_overview: `Berhasil memproses ${data.result?.tables?.length || 0} tabel dan ${data.result?.charts?.length || 0} grafik.`,
            analysis: data.message || '',
            charts_created: data.result?.charts?.length || 0,
          }
        } else {
          // Job still running or queued — SSE dropped but job continues
          extractState.value = 'error'
          extractError.value = 'Koneksi terputus. Job masih berjalan. Refresh halaman untuk melanjutkan.'
        }
      } catch (e) {
        extractState.value = 'error'
        extractError.value = 'Koneksi terputus. Job mungkin masih berjalan. Refresh halaman untuk melanjutkan.'
      }
    }

  } catch (e: any) {
    extractState.value = 'error'
    extractError.value = e.message || 'Gagal memproses data'
  }
}

// Text-only extraction (no file required)
async function startTextExtraction() {
  if (!paperId.value) {
    extractState.value = 'error'
    extractError.value = 'Simpan paper terlebih dahulu.'
    return
  }

  if (!extractPrompt.value.trim()) {
    extractState.value = 'error'
    extractError.value = 'Masukkan instruksi atau data teks terlebih dahulu.'
    return
  }

  extractState.value = 'loading'
  extractError.value = ''
  extractProgress.value = { progress: 0, message: 'Memproses teks...', stage: 'queued' }

  const formData = new FormData()
  formData.append('prompt', extractPrompt.value)
  // No files appended — text-only mode

  try {
    const csrf = (document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/) || [])[1] || ''
    const res = await fetch(`/api/papers/${paperId.value}/data-jobs`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: {
        'X-CSRF-TOKEN': csrf,
      },
    })

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.error || 'Gagal memulai job')
    }

    const data = await res.json()
    currentJobId = data.job_id

    if (paperId.value) localStorage.setItem(LS_DATA_JOB_KEY(paperId.value), currentJobId)

    // Close any existing EventSource first to prevent connection leaks
    closeEventSource()

    // Cookie-based auth: backend falls through to access_token_cookie when no query token
    // (No JWT in URL — avoids leaking tokens in logs/history)
    eventSource = new EventSource(`/api/data-jobs/${currentJobId}/stream`)

    // Reuse the same SSE handler as startExtraction
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        extractProgress.value = {
          progress: payload.progress || 0,
          message: payload.message || '',
          stage: payload.stage || '',
        }

        if (payload.status === 'done') {
          extractState.value = 'idle'
          extractPrompt.value = ''
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          saveExtractionToSources(payload.result)
          loadCharts()
          aiSummary.value = {
            data_overview: `Berhasil memproses ${payload.result?.tables?.length || 0} tabel dan ${payload.result?.charts?.length || 0} grafik dari teks.`,
            analysis: payload.message || '',
            charts_created: payload.result?.charts?.length || 0,
          }
          closeEventSource()
        } else if (payload.status === 'error') {
          extractState.value = 'error'
          extractError.value = payload.error || 'Gagal memproses data'
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          closeEventSource()
        } else if (payload.status === 'cancelled') {
          extractState.value = 'idle'
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          closeEventSource()
        }
      } catch (e) {
        console.error('Failed to parse SSE event:', e)
      }
    }

    eventSource.onerror = async () => {
      closeEventSource()
      if (!currentJobId) {
        extractState.value = 'error'
        extractError.value = 'Koneksi terputus.'
        return
      }
      try {
        const csrf = (document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/) || [])[1] || ''
        const res = await fetch(`/api/data-jobs/${currentJobId}`, {
          credentials: 'include',
          headers: { 'X-CSRF-TOKEN': csrf },
        })
        const statusData = await res.json()
        if (statusData.status === 'error') {
          extractState.value = 'error'
          extractError.value = statusData.error || 'Gagal memproses data'
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
        } else if (statusData.status === 'done') {
          extractState.value = 'idle'
          extractPrompt.value = ''
          if (paperId.value) localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          saveExtractionToSources(statusData.result)
          loadCharts()
          aiSummary.value = {
            data_overview: `Berhasil memproses ${statusData.result?.tables?.length || 0} tabel dan ${statusData.result?.charts?.length || 0} grafik dari teks.`,
            analysis: statusData.message || '',
            charts_created: statusData.result?.charts?.length || 0,
          }
        } else {
          extractState.value = 'error'
          extractError.value = 'Koneksi terputus. Job masih berjalan. Refresh halaman untuk melanjutkan.'
        }
      } catch (e) {
        extractState.value = 'error'
        extractError.value = 'Koneksi terputus. Job mungkin masih berjalan. Refresh halaman untuk melanjutkan.'
      }
    }

  } catch (e: any) {
    extractState.value = 'error'
    extractError.value = e.message || 'Gagal memproses data'
  }
}

async function cancelExtraction() {
  if (!currentJobId) return

  try {
    await fetch(`/api/data-jobs/${currentJobId}/cancel`, {
      method: 'POST',
      credentials: 'include',
    })
  } catch (e) {
    // Ignore
  }

  extractState.value = 'idle'
  closeEventSource()
}

function closeEventSource() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  currentJobId = null
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

// Delete source dialog
const deleteSourceTarget = ref<{ source: any } | null>(null)
const deleteTableTarget = ref<{ source: any; table: any } | null>(null)

function confirmDeleteSource(source: any) {
  deleteSourceTarget.value = { source }
}

async function executeDeleteSource() {
  if (!deleteSourceTarget.value) return
  const { source } = deleteSourceTarget.value
  deleteSourceTarget.value = null
  try {
    for (const t of source.tables) {
      for (const id of (t.chartIds || [])) {
        await backendDeleteChart(id)
      }
    }
    const idx = sources.indexOf(source)
    if (idx >= 0) sources.splice(idx, 1)
  } catch (err: any) {
    console.warn('deleteSource failed', err)
  }
}

function confirmDeleteTable(source: any, table: any) {
  deleteTableTarget.value = { source, table }
}

async function executeDeleteTable() {
  if (!deleteTableTarget.value) return
  const { source, table } = deleteTableTarget.value
  deleteTableTarget.value = null
  try {
    for (const id of (table.chartIds || [])) {
      await backendDeleteChart(id)
    }
    const idx = source.tables.indexOf(table)
    if (idx >= 0) source.tables.splice(idx, 1)
  } catch (err: any) {
    console.warn('deleteTable failed', err)
  }
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
const charts = ref<any[]>([])
const chartsLoading = ref(false)
const chartsListError = ref('')
const editingTableId = ref<string | null>(null)
const editorTab = ref<'data' | 'style'>('data')
const saving = ref(false)
const editorError = ref('')

// Delete chart dialog
const deleteChartTarget = ref<{ table: any; chartId: number; title: string } | null>(null)
const deleteOrphanTarget = ref<{ chartId: number; title: string } | null>(null)

// Update chart states
const updatingCharts = ref<Set<number>>(new Set())

// Chart specs storage (for regeneration) — keyed by chartId
const chartSpecStore = reactive<Record<string, Record<number, any>>>({})
function getChartSpecsKey() { return paperId.value ? `pg_chart_specs_${paperId.value}` : '' }
function saveChartSpecs() {
  const key = getChartSpecsKey()
  if (!key) return
  try { localStorage.setItem(key, JSON.stringify(chartSpecStore)) } catch {}
}
function restoreChartSpecs() {
  const key = getChartSpecsKey()
  if (!key) return
  Object.keys(chartSpecStore).forEach(k => delete chartSpecStore[k])
  try {
    const raw = localStorage.getItem(key)
    if (raw) { Object.assign(chartSpecStore, JSON.parse(raw)) }
  } catch {}
}

// Preview state
const previewImage = ref('')
const previewLoading = ref(false)
const previewError = ref('')

const form = reactive({
  kind: 'line',
  title: '',
  xlabel: '',
  ylabel: '',
  xCol: -1,
  yCols: [] as number[],
  // Styling
  color_palette: 'academic',
  theme: 'clean',
  font_size: 11,
  title_font_size: 14,
  show_grid: true,
  show_legend: true,
  legend_position: 'best',
  bar_width: 0.8,
  line_width: 2.0,
  marker_size: 6.0,
  show_data_labels: false,
  rotation_x: 0,
  dpi: 150,
})

function tableCharts(table: any) {
  const byId = new Map(charts.value.map((c) => [c.image_id, c]))
  return (table.chartIds || []).map((id: number) => byId.get(id)).filter(Boolean)
}

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
  previewImage.value = ''
  previewError.value = ''
  editorTab.value = 'data'
  form.kind = 'line'
  form.title = ''
  form.xlabel = table.columns[0] || ''
  form.ylabel = ''
  const firstTextCol = table.columns.findIndex(
    (_c: any, i: number) => table.rows.some((r: any[]) => r[i] !== '' && !isFiniteNumber(r[i]))
  )
  form.xCol = firstTextCol
  form.yCols = defaultYCols(table)
  // Reset styling
  form.color_palette = 'academic'
  form.theme = 'clean'
  form.font_size = 11
  form.show_grid = true
  form.show_legend = true
  form.show_data_labels = false
  form.rotation_x = 0
  form.dpi = 150
  form.legend_position = 'best'
  editingTableId.value = table.id

  // Auto-preview after a short delay
  setTimeout(() => refreshPreview(table), 500)
}

function cancelEdit() {
  editingTableId.value = null
  editorError.value = ''
  previewImage.value = ''
  previewError.value = ''
}

function buildSpec(table: any) {
  const xCol = form.xCol
  const yCols = form.yCols.length ? form.yCols : defaultYCols(table)
  if (!yCols.length) {
    throw new Error('Pilih minimal satu kolom Y (seri numerik).')
  }
  // Detect if Y data is non-numeric (variable mode: a1, a2, b1...)
  const isVariableMode = yCols.some((c: number) =>
    table.rows.some((r: any[]) => r[c] !== '' && !isFiniteNumber(r[c]))
  )
  let data: number[][]
  if (isVariableMode) {
    // Assign sequential placeholder values so chart renders meaningfully
    // Each series gets offset values: series 0 → 1,2,3... series 1 → 10,20,30...
    data = yCols.map((c: number, sIdx: number) =>
      table.rows.map((_r: any[], rIdx: number) => (rIdx + 1) * 10 * (sIdx + 1))
    )
  } else {
    data = yCols.map((c: number) => table.rows.map((r: any[]) => Number(r[c]) || 0))
  }
  const series_labels = yCols.map((c: number) => table.columns[c] || `Seri ${c + 1}`)
  const x_data = xCol >= 0 ? table.rows.map((r: any[]) => r[xCol]) : table.rows.map((_r: any, i: number) => `${i + 1}`)
  return {
    kind: form.kind,
    title: form.title || 'Grafik',
    xlabel: form.xlabel || '',
    ylabel: form.ylabel || '',
    data,
    series_labels,
    x_data,
    color_palette: form.color_palette,
    theme: form.theme,
    font_size: form.font_size,
    title_font_size: form.title_font_size,
    show_grid: form.show_grid,
    show_legend: form.show_legend,
    legend_position: form.legend_position,
    bar_width: form.bar_width,
    line_width: form.line_width,
    marker_size: form.marker_size,
    show_data_labels: form.show_data_labels,
    rotation_x: form.rotation_x,
    dpi: form.dpi,
  }
}

// ─── Preview ────────────────────────────────────────────────────────────
let _previewTimer: ReturnType<typeof setTimeout> | null = null

async function refreshPreview(table: any) {
  if (!paperId.value) return
  previewError.value = ''
  previewLoading.value = true

  try {
    const spec = buildSpec(table)
    const res = await chartsApi.preview(paperId.value, spec)
    previewImage.value = res.image
  } catch (err: any) {
    previewError.value = err.response?.data?.error || err.message || 'Gagal memuat preview.'
    previewImage.value = ''
  } finally {
    previewLoading.value = false
  }
}

// Auto-preview on form changes (debounced)
watch(
  () => [form.kind, form.color_palette, form.theme, form.show_grid, form.show_legend,
         form.show_data_labels, form.font_size, form.rotation_x, form.legend_position],
  () => {
    if (!editingTableId.value) return
    if (_previewTimer) clearTimeout(_previewTimer)
    _previewTimer = setTimeout(() => {
      const table = findEditingTable()
      if (table) refreshPreview(table)
    }, 600)
  }
)

function findEditingTable() {
  for (const s of sources) {
    for (const t of s.tables) {
      if (t.id === editingTableId.value) return t
    }
  }
  return null
}

// ─── Save chart ─────────────────────────────────────────────────────────
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
      // Store spec for future regeneration (with column mapping)
      if (paperId.value) {
        if (!chartSpecStore[paperId.value]) chartSpecStore[paperId.value] = {}
        chartSpecStore[paperId.value][created.image_id] = { ...spec, _xCol: form.xCol, _yCols: [...form.yCols] }
        saveChartSpecs()
      }
    }
    await loadCharts()
    editingTableId.value = null
    previewImage.value = ''
  } catch (err: any) {
    editorError.value = err.response?.data?.error || err.message || 'Gagal membuat grafik.'
  } finally {
    saving.value = false
  }
}

async function backendDeleteChart(chartId: number) {
  if (!paperId.value) return
  await chartsApi.delete(paperId.value, chartId)
}

function confirmDeleteChart(table: any, chartId: number, title: string) {
  deleteChartTarget.value = { table, chartId, title }
}

async function executeDeleteChart() {
  if (!deleteChartTarget.value) return
  const { table, chartId } = deleteChartTarget.value
  try {
    await backendDeleteChart(chartId)
    const idx = table.chartIds.indexOf(chartId)
    if (idx >= 0) table.chartIds.splice(idx, 1)
    await loadCharts()
  } catch (err: any) {
    console.warn('deleteChart failed', err)
  } finally {
    deleteChartTarget.value = null
  }
}

function confirmDeleteOrphan(chartId: number, title: string) {
  deleteOrphanTarget.value = { chartId, title }
}

async function executeDeleteOrphan() {
  if (!deleteOrphanTarget.value) return
  const { chartId } = deleteOrphanTarget.value
  try {
    await backendDeleteChart(chartId)
    await loadCharts()
  } catch (err: any) {
    console.warn('deleteOrphan failed', err)
  } finally {
    deleteOrphanTarget.value = null
  }
}

// ─── Update chart (regenerate with current table data) ─────────────────
async function updateChart(table: any, chartId: number) {
  if (!paperId.value) return
  const spec = chartSpecStore[paperId.value]?.[chartId]
  if (!spec) {
    alert('Tidak ada data tersimpan untuk grafik ini. Silakan buat grafik baru.')
    return
  }
  updatingCharts.value = new Set([...updatingCharts.value, chartId])
  try {
    // Rebuild data arrays from current table content
    const xCol = spec._xCol ?? -1
    const yCols = spec._yCols || []
    const data = yCols.map((c: number) => table.rows.map((r: any[]) => Number(r[c]) || 0))
    const series_labels = yCols.map((c: number) => table.columns[c] || `Seri ${c + 1}`)
    const x_data = xCol >= 0 ? table.rows.map((r: any[]) => r[xCol]) : table.rows.map((_r: any, i: number) => `${i + 1}`)
    const updateSpec = { ...spec, data, series_labels, x_data }
    delete updateSpec._xCol
    delete updateSpec._yCols
    await chartsApi.update(paperId.value, chartId, updateSpec)
    await loadCharts()
  } catch (err: any) {
    console.warn('updateChart failed', err)
  } finally {
    const next = new Set(updatingCharts.value)
    next.delete(chartId)
    updatingCharts.value = next
  }
}

async function updateAllCharts(table: any) {
  if (!paperId.value) return
  const specs = chartSpecStore[paperId.value] || {}
  const ids = (table.chartIds || []).filter((id: number) => specs[id])
  if (!ids.length) {
    alert('Tidak ada grafik yang bisa di-update (belum ada data tersimpan).')
    return
  }
  for (const chartId of ids) {
    await updateChart(table, chartId)
  }
}

async function loadCharts() {
  if (!paperId.value) return
  chartsLoading.value = true
  chartsListError.value = ''
  try {
    const res = await chartsApi.list(paperId.value)
    charts.value = res.charts || []
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
  loadMeta()
  restoreChartSpecs()
})

// Resume monitoring a saved extraction job on mount
async function resumeExtractionJob() {
  if (!paperId.value) return
  const savedJobId = localStorage.getItem(LS_DATA_JOB_KEY(paperId.value))
  if (!savedJobId) return

  // Check if job is still running
  try {
    const res = await fetch(`/api/data-jobs/${savedJobId}`, {
      credentials: 'include',
    })
    if (!res.ok) {
      // Job not found or error - clear saved ID
      localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
      return
    }
    const job = await res.json()
    if (job.status === 'done' || job.status === 'error' || job.status === 'cancelled') {
      // Job already finished - clear saved ID
      localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
      if (job.status === 'done') {
        // Reload charts to show new data
        loadCharts()
      }
      return
    }

    // Job is still running - resume monitoring
    currentJobId = savedJobId
    extractState.value = 'loading'
    extractProgress.value = { progress: job.progress || 0, message: 'Melanjutkan...', stage: job.stage || '' }

    // Reconnect SSE
    // Close any existing EventSource first to prevent connection leaks
    closeEventSource()
    // Cookie-based auth: backend falls through to access_token_cookie when no query token
    // (No JWT in URL — avoids leaking tokens in logs/history)
    eventSource = new EventSource(`/api/data-jobs/${currentJobId}/stream`)

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        extractProgress.value = {
          progress: payload.progress || 0,
          message: payload.message || '',
          stage: payload.stage || '',
        }

        if (payload.status === 'done') {
          extractState.value = 'idle'
          pendingFiles.value = []
          extractPrompt.value = ''
          localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          saveExtractionToSources(payload.result)
          loadCharts()
          aiSummary.value = {
            data_overview: `Berhasil memproses ${payload.result?.tables?.length || 0} tabel dan ${payload.result?.charts?.length || 0} grafik.`,
            analysis: payload.message || '',
            charts_created: payload.result?.charts?.length || 0,
          }
          closeEventSource()
        } else if (payload.status === 'error') {
          extractState.value = 'error'
          extractError.value = payload.error || 'Gagal memproses data'
          localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          closeEventSource()
        } else if (payload.status === 'cancelled') {
          extractState.value = 'idle'
          localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
          closeEventSource()
        }
      } catch (e) {
        console.error('Failed to parse SSE event:', e)
      }
    }

    eventSource.onerror = () => {
      extractState.value = 'error'
      extractError.value = 'Koneksi terputus. Job mungkin masih berjalan di background. Refresh halaman untuk melanjutkan.'
      // Keep the saved job ID — the worker survives a dropped SSE socket, so a
      // later refresh can resume it. Only terminal statuses clear it.
      closeEventSource()
    }
  } catch (e) {
    // Failed to check job - clear saved ID
    localStorage.removeItem(LS_DATA_JOB_KEY(paperId.value))
  }
}

onMounted(() => {
  restore()
  loadCharts()
  loadMeta()
  restoreChartSpecs()
  resumeExtractionJob()
})

onUnmounted(() => {
  closeEventSource()
  if (_previewTimer) clearTimeout(_previewTimer)
})
</script>
