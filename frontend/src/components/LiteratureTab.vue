<template>
  <div class="w-full">
    <div class="bg-white dark:bg-ash-700 rounded-2xl border border-ivory-300 dark:border-ash-500 shadow-sm p-6 space-y-5">
      <!-- Header -->
      <div class="flex items-start justify-between gap-3 flex-wrap">
              <div class="min-w-0">
                <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50 font-serif flex items-center gap-2">
                  <svg class="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M12 8v8"/></svg>
                  Literatur
                </h2>
          <p class="text-sm text-ink-700 dark:text-ash-300 mt-1">
            Tabel referensi paper. Klik baris untuk check/uncheck. Hasil SLR otomatis tersimpan di sini.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button
            @click="triggerPdfUpload"
            :disabled="loading"
            class="px-3 py-1.5 rounded-lg text-xs font-medium bg-ivory-200 hover:bg-ivory-300 dark:bg-ash-600 dark:hover:bg-ash-500 text-ink-900 dark:text-ink-50 disabled:opacity-50"
            title="Upload file PDF untuk ekstraksi metadata dan sinkronisasi"
          >📄 Upload File PDF</button>
          <input
            ref="pdfFileInput"
            type="file"
            multiple
            accept=".pdf,application/pdf"
            class="hidden"
            @change="handlePdfUpload"
          />
          <button
            @click="showAddManual = !showAddManual"
            class="px-3 py-1.5 rounded-lg text-xs font-medium bg-navy-700 hover:bg-navy-800 dark:bg-navy-700 dark:hover:bg-navy-600 text-cream-50 dark:text-ash-900 active:scale-95 transition-transform"
          >＋ Tambah Manual</button>
        </div>
      </div>

      <!-- Inline error banner -->
      <div
        v-if="loadError"
        class="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-3 py-2 text-xs flex items-center justify-between gap-2"
      >
        <span class="text-amber-800 dark:text-amber-200 truncate">{{ loadError }}</span>
        <button
          @click="retryLoad"
          class="px-2 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white text-[11px] font-semibold shrink-0"
        >Coba lagi</button>
      </div>

      <!-- Run SLR -->
      <div ref="slrCardRef" class="rounded-xl border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 p-4">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 font-serif">🔍 Jalankan SLR</h3>
          <span class="text-[10px] text-ink-500 dark:text-ash-300">Multi-source (OpenAlex · Crossref · arXiv · IEEE · SINTA · ...)</span>
        </div>
        <div class="flex flex-col sm:flex-row gap-2">
          <input
            ref="slrInputRef"
            v-model="slrQuery"
            @keyup.enter="runSLR"
            type="text"
            autocomplete="off"
            placeholder="Ketik topik (mis. 'reinforcement learning untuk navigasi AGV')"
            class="flex-1 px-3 py-2 border border-ivory-300 dark:border-ash-500 rounded-lg text-sm bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 placeholder-ivory-500 dark:placeholder-ash-400 focus:ring-2 focus:ring-[#238f7f]/30 outline-none"
            :disabled="slrRunning"
          />
          <select
            v-model.number="slrTopK"
            class="w-24 px-2 py-2 border border-ivory-300 dark:border-ash-500 rounded-lg text-sm bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 text-center"
            :disabled="slrRunning"
            title="Jumlah referensi yang ditampilkan dan di-review AI"
          >
            <option :value="20">20</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
            <option :value="150">150</option>
            <option :value="200">200</option>
          </select>
          <button
            @click="runSLR"
            :disabled="slrRunning || !slrQuery.trim()"
            class="px-4 py-2 rounded-lg text-sm font-semibold bg-navy-700 hover:bg-navy-800 dark:bg-navy-700 dark:hover:bg-navy-600 text-cream-50 dark:text-ash-900 disabled:opacity-50 active:scale-95 transition-transform"
          >
            <span v-if="slrRunning" class="flex items-center gap-1.5">
              <span class="animate-spin inline-block">🔬</span>
              {{ primarySlrStatus }}
            </span>
            <span v-else>Jalankan SLR</span>
          </button>
        </div>

        <!-- Setting button + collapsible panel -->
        <div class="mt-2">
          <button
            @click="showSlrSettings = !showSlrSettings"
            class="px-3 py-1.5 rounded-lg text-xs font-medium bg-ivory-200 hover:bg-ivory-300 dark:bg-ash-600 dark:hover:bg-ash-500 text-ink-700 dark:text-ink-50 active:scale-95 transition-transform"
          >⚙️ Setting {{ showSlrSettings ? '▲' : '▼' }}</button>
          <div v-if="showSlrSettings" class="mt-2 rounded-lg border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-700 p-3 space-y-3">
            <!-- Source checkboxes -->
            <div>
              <div class="text-xs font-medium text-ink-700 dark:text-ash-300 mb-1">Source:</div>
              <div class="flex flex-wrap gap-2">
                <label
                  v-for="src in availableSources"
                  :key="src"
                  class="flex items-center gap-1 text-[11px] text-ink-700 dark:text-ash-300 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    :value="src"
                    v-model="slrSources"
                    class="rounded border-ivory-300 dark:border-ash-500"
                  />
                  {{ src }}
                </label>
              </div>
              <div class="flex gap-2 mt-1">
                <button @click="slrSources = [...availableSources]" class="text-[10px] text-blue-600 dark:text-blue-400 hover:underline">Pilih semua</button>
                <button @click="slrSources = []" class="text-[10px] text-blue-600 dark:text-blue-400 hover:underline">Hapus semua</button>
              </div>
            </div>
            <!-- Year range inputs (horizontal) -->
            <div class="grid grid-cols-2 gap-3">
              <div>
                <div class="text-xs font-medium text-ink-700 dark:text-ash-300 mb-1">Tahun awal:</div>
                <input
                  v-model.number="slrYearFrom"
                  type="number"
                  :min="1900"
                  :max="slrYearTo || new Date().getFullYear() + 1"
                  placeholder="Contoh: 2019"
                  class="w-full px-2 py-1 border border-ivory-300 dark:border-ash-500 rounded-lg text-xs bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50"
                  @blur="validateYearRange"
                />
              </div>
              <div>
                <div class="text-xs font-medium text-ink-700 dark:text-ash-300 mb-1">Tahun akhir:</div>
                <input
                  v-model.number="slrYearTo"
                  type="number"
                  :min="slrYearFrom || 1900"
                  :max="new Date().getFullYear() + 1"
                  placeholder="Contoh: 2024"
                  class="w-full px-2 py-1 border border-ivory-300 dark:border-ash-500 rounded-lg text-xs bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50"
                  @blur="validateYearRange"
                />
              </div>
            </div>
            <div v-if="yearRangeError" class="text-[10px] text-red-500 mt-1">Tahun awal harus ≤ Tahun akhir</div>
            <!-- Page size selector -->
            <div>
              <div class="text-xs font-medium text-ink-700 dark:text-ash-300 mb-1">Tampilkan:</div>
              <input
                v-model="pageSizeInput"
                type="number"
                min="5"
                max="500"
                class="w-20 px-2 py-1 border border-ivory-300 dark:border-ash-500 rounded-lg text-xs bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 text-center"
              />
            </div>
          </div>
        </div>

        <!-- Active jobs -->
        <div v-if="activeJobs.length" class="mt-3 space-y-2">
          <SLRProgressCard
            v-for="job in activeJobs"
            :key="job.id"
            :job="job"
            @cancel="cancelJob(job.id)"
          />
        </div>
      </div>

      <!-- Add manual form -->
      <div v-if="showAddManual" class="rounded-xl border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 p-4 space-y-2">
        <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 font-serif">＋ Tambah Literatur Manual</h3>
        <input v-model="manualForm.title" placeholder="Judul *" autocomplete="off" class="input-sm w-full" />
        <input v-model="manualForm.authors_str" placeholder="Authors (pisah koma)" autocomplete="off" class="input-sm w-full" />
        <div class="grid grid-cols-2 gap-2">
          <input v-model.number="manualForm.year" type="number" placeholder="Year" autocomplete="off" inputmode="numeric" class="input-sm" />
          <input v-model="manualForm.venue" placeholder="Venue / Journal" autocomplete="off" class="input-sm" />
          <input v-model="manualForm.doi" placeholder="DOI" autocomplete="off" class="input-sm" />
          <input v-model="manualForm.url" placeholder="URL" autocomplete="url" inputmode="url" class="input-sm" />
        </div>
        <textarea v-model="manualForm.summary" rows="2" placeholder="Ringkasan / catatan singkat" class="input-sm w-full resize-y"></textarea>
        <div class="flex gap-2 justify-end">
          <button @click="showAddManual = false" class="btn-cancel">Batal</button>
          <button @click="addManual" :disabled="!manualForm.title.trim()" class="btn-primary">Simpan</button>
        </div>
      </div>

      <!-- Review Pinned + Counts + Delete Checked -->
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <div class="text-[11px] text-ink-500 dark:text-ash-300 flex items-center gap-2">
          <button
            @click="reviewAllChecked"
            :disabled="reviewBusy || checkedCount === 0"
            class="px-2 py-1 rounded-lg text-[10px] font-semibold bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50 active:scale-95 transition-transform"
            title="Review semua literatur yang di-check dengan AI"
          >🤖 Review Selected</button>
          <span>{{ filteredItems.length }} / {{ items.length }} literatur</span>
          <button
            @click="clearAllFilters"
            class="px-2 py-1 rounded-lg text-[10px] font-medium bg-gray-500 hover:bg-gray-600 text-white active:scale-95 transition-transform"
            title="Reset semua filter, sort, dan uncheck literatur"
          >Clear all</button>
          <button
            v-if="checkedCount > 0"
            @click="deleteChecked"
            class="px-2 py-1 rounded-lg text-[10px] font-medium bg-red-600 hover:bg-red-700 text-white active:scale-95 transition-transform"
            title="Hapus semua literatur yang di-check"
          >🗑 Hapus ({{ checkedCount }})</button>
        </div>
        
      </div>

      <!-- Search & filter bar -->
      <div class="flex items-center gap-2 flex-wrap">
        <input
          v-model="filter"
          type="text"
          placeholder="Cari judul, penulis, venue..."
          class="flex-1 min-w-[200px] px-2 py-1.5 border border-ivory-300 dark:border-ash-500 rounded-lg text-xs bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 placeholder-ivory-500 dark:placeholder-ash-400 outline-none focus:ring-1 focus:ring-[#238f7f]/30"
        />
        <select
          v-model="filterSource"
          class="px-2 py-1.5 border border-ivory-300 dark:border-ash-500 rounded-lg text-xs bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50"
        >
          <option value="">Semua sumber</option>
          <option v-for="src in availableSources" :key="src" :value="src">{{ src }}</option>
        </select>
        <input
          v-model.number="minYear"
          type="number"
          placeholder="Min tahun"
          :min="1900"
          :max="new Date().getFullYear() + 1"
          class="w-24 px-2 py-1.5 border border-ivory-300 dark:border-ash-500 rounded-lg text-xs bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 placeholder-ivory-500"
        />
      </div>

      <!-- Quick sort buttons -->
      <div class="flex items-center gap-2 flex-wrap">
        <span class="text-xs font-medium text-ink-700 dark:text-ash-300 mr-1">Filter:</span>
        <div class="flex items-center gap-1">
          <button @click="setSort('year')" class="sort-btn" :class="{ active: sortKey === 'year' }">Tahun {{ sortIndicator('year') }}</button>
          <button @click="setSort('citations')" class="sort-btn" :class="{ active: sortKey === 'citations' }">Sitasi {{ sortIndicator('citations') }}</button>
          <button @click="setSort('title')" class="sort-btn" :class="{ active: sortKey === 'title' }">Judul A-Z {{ sortIndicator('title') }}</button>
          <button @click="setSort('authors')" class="sort-btn" :class="{ active: sortKey === 'authors' }">Penulis A-Z {{ sortIndicator('authors') }}</button>
        </div>
        <span class="text-ink-300 dark:text-ash-300 select-none">|</span>
        <div class="flex items-center gap-1">
          <button
            v-if="duplicateCount > 0"
            @click="duplicateMode = duplicateMode === 'show_duplicates' ? 'off' : 'show_duplicates'"
            class="sort-btn"
            :class="{ active: duplicateMode === 'show_duplicates' }"
            title="Tampilkan hanya paper yang duplikat (judul sama)"
          >⚠️ Duplikat ({{ duplicateCount }})</button>
          <button
            v-if="duplicateCount > 0"
            @click="duplicateMode = duplicateMode === 'hide_duplicates' ? 'off' : 'hide_duplicates'"
            class="sort-btn"
            :class="{ active: duplicateMode === 'hide_duplicates' }"
            title="Sembunyikan paper duplikat, tampilkan yang unik saja"
          >✓ Unik</button>
        </div>
      </div>

      <!-- Pagination bar (top) -->
      <div v-if="totalPages > 1" class="flex items-center justify-end gap-2 flex-wrap">
        <div class="text-[11px] text-ink-500 dark:text-ash-300">
          Baris {{ pageOffset + 1 }}–{{ Math.min(pageOffset + pageSize, filteredItems.length) }} dari {{ filteredItems.length }}
        </div>
        <div class="flex items-center gap-1">
          <button
            @click="currentPage = 1"
            :disabled="currentPage <= 1"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700 disabled:opacity-40"
          >««</button>
          <button
            @click="currentPage--"
            :disabled="currentPage <= 1"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700 disabled:opacity-40"
          >« Prev</button>
          <template v-for="p in visiblePageNumbers" :key="'top-' + p">
            <button
              v-if="p !== '...'"
              @click="currentPage = p as number"
              :class="['px-2 py-1 rounded text-[10px] font-medium border transition-colors', currentPage === p ? 'bg-navy-700 text-cream-50 border-navy-700 dark:bg-navy-700 dark:text-ash-900 dark:border-navy-600' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700']"
            >{{ p }}</button>
            <span v-else class="px-1 text-[10px] text-ink-400 dark:text-ash-300">…</span>
          </template>
          <button
            @click="currentPage++"
            :disabled="currentPage >= totalPages"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700 disabled:opacity-40"
          >Next »</button>
          <button
            @click="currentPage = totalPages"
            :disabled="currentPage >= totalPages"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700 disabled:opacity-40"
          >»»</button>
        </div>
      </div>

      <!-- Table -->
      <div class="overflow-x-auto rounded-xl border border-ivory-300 dark:border-ash-500">
        <table class="w-full table-fixed text-sm border-collapse" style="min-width: 1200px;">
          <colgroup>
            <col style="width: 28px" />
            <col style="width: 36px" />
            <col style="width: 22%" />
            <col style="width: 52%" />
            <col style="width: 26%" />
          </colgroup>
          <thead class="bg-ivory-100 dark:bg-ash-700 text-ink-700 dark:text-ash-100 sticky top-0 z-10">
            <tr>
              <th class="px-1 py-2.5 text-left w-5">
                <input
                  type="checkbox"
                  :checked="allVisibleChecked"
                  :indeterminate="someVisibleChecked && !allVisibleChecked"
                  @change="toggleCheckAllVisible"
                  title="Check/uncheck semua di halaman ini"
                />
              </th>
              <th class="px-1 py-2.5 text-left w-7">#</th>
              <th class="px-2 py-2.5 text-left">Judul dan Informasi</th>
              <th class="px-2 py-2.5 text-left">Abstract</th>
              <th class="px-2 py-2.5 text-left w-52">Review &amp; Gap</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && items.length === 0">
              <td colspan="5" class="px-3 py-6 text-center text-ink-500 dark:text-ash-300">Memuat…</td>
            </tr>
            <tr v-else-if="items.length === 0">
              <td colspan="5" class="px-3 py-8 text-center text-ink-500 dark:text-ash-300">
                <div class="space-y-3">
                  <div>Belum ada literatur. Jalankan SLR atau tambah manual untuk mulai.</div>
                  <button
                    v-if="paperTitle"
                    @click="startSLRFromPaperTopic"
                    class="px-3 py-1.5 rounded-lg text-sm font-semibold bg-navy-700 hover:bg-navy-800 dark:bg-navy-700 dark:hover:bg-navy-600 text-cream-50 dark:text-ash-900 active:scale-95 transition-transform"
                  >Jalankan SLR otomatis dari topik paper ini</button>
                </div>
              </td>
            </tr>
            <tr v-else-if="filteredItems.length === 0">
              <td colspan="5" class="px-3 py-8 text-center text-ink-500 dark:text-ash-300">
                Tidak ada literatur yang cocok dengan filter ini. Coba ubah / kosongkan filter.
              </td>
            </tr>
            <template v-else>
              <tr
                v-for="(it, i) in paginatedItems"
                :key="it.id"
                :class="[rowClass(it), { 'ring-2 ring-yellow-400 dark:ring-yellow-500 bg-yellow-50 dark:bg-yellow-900/10': duplicateIds.has(it.id) }]"
                @click="toggleCheck(it)"
              >
                <td class="px-1 py-2.5 align-top text-center" @click.stop>
                  <input
                    type="checkbox"
                    :checked="checkedIds.has(it.id)"
                    @change="toggleCheck(it)"
                    title="Centang = pilih untuk review/delete"
                    class="w-3 h-3 mt-0.5"
                  />
                </td>
                <td class="px-1 py-2.5 align-top text-center text-ink-500 dark:text-ash-300 font-mono text-[11px] pt-1">{{ pageOffset + i + 1 }}</td>
                <!-- Judul dan Informasi -->
                <td class="px-2 py-2 align-top cursor-pointer">
                  <div class="font-medium text-sm text-ink-900 dark:text-ink-50 leading-snug break-words mb-1">
                    {{ it.title }}
                  </div>
                  <div class="text-[11px] text-ink-500 dark:text-ash-300">
                    <span v-if="it.year" class="inline-block">{{ it.year }}</span>
                    <span v-if="it.citations !== null && it.citations !== undefined" class="inline-block">⚡ {{ it.citations }} sitasi</span>
                    <span v-if="it.authors && it.authors.length" class="inline-block" :title="safeAuthorsJoin(it.authors)">👤 {{ formatAuthors(normalizeAuthors(it.authors)) }}</span>
                    <span v-if="it.venue || it.publisher" class="inline-block text-ink-400 dark:text-ash-500 italic">{{ it.venue || it.publisher }}</span>
                  </div>
                  <div v-if="it.doi || it.pdf_url || it.url" class="flex flex-wrap gap-1 mt-1">
                    <button
                      v-if="it.doi"
                      @click.stop="openDoi(it.doi)"
                      class="text-[10px] px-1.5 py-0.5 rounded font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 hover:bg-blue-200"
                    >DOI</button>
                    <button
                      v-if="it.pdf_url"
                      @click.stop="openPdfUrl(it.pdf_url)"
                      class="text-[10px] px-1.5 py-0.5 rounded font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200 hover:bg-emerald-200"
                    >PDF</button>
                    <button
                      v-if="it.url && !it.doi && !it.pdf_url"
                      @click.stop="openUrl(it.url)"
                      class="text-[10px] px-1.5 py-0.5 rounded font-medium bg-gray-100 text-gray-700 dark:bg-gray-900/40 dark:text-gray-300 hover:bg-gray-200"
                    >URL</button>
                  </div>
                </td>
                <!-- Abstract -->
                <td class="px-2 py-2 align-top text-xs text-ink-700 dark:text-ash-300 leading-relaxed">
                  <div v-if="it.abstract">
                    <div class="whitespace-pre-wrap break-words" :class="expandedAbstract.has(it.id) ? '' : 'line-clamp-4'">{{ it.abstract }}</div>
                    <button
                      v-if="isLongText(it.abstract)"
                      @click.stop="toggleExpand('abstract', it.id)"
                      class="text-[10px] text-blue-600 dark:text-blue-400 hover:underline mt-0.5"
                    >{{ expandedAbstract.has(it.id) ? '▲ Ciutkan' : '▼ Selengkapnya' }}</button>
                  </div>
                  <span v-else class="text-ink-400 dark:text-ash-400 italic">—</span>
                </td>
                <!-- Review & Gap -->
                <td class="px-2 py-2 align-top text-xs leading-relaxed">
                  <div v-if="it.summary || it.gap_riset" class="space-y-2">
                    <div v-if="it.summary" class="text-ink-800 dark:text-ash-200">
                      <span class="font-semibold text-purple-700 dark:text-purple-300">Review:</span>
                      <span class="block mt-0.5">{{ it.summary }}</span>
                    </div>
                    <div v-if="it.gap_riset" class="text-ink-800 dark:text-ash-200">
                      <span class="font-semibold text-orange-700 dark:text-orange-300">Gap:</span>
                      <span class="block mt-0.5 italic">{{ it.gap_riset }}</span>
                    </div>
                  </div>
                  <span v-else class="text-ink-400 dark:text-ash-400 italic text-[11px]">Belum direview</span>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- Pagination bar -->
      <div v-if="totalPages > 1" class="flex items-center justify-between gap-2 flex-wrap">
        <div class="text-[11px] text-ink-500 dark:text-ash-300">
          Baris {{ pageOffset + 1 }}–{{ Math.min(pageOffset + pageSize, filteredItems.length) }} dari {{ filteredItems.length }}
        </div>
        <div class="flex items-center gap-1">
          <button
            @click="currentPage = 1"
            :disabled="currentPage <= 1"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700 disabled:opacity-40"
          >««</button>
          <button
            @click="currentPage--"
            :disabled="currentPage <= 1"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700 disabled:opacity-40"
          >« Prev</button>
          <template v-for="p in visiblePageNumbers" :key="'bottom-' + p">
            <button
              v-if="p !== '...'"
              @click="currentPage = p as number"
              :class="['px-2 py-1 rounded text-[10px] font-medium border transition-colors', currentPage === p ? 'bg-navy-700 text-cream-50 border-navy-700 dark:bg-navy-700 dark:text-ash-900 dark:border-navy-600' : 'border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700']"
            >{{ p }}</button>
            <span v-else class="px-1 text-[10px] text-ink-400 dark:text-ash-300">…</span>
          </template>
          <button
            @click="currentPage++"
            :disabled="currentPage >= totalPages"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700 disabled:opacity-40"
          >Next »</button>
          <button
            @click="currentPage = totalPages"
            :disabled="currentPage >= totalPages"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700 disabled:opacity-40"
          >»»</button>
        </div>
      </div>

      <div class="text-[11px] text-ink-500 dark:text-ash-300">
        💡 <strong>Tip:</strong> Klik baris untuk check/uncheck paper. Paper yang di-check bisa direview atau dihapus massal.
      </div>
    </div>
  </div>

  <!-- Centered confirmation dialog -->
  <AppDialog v-if="dg.open" :open="dg.open" :title="dg.title" @close="dg.open = false">
    <p class="text-ink-700 dark:text-ink-200 text-sm whitespace-pre-wrap">{{ dg.message }}</p>
    <template #actions>
      <button @click="dg.onCancel?.(); dg.open = false" class="px-4 py-2.5 min-h-[44px] border border-cream-400 dark:border-ash-500 hover:bg-cream-100 dark:hover:bg-ash-700 text-ink-900 dark:text-ink-50 rounded-xl text-sm font-medium transition-colors">Batal</button>
      <button @click="dg.onConfirm(); dg.open = false" class="px-4 py-2.5 min-h-[44px] bg-[#c43655] hover:bg-[#c43655]/90 text-white rounded-xl text-sm font-medium transition-colors">{{ dg.actionLabel || 'OK' }}</button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { usePaperStore } from '../stores/paper'
import { useLiteratureStore } from '../stores/literature'
import { useUiStore } from '../stores/ui'
import api from '../api/index'
import AppDialog from './AppDialog.vue'
import SLRProgressCard from './SLRProgressCard.vue'

// Centered confirmation dialog state
const dg = reactive({ open: false, title: '', message: '', actionLabel: '', onConfirm: () => {}, onCancel: (() => {}) as (() => void) | undefined })

function askConfirm(title: string, message: string, actionLabel: string, onConfirm: () => void, onCancel?: () => void): void {
  dg.title = title
  dg.message = message
  dg.actionLabel = actionLabel
  dg.onConfirm = onConfirm
  dg.onCancel = onCancel
  dg.open = true
}

interface LiteratureItem {
  id: number
  title: string
  authors?: string[]
  year?: number | null
  venue?: string
  publisher?: string
  doi?: string | null
  url?: string
  pdf_url?: string | null
  abstract?: string
  summary?: string
  source?: string
  source_kind?: string
  score_total?: number
  score_breakdown?: any
  citations?: number
  review?: string
  must_read?: boolean
  is_checked?: boolean
}

interface SLRJob {
  id: string
  query: string
  status: 'queued' | 'running' | 'done' | 'error' | 'pending' | 'cancelled' | 'analyzing' | 'fetching' | 'ranking' | 'summarizing'
  stage?: string
  progress?: number
  progress_message?: string
  queued_at?: string
  finished_at?: string
  sources_completed?: string[]
  sources_running?: string[]
  sources_pending?: string[]
  sources_total?: number
  papers_fetched?: number
  stats?: {
    ai_summary_used?: boolean
    [key: string]: any
  }
  eta_seconds?: number
  eta_display?: string
}

interface ManualForm {
  title: string
  authors_str: string
  year: number | null
  venue: string
  doi: string
  url: string
  summary: string
}

interface FilterState {
  filter: string
  filterSource: string
  minYear: number | null
  pageSize?: number
}

const store = usePaperStore()
const litStore = useLiteratureStore()
const uiStore = useUiStore()
const { currentPaperId } = storeToRefs(store)

const items = ref<LiteratureItem[]>([])
const loading = ref(false)
const loadError = ref('')

const filter = ref('')
const filterSource = ref('')
const minYear = ref<number | null>(null)

const showAddManual = ref(false)

const slrQuery = ref('')
const slrTopK = ref(50)
const slrRunning = ref(false)
const activeJobs = ref<SLRJob[]>([])
const lastSlrJob = ref<SLRJob | null>(null)
const slrCardRef = ref<HTMLElement | null>(null)
let _pollTimer: ReturnType<typeof setTimeout> | null = null
let _extraFastPolls = 0
let _loadItemsInFlight = false
let _userClearedTable = false  // Skip auto-reload after user clicks "Clear all"

// SLR live stream: items that arrived during active SLR
const slrStreamItems = ref<LiteratureItem[]>([])
let _knownIdsBeforeSlr = new Set<number>()

// SSE connections for real-time job progress
const _sseConnections = new Map<string, EventSource>()

// SLR Settings
const showSlrSettings = ref(false)
const availableSources = ref([
  'openalex', 'crossref', 'arxiv', 'ieee', 'semantic_scholar',
  'pubmed', 'sinta', 'scopus', 'dblp', 'europepmc',
  'doaj', 'core', 'lens', 'zenodo', 'hal', 'cambridge',
  'plos', 'sciencedirect', 'openaire', 'datacite',
])
const slrSources = ref<string[]>([])
const slrYearFrom = ref<number | null>(null)
const slrYearTo = ref<number | null>(null)
const yearRangeError = ref(false)

const validateYearRange = () => {
  yearRangeError.value = slrYearFrom.value !== null && slrYearTo.value !== null && slrYearFrom.value > slrYearTo.value
}

const manualForm = ref<ManualForm>({
  title: '', authors_str: '', year: null,
  venue: '', doi: '', url: '', summary: '',
})

// CHECKED state — separate from pinned
const checkedIds = ref<Set<number>>(new Set())
const checkedCount = computed(() => {
  let count = 0
  for (const it of items.value) {
    if (checkedIds.value.has(it.id)) count++
  }
  return count
})

const sortKey = ref<'default' | 'title' | 'year' | 'score' | 'citations' | 'authors'>('default')
const sortDir = ref<'asc' | 'desc'>('desc')

// ── Deteksi duplikat ───────────────────────────────────────────
type DuplicateMode = 'off' | 'show_duplicates' | 'hide_duplicates'
const duplicateMode = ref<DuplicateMode>('off')
const hasActiveFilters = computed(() =>
  filter.value !== '' ||
  filterSource.value !== '' ||
  minYear.value != null ||
  duplicateMode.value !== 'off' ||
  sortKey.value !== 'default'
)

/** Set of IDs yang judulnya muncul lebih dari 1× (case-insensitive, trim). */
const duplicateIds = computed<Set<number>>(() => {
  const norm = new Map<string, number[]>()
  for (const it of items.value) {
    const key = (it.title || '').toLowerCase().trim().replace(/\s+/g, ' ')
    if (!key) continue
    const arr = norm.get(key) || []
    arr.push(it.id)
    norm.set(key, arr)
  }
  const ids = new Set<number>()
  for (const arr of norm.values()) {
    if (arr.length > 1) for (const id of arr) ids.add(id)
  }
  return ids
})

const duplicateCount = computed(() => duplicateIds.value.size)

const reviewingId = ref<number | null>(null)
const reviewBusy = ref(false)

const paperTitle = computed<string>(() => store.paper?.title || '')

// Primary SLR status (for button display)
const primarySlrStatus = computed<string>(() => {
  if (activeJobs.value.length === 0) return 'Mencari…'
  const primary = activeJobs.value[0]
  const stage = primary.stage || primary.status
  const sources = primary.sources_completed?.length || 0
  const total = primary.sources_total || 0
  
  if (stage === 'analyzing') return 'Menganalisis…'
  if (stage === 'fetching') return `Mengambil (${sources}/${total})`
  if (stage === 'summarizing' || stage === 'ranking') return 'Memproses…'
  return 'Mencari…'
})

// Pagination
const pageSize = ref(50)
const pageSizeInput = ref(String(pageSize.value))
const currentPage = ref(1)

// Sync input → pageSize
watch(pageSizeInput, (val) => {
  const n = parseInt(val, 10)
  if (!isNaN(n) && n >= 5 && n <= 500) {
    pageSize.value = n
    currentPage.value = 1
  }
})

// Sync pageSize → input (saat restore dari localStorage)
watch(pageSize, (val) => {
  if (String(val) !== pageSizeInput.value) {
    pageSizeInput.value = String(val)
  }
})

// Expandable abstract — Set of item IDs that are expanded (default = collapsed via line-clamp-4)
const expandedAbstract = ref<Set<number>>(new Set())

function isLongText(text: string | undefined): boolean {
  if (!text) return false
  const lines = text.split('\n')
  // Expand toggle if many lines OR very long single line
  return lines.length > 4 || text.length > 220
}

function toggleExpand(field: 'abstract', id: number): void {
  const set = expandedAbstract
  const next = new Set(set.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  set.value = next
}

const filteredItems = computed<LiteratureItem[]>(() => {
  const q = filter.value.trim().toLowerCase()
  const minY = (minYear.value != null && minYear.value !== '' && Number.isFinite(Number(minYear.value)))
    ? Number(minYear.value)
    : null
  const dupFilters = duplicateMode.value !== 'off'
  // Merge items + slrStreamItems (dedup by title for streaming papers without id)
  const allRaw = [...items.value]
  for (const p of slrStreamItems.value) {
    if (!allRaw.find(i => i.title === p.title)) {
      allRaw.push(p as LiteratureItem)
    }
  }
  return allRaw.filter(it => {
    if (filterSource.value && it.source !== filterSource.value && it.source_kind !== filterSource.value) return false
    if (minY != null && (it.year == null || Number(it.year) < minY)) return false
    // duplicate filter
    if (dupFilters) {
      const isDup = duplicateIds.value.has(it.id)
      if (duplicateMode.value === 'hide_duplicates' && isDup) return false
      if (duplicateMode.value === 'show_duplicates' && !isDup) return false
    }
    if (!q) return true
    const hay = [
      it.title, it.venue, it.publisher, it.doi, it.url, it.pdf_url,
      safeAuthorsJoin(it.authors),
    ].join(' ').toLowerCase()
    return hay.includes(q)
  })
})

const displayedItems = computed<LiteratureItem[]>(() => {
  const arr = filteredItems.value.slice()
  if (sortKey.value === 'default') {
    arr.sort((a, b) => {
      const sa = a.score_total ?? -Infinity
      const sb = b.score_total ?? -Infinity
      if (sa !== sb) return sb - sa
      // Fallback: year desc → citations desc when score_total is equal/null
      const ya = a.year ?? -Infinity
      const yb = b.year ?? -Infinity
      if (ya !== yb) return yb - ya
      const ca = a.citations ?? -Infinity
      const cb = b.citations ?? -Infinity
      return cb - ca
    })
    return arr
  }
  const dir = sortDir.value === 'asc' ? 1 : -1
  arr.sort((a, b) => {
    let va: any, vb: any
    switch (sortKey.value) {
      case 'title':
        va = (a.title || '').toLowerCase()
        vb = (b.title || '').toLowerCase()
        break
      case 'year':
        va = a.year ?? -Infinity
        vb = b.year ?? -Infinity
        break
      case 'score':
        va = a.score_total ?? -Infinity
        vb = b.score_total ?? -Infinity
        break
      case 'citations':
        va = a.citations ?? -Infinity
        vb = b.citations ?? -Infinity
        break
      case 'authors':
        va = (normalizeAuthors(a.authors)[0] || safeAuthorsJoin(a.authors)).toLowerCase()
        vb = (normalizeAuthors(b.authors)[0] || safeAuthorsJoin(b.authors)).toLowerCase()
        break
      default:
        return 0
    }
    if (va < vb) return -1 * dir
    if (va > vb) return 1 * dir
    return 0
  })
  return arr
})

const totalPages = computed(() => Math.max(1, Math.ceil(displayedItems.value.length / pageSize.value)))
const pageOffset = computed(() => (currentPage.value - 1) * pageSize.value)
const paginatedItems = computed(() => {
  const start = pageOffset.value
  return displayedItems.value.slice(start, start + pageSize.value)
})

const visiblePageNumbers = computed(() => {
  const total = totalPages.value
  const cur = currentPage.value
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages: (number | string)[] = [1]
  if (cur > 3) pages.push('...')
  const rangeStart = Math.max(2, cur - 1)
  const rangeEnd = Math.min(total - 1, cur + 1)
  for (let i = rangeStart; i <= rangeEnd; i++) pages.push(i)
  if (cur < total - 2) pages.push('...')
  pages.push(total)
  return pages
})

const allVisibleChecked = computed<boolean>(() => {
  const arr = paginatedItems.value
  if (arr.length === 0) return false
  return arr.every(it => checkedIds.value.has(it.id))
})

const someVisibleChecked = computed<boolean>(() => {
  return paginatedItems.value.some(it => checkedIds.value.has(it.id))
})

function rowClass(it: LiteratureItem): string {
  const classes = ['cursor-pointer', 'transition-colors']
  if (checkedIds.value.has(it.id)) {
    classes.push('bg-blue-50', 'dark:bg-blue-900/20', 'border-l-2', 'border-blue-500')
  }
  // Hover hanya untuk row yang tidak checked
  if (!checkedIds.value.has(it.id)) {
    classes.push('hover:bg-ivory-50/70', 'dark:hover:bg-anthracite-700/20')
  }
  return classes.join(' ')
}

function toast(msg: string, type: 'info' | 'success' | 'error' = 'info'): void {
  if (typeof store.showToast === 'function') store.showToast(msg, type)
  else {
    if (type === 'error') console.error(msg)
    else console.info(msg)
    alert(msg)
  }
}

function safeUrl(u: string | undefined): string {
  if (typeof u !== 'string') return '#'
  return /^(https?:\/\/|\/)/.test(u) ? u : '#'
}

function openDoi(doi: string): void {
  if (!doi) return
  // Strip https://doi.org/ prefix jika ada
  const cleanDoi = doi.replace(/^https?:\/\/(dx\.)?doi\.org\//, '')
  const url = `https://doi.org/${cleanDoi}`
  window.open(url, '_blank', 'noopener,noreferrer')
}

function openPdfUrl(pdfUrl: string): void {
  if (!pdfUrl) return
  const url = safeUrl(pdfUrl)
  if (url === '#') {
    toast('URL PDF tidak valid', 'error')
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

function openUrl(rawUrl: string): void {
  if (!rawUrl) return
  const url = safeUrl(rawUrl)
  if (url === '#') {
    toast('URL tidak valid', 'error')
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

function filterStorageKey(paperId: string): string {
  return `lit.filter.${paperId}`
}

function isAllFiltersDefault(): boolean {
  return !filter.value
    && !filterSource.value
    && (minYear.value == null || minYear.value === '')
    && pageSize.value === 50
}

function saveFilterState(): void {
  if (!currentPaperId.value) return
  try {
    if (isAllFiltersDefault()) {
      localStorage.removeItem(filterStorageKey(currentPaperId.value))
      return
    }
    const payload: FilterState = {
      filter: filter.value,
      filterSource: filterSource.value,
      minYear: minYear.value,
      pageSize: pageSize.value,
    }
    localStorage.setItem(filterStorageKey(currentPaperId.value), JSON.stringify(payload))
  } catch { /* ignore quota / unavailable */ }
}

function loadFilterStateFor(paperId: string): FilterState | null {
  try {
    const raw = localStorage.getItem(filterStorageKey(paperId))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch { return null }
}

function applySavedFilter(saved: FilterState | null): void {
  if (!saved) {
    filter.value = ''
    filterSource.value = ''
    minYear.value = null
    pageSize.value = 50
    pageSizeInput.value = '50'
    return
  }
  filter.value = saved.filter || ''
  filterSource.value = saved.filterSource || ''
  minYear.value = (saved.minYear === '' || saved.minYear == null) ? null : Number(saved.minYear)
  if (typeof saved.pageSize === 'number' && saved.pageSize > 0) {
    pageSize.value = saved.pageSize
    pageSizeInput.value = String(saved.pageSize)
  }
}

let _filterSaveTimer: ReturnType<typeof setTimeout> | null = null
watch(
  [filter, filterSource, minYear, pageSize],
  () => {
    if (_filterSaveTimer) clearTimeout(_filterSaveTimer)
    _filterSaveTimer = setTimeout(() => { saveFilterState() }, 300)
  }
)

async function loadItems(): Promise<void> {
  if (!currentPaperId.value) return
  if (_loadItemsInFlight) return
  _loadItemsInFlight = true
  if (!slrRunning.value) loading.value = true
  try {
    const res = await api.get(`/api/papers/${currentPaperId.value}/literature`)
    const data = res.data
    let fetched: LiteratureItem[] = []
    if (Array.isArray(data)) {
      fetched = data
    } else if (data && Array.isArray(data.items)) {
      fetched = data.items
    }

    // Sync checked state from server (add new, remove stale)
    const fetchedIds = new Set(fetched.map((it: Record<string, any>) => it.id))
    const nextChecked = new Set<number>()
    for (const it of fetched) {
      if (it.is_checked) nextChecked.add(it.id)
    }
    // Only update if different
    const needsUpdate = nextChecked.size !== checkedIds.value.size ||
      Array.from(checkedIds.value).some(id => !nextChecked.has(id)) ||
      Array.from(nextChecked).some(id => !checkedIds.value.has(id))
    if (needsUpdate) checkedIds.value = nextChecked

    if (slrRunning.value) {
      const existingMap = new Map(items.value.map(i => [i.id, i]))
      const newItems: LiteratureItem[] = []
      for (const item of fetched) {
        if (existingMap.has(item.id)) {
          Object.assign(existingMap.get(item.id)!, item)
        } else {
          newItems.push(item)
        }
      }
      if (newItems.length > 0) {
        items.value = [...items.value, ...newItems]
        slrStreamItems.value = [...slrStreamItems.value, ...newItems].slice(-50)
      }
    } else {
      items.value = fetched
    }
    loadError.value = ''
  } catch (e: any) {
    loadError.value = 'Gagal memuat literatur: ' + (e?.response?.data?.error || e?.message || 'network error')
  } finally {
    loading.value = false
    _loadItemsInFlight = false
  }
}

const _lastJobIds = ref<Set<number>>(new Set())
let _lastJobStatus: Record<number, string> = {}
let _consecutiveFailures = 0
let _waitCursor = 0
const _TRANSIENT_STATUSES = new Set([0, 408, 429, 502, 503, 504, 520, 521, 522, 523, 524])
let _slrGraceUntil = 0

async function loadJobs(): Promise<void> {
  if (!currentPaperId.value) return
  try {
    const hasRunning = activeJobs.value.some(
      j => j.status === 'running' || j.status === 'pending' || j.status === 'queued'
    )
    const useLongPoll = hasRunning && _consecutiveFailures < 2
    let jobs: SLRJob[]
    if (useLongPoll) {
      const res = await api.get(`/api/papers/${currentPaperId.value}/slr/jobs/wait`, {
        params: { after: _waitCursor },
        timeout: 35000,
      })
      const data = res.data || {}
      if (data.noop) {
        _consecutiveFailures = 0
        if (loadError.value) loadError.value = ''
        return
      }
      jobs = Array.isArray(data.jobs) ? data.jobs : []
      _waitCursor = typeof data.ts === 'number' ? data.ts : _waitCursor
    } else {
      const res = await api.get(`/api/papers/${currentPaperId.value}/slr/jobs`)
      jobs = Array.isArray(res.data) ? res.data : []
    }
    const active = jobs.filter(j => 
      j.status === 'queued' || j.status === 'running' || j.status === 'pending' ||
      j.status === 'analyzing' || j.status === 'fetching' || j.status === 'ranking' || j.status === 'summarizing'
    ).sort((a, b) => {
      const ta = new Date(a.queued_at || 0).getTime()
      const tb = new Date(b.queued_at || 0).getTime()
      return tb - ta
    })
    activeJobs.value = active.length > 0 ? [active[0]] : []
    const finished = jobs
      .filter(j => j.status === 'done' || j.status === 'error')
      .sort((a, b) => {
        const ta = new Date(a.finished_at || a.queued_at || 0).getTime()
        const tb = new Date(b.finished_at || b.queued_at || 0).getTime()
        return tb - ta
      })
    lastSlrJob.value = finished[0] || null
    const newlyDone = jobs.filter(j =>
      j.status === 'done' &&
      (!_lastJobIds.value.has(j.id) || _lastJobStatus[j.id] !== 'done')
    )
    const justFinished = jobs.some(j =>
      (j.status === 'done' || j.status === 'error') &&
      (!_lastJobIds.value.has(j.id) || _lastJobStatus[j.id] !== j.status)
    )
    if (justFinished) {
      if (_userClearedTable) {
        _userClearedTable = false  // Reset flag, allow future auto-reloads
      } else {
        _extraFastPolls = 1
        await loadItems()
        if (newlyDone.length > 0) {
          const newCount = _knownIdsBeforeSlr
            ? items.value.filter(i => !_knownIdsBeforeSlr.has(i.id)).length
            : items.value.length
          toast(`SLR selesai. ${newCount} literatur masuk.`, 'success')
          try {
            const { useChatStore } = await import('../stores/chat')
            const chatStore = useChatStore()
            const j = newlyDone[0]
            const q = j?.query || ''
            const body = [
              `✅ **SLR selesai.** ${newCount} literatur berhasil dikumpulkan`,
              q ? ` untuk query *"${q}"*.` : '.',
              '',
              'Mau lanjut yang mana?',
              '[OPSI]',
              'Lanjutkan generate paper lengkap dengan literatur ini',
              'Lihat & pilih literatur dulu (pin must-read)',
              'Tambahkan keyword lain untuk SLR berikutnya',
              'Cukup, saya akan ketik permintaan sendiri',
              '[/OPSI]',
            ].join('\n')
            chatStore.injectAssistantMessage?.(body)
          } catch (e) {
            // Silent
          }
        }
      }
    }
    const wasRunning = slrRunning.value
    const hasActive = active.length > 0
    const inGrace = Date.now() < _slrGraceUntil
    slrRunning.value = hasActive || (wasRunning && inGrace)
    if (!wasRunning && slrRunning.value) {
      _knownIdsBeforeSlr = new Set(items.value.map(i => i.id))
    }
    // Connect SSE for any active jobs that don't have an SSE connection yet
    for (const j of active) {
      if (!_sseConnections.has(j.id)) {
        connectSSE(j.id)
      }
    }
    // Disconnect SSE for jobs that are no longer active
    for (const [id] of _sseConnections) {
      if (!active.find(j => j.id === id)) {
        disconnectSSE(id)
      }
    }
    _lastJobIds.value = new Set(jobs.map(j => j.id))
    _lastJobStatus = Object.fromEntries(jobs.map(j => [j.id, j.status]))
    _consecutiveFailures = 0
    if (loadError.value) loadError.value = ''
  } catch (e: any) {
    const status = e?.response?.status ?? 0
    const code = e?.response?.data?.code
    const transient = _TRANSIENT_STATUSES.has(status) || code === 'DB_BUSY'
    _consecutiveFailures++
    _extraFastPolls = Math.max(_extraFastPolls, 2)
    if (transient && activeJobs.value.length > 0) {
      loadItems().catch(() => { /* swallow */ })
    }
    if (_consecutiveFailures < 3) {
      return
    }
    loadError.value = 'Sambungan ke server lambat. Coba lagi?'
  }
}

async function retryLoad(): Promise<void> {
  loadError.value = ''
  _consecutiveFailures = 0
  try { await loadItems() } catch { /* handled in loadItems */ }
  try { await loadJobs() } catch { /* handled in loadJobs */ }
}

function schedulePoll(): void {
  if (_pollTimer) clearTimeout(_pollTimer)
  let delay: number
  if (typeof document !== 'undefined' && document.hidden) {
    delay = 5000
  } else if (activeJobs.value.length > 0) {
    delay = 2500
  } else if (_extraFastPolls > 0) {
    _extraFastPolls--
    delay = 2500
  } else {
    delay = 30000
  }
  _pollTimer = setTimeout(async () => {
    const hasActive = activeJobs.value.some(
      j => j.status === 'running' || j.status === 'pending' || j.status === 'queued'
    )
    await loadJobs()
    if (hasActive && !_userClearedTable) {
      await loadItems()
    }
    schedulePoll()
  }, delay + Math.floor(Math.random() * 500))
}

function _onVisibilityChange(): void {
  schedulePoll()
}

async function runSLR(): Promise<void> {
  const q = slrQuery.value.trim()
  if (!q || !currentPaperId.value) return
  // Token estimation: top_n papers × ~150 tokens/paper (400ch abstract + review)
  const estTokens = slrTopK.value * 150
  const estTokensStr = estTokens >= 1000 ? `${(estTokens / 1000).toFixed(1)}K` : `${estTokens}`
  askConfirm(
    'Konfirmasi SLR',
    `Topik: "${q}"\nJumlah referensi: ${slrTopK.value}\nEstimasi token: ~${estTokensStr} (prompt + AI review untuk ${slrTopK.value} paper teratas)\n\nToken aktual dihitung per referensi yang berhasil di-fetch (bisa lebih sedikit).`,
    'Jalankan SLR',
    async () => {
      slrRunning.value = true
      _userClearedTable = false
      _slrGraceUntil = Date.now() + 5000
      _knownIdsBeforeSlr = new Set(items.value.map(i => i.id))
      slrStreamItems.value = []
      try {
        const res = await api.post(`/api/papers/${currentPaperId.value}/slr/jobs`, {
          query: q,
          top_k: slrTopK.value,
          sources: slrSources.value.length ? slrSources.value : undefined,
          year_from: slrYearFrom.value || null,
          year_to: slrYearTo.value || null,
        })
        const jobId = res.data?.job_id || res.data?.id
        if (jobId) {
          connectSSE(jobId)
        }
        await loadJobs()
        schedulePoll()
      } catch (e: any) {
        const msg = e?.response?.data?.error || e?.message || 'SLR failed'
        toast('SLR error: ' + msg, 'error')
        slrRunning.value = false
      }
    },
    () => { /* user cancelled — do nothing */ }
  )
}

async function cancelJob(jobId: string): Promise<void> {
  askConfirm('Hentikan SLR?', 'Job akan dihentikan. Hasil parsial akan dihilangkan.', 'Hentikan', async () => {
    try {
      await api.delete(`/api/slr/jobs/${jobId}`)
      disconnectSSE(jobId)
      await loadJobs()
    } catch (e: any) {
      toast('Cancel failed: ' + (e?.response?.data?.error || e?.message || ''), 'error')
    }
  })
}

// ── SSE real-time streaming for SLR jobs ──────────────────────────────
function connectSSE(jobId: string): void {
  if (_sseConnections.has(jobId)) return
  try {
    const es = new EventSource(`/api/slr/jobs/${jobId}/stream?token=${encodeURIComponent(document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/)?.[1] || '')}`)
    
    es.addEventListener('snapshot', (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data)
        // Update activeJobs with snapshot
        const job = activeJobs.value.find(j => j.id === jobId)
        if (job) {
          job.status = data.status || job.status
          job.stage = data.stage || job.stage
          job.progress = data.percent || job.progress
          job.papers_fetched = data.papers_count || job.papers_fetched
          // ETA fields
          job.eta_seconds = data.eta_seconds ?? job.eta_seconds
          job.eta_display = data.eta_display ?? job.eta_display
        }
      } catch { /* ignore parse error */ }
    })
    
    es.addEventListener('progress', (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data)
        // Update activeJobs with real-time progress
        const job = activeJobs.value.find(j => j.id === jobId)
        if (job) {
          job.status = data.status || job.status
          job.stage = data.stage || job.stage
          job.progress = data.progress_pct || job.progress
          job.stage_detail = data.stage_detail || job.stage_detail
          job.papers_fetched = data.papers_fetched || job.papers_fetched
          job.all_papers_count = data.all_papers_count || job.all_papers_count
          job.sources_completed = data.sources_completed || job.sources_completed
          job.sources_running = data.sources_running || job.sources_running
          job.sources_pending = data.sources_pending || job.sources_pending
          job.sources_total = data.sources_total || job.sources_total
          // ETA fields
          job.eta_seconds = data.eta_seconds ?? job.eta_seconds
          job.eta_display = data.eta_display ?? job.eta_display
          // Also update primarySlrStatus computed
          slrRunning.value = true
        }
      } catch { /* ignore */ }
    })
    
    es.addEventListener('partial', (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data)
        // Update job papers count
        const job = activeJobs.value.find(j => j.id === jobId)
        if (job) {
          job.papers_fetched = data.papers_count || job.papers_fetched
        }
        // Add new partial papers to the stream
        if (data.new_papers && Array.isArray(data.new_papers)) {
          for (const paper of data.new_papers) {
            if (paper.title && !slrStreamItems.value.find(p => p.title === paper.title)) {
              // Add as a temporary display item in the table
              slrStreamItems.value.push(paper)
            }
          }
        }
      } catch { /* ignore */ }
    })
    
    es.addEventListener('done', (ev: MessageEvent) => {
      try {
        const data = JSON.parse(ev.data)
        // Mark terminal FIRST so loadJobs won't reconnect SSE
        const job = activeJobs.value.find(j => j.id === jobId)
        if (job) {
          job.status = data.status || job.status || 'done'
          job.progress = 100
        }
        disconnectSSE(jobId)
        slrRunning.value = false
        // Give backend a moment to finalize DB, then reload
        setTimeout(async () => {
          await loadJobs()
          await loadItems()
          // Clear streamed items — real data now in items.value
          slrStreamItems.value = []
        }, 500)
      } catch { /* ignore */ }
    })
    
    es.onerror = () => {
      // Close immediately to prevent native auto-reconnect (would duplicate)
      es.close()
      _sseConnections.delete(jobId)
      // Reconnect after 3s if job is still active
      setTimeout(() => {
        if (activeJobs.value.some(j => j.id === jobId && (j.status === 'running' || j.status === 'pending' || j.status === 'queued' || j.status === 'fetching' || j.status === 'summarizing' || j.status === 'analyzing'))) {
          connectSSE(jobId)
        }
      }, 3000)
    }
    
    _sseConnections.set(jobId, es)
  } catch {
    // SSE not supported or network error — fall back to polling
  }
}

function disconnectSSE(jobId: string): void {
  const es = _sseConnections.get(jobId)
  if (es) {
    es.close()
    _sseConnections.delete(jobId)
  }
}

function disconnectAllSSE(): void {
  for (const [id, es] of _sseConnections) {
    es.close()
  }
  _sseConnections.clear()
}

async function startSLRFromPaperTopic(): Promise<void> {
  const title = paperTitle.value
  if (!title) return
  slrQuery.value = title
  await nextTick()
  if (slrCardRef.value && typeof slrCardRef.value.scrollIntoView === 'function') {
    slrCardRef.value.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  await runSLR()
}

const pdfFileInput = ref<HTMLInputElement | null>(null)

function triggerPdfUpload(): void {
  pdfFileInput.value?.click()
}

async function handlePdfUpload(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (!files || files.length === 0 || !currentPaperId.value) return
  
  loading.value = true
  try {
    const formData = new FormData()
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i])
    }
    
    const res = await api.post(`/api/papers/${currentPaperId.value}/literature/upload-pdf`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    
    const data = res?.data || {}
    const createdCount = (data.created || []).length
    const matchedCount = (data.matched || []).length
    const total = data.total || 0
    
    if (total === 0) {
      toast('Tidak ada file yang berhasil diupload', 'info')
    } else {
      const parts: string[] = []
      if (createdCount > 0) parts.push(`${createdCount} literatur baru`)
      if (matchedCount > 0) parts.push(`${matchedCount} file cocok dengan SLR`)
      toast(`\u2705 ${parts.join(', ')} ditambahkan`, 'success')
    }
    
    await loadItems()
  } catch (e: any) {
    toast('Upload gagal: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  } finally {
    loading.value = false
    if (pdfFileInput.value) {
      pdfFileInput.value.value = ''
    }
  }
}

function validateManual(f: ManualForm): boolean {
  if (f.doi) {
    const d = f.doi.trim()
    if (d && !/^10\.\d{4,9}\//.test(d)) {
      toast('DOI tidak valid (format: 10.XXXX/...)', 'error')
      return false
    }
  }
  if (f.url) {
    const u = f.url.trim()
    if (u && !/^https?:\/\//.test(u)) {
      toast('URL harus diawali http:// atau https://', 'error')
      return false
    }
  }
  if (f.year != null && f.year !== '') {
    const y = Number(f.year)
    const max = new Date().getFullYear() + 1
    if (!Number.isFinite(y) || y < 1500 || y > max) {
      toast(`Year harus antara 1500 dan ${max}`, 'error')
      return false
    }
  }
  return true
}

async function addManual(): Promise<void> {
  if (!manualForm.value.title.trim() || !currentPaperId.value) return
  const f = manualForm.value
  if (!validateManual(f)) return
  const authors = f.authors_str
    .split(',').map(a => a.trim()).filter(Boolean)
  try {
    await api.post(`/api/papers/${currentPaperId.value}/literature`, {
      title: f.title.trim(),
      authors,
      year: f.year || null,
      venue: f.venue.trim() || '',
      doi: f.doi.trim() || null,
      url: f.url.trim() || '',
      summary: f.summary.trim() || '',
      source_kind: 'manual',
      source: 'manual',
    })
    manualForm.value = { title: '', authors_str: '', year: null,
                          venue: '', doi: '', url: '', summary: '' }
    showAddManual.value = false
    await loadItems()
    toast('Literatur ditambahkan', 'success')
  } catch (e: any) {
    toast('Tambah gagal: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  }
}

async function deleteItem(it: LiteratureItem): Promise<void> {
  if (!currentPaperId.value) return
  askConfirm('Hapus literatur?', `"${it.title?.slice(0, 80) || 'literatur ini'}" akan dihapus permanen.`, 'Hapus', async () => {
    try {
      await api.delete(`/api/papers/${currentPaperId.value}/literature/${it.id}`)
      const next = new Set(checkedIds.value)
      next.delete(it.id)
      checkedIds.value = next
      await loadItems()
      toast('Dihapus', 'success')
    } catch (e: any) {
      toast('Hapus gagal: ' + (e?.response?.data?.error || e?.message || ''), 'error')
    }
  })
}

// CHECKED functions
function toggleCheck(it: LiteratureItem): void {
  const next = new Set(checkedIds.value)
  const newVal = !next.has(it.id)
  if (newVal) next.add(it.id)
  else next.delete(it.id)
  checkedIds.value = next
  // Sync ke backend
  if (currentPaperId.value) {
    api.patch(`/api/papers/${currentPaperId.value}/literature/${it.id}`, {
      is_checked: newVal,
    }).catch(() => { /* silent */ })
  }
}

function toggleCheckAllVisible(): void {
  if (allVisibleChecked.value) {
    // Uncheck all
    const next = new Set(checkedIds.value)
    for (const it of paginatedItems.value) next.delete(it.id)
    checkedIds.value = next
    // Bulk sync
    if (currentPaperId.value) {
      const ids = paginatedItems.value.map(it => it.id)
      api.post(`/api/papers/${currentPaperId.value}/literature/bulk-patch`, {
        ids,
        patch: { is_checked: false },
      }).catch(() => {})
    }
  } else {
    // Check all
    const next = new Set(checkedIds.value)
    for (const it of paginatedItems.value) next.add(it.id)
    checkedIds.value = next
    if (currentPaperId.value) {
      const ids = paginatedItems.value.map(it => it.id)
      api.post(`/api/papers/${currentPaperId.value}/literature/bulk-patch`, {
        ids,
        patch: { is_checked: true },
      }).catch(() => {})
    }
  }
}

function clearAllFilters(): void {
  askConfirm('Kosongkan tabel?', 'Semua literatur akan dihapus permanen dari database. Jalankan SLR baru untuk mengumpulkan ulang.', 'Kosongkan', async () => {
    _userClearedTable = true  // Prevent auto-reload from re-populating
    items.value = []
    slrStreamItems.value = []
    checkedIds.value = new Set()
    filter.value = ''
    filterSource.value = ''
    minYear.value = null
    pageSize.value = 50
    pageSizeInput.value = '50'
    duplicateMode.value = 'off'
    sortKey.value = 'default'
    sortDir.value = 'desc'
    currentPage.value = 1
    if (currentPaperId.value) {
      localStorage.removeItem(filterStorageKey(currentPaperId.value))
      // Delete from DB so they don't reappear on next loadItems/SLR
      try {
        await api.post(`/api/papers/${currentPaperId.value}/literature/clear`)
      } catch { /* silent — UI already cleared */ }
    }
  })
}

async function deleteChecked(): Promise<void> {
  const ids = Array.from(checkedIds.value)
  if (ids.length === 0 || !currentPaperId.value) return
  askConfirm('Hapus literatur?', `Hapus ${ids.length} literatur yang di-check?\nTindakan ini tidak bisa dibatalkan.`, 'Hapus', async () => {
    try {
      const res = await api.post(`/api/papers/${currentPaperId.value}/literature/bulk-delete`, { ids })
      const deleted = res.data?.deleted || 0
      checkedIds.value = new Set()
      await loadItems()
      toast(`Dihapus ${deleted} literatur`, 'success')
    } catch (e: any) {
      toast('Hapus gagal: ' + (e?.response?.data?.error || e?.message || 'coba lagi'), 'error')
      await loadItems()
    }
  })
}

function setSort(key: 'default' | 'title' | 'year' | 'score' | 'citations' | 'authors'): void {
  if (sortKey.value !== key) {
    sortKey.value = key
    sortDir.value = (key === 'title' || key === 'authors') ? 'asc' : 'desc'
    currentPage.value = 1
    return
  }
  if (sortDir.value === 'desc') {
    sortDir.value = 'asc'
  } else if (sortDir.value === 'asc') {
    sortKey.value = 'default'
    sortDir.value = 'desc'
  }
  currentPage.value = 1
}

function sortIndicator(key: string): string {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'asc' ? ' ▲' : ' ▼'
}

function normalizeAuthors(authors: unknown): string[] {
  if (!authors) return []
  if (Array.isArray(authors)) return authors as string[]
  if (typeof authors === 'string') {
    // Backend kadang serialize authors sebagai comma-separated string
    return authors.split(',').map(s => s.trim()).filter(Boolean)
  }
  return []
}

function safeAuthorsJoin(authors: unknown): string {
  const arr = normalizeAuthors(authors)
  return arr.length ? arr.join(', ') : ''
}

function formatAuthors(authors: string[] | undefined): string {
  if (!authors || authors.length === 0) return '\u2013'
  if (authors.length <= 3) return authors.join(', ')
  return `${authors.slice(0, 3).join(', ')}, et al.`
}

async function reviewAllChecked(): Promise<void> {
  if (!currentPaperId.value) return
  const checked = items.value.filter(it => checkedIds.value.has(it.id))
  if (checked.length === 0) {
    toast('Tidak ada literatur yang di-check', 'info')
    return
  }
  
  const doReview = () => {
    litStore.setIntent({
      action: 'review_checked',
      items: checked.map(it => ({
        id: it.id,
        title: it.title,
        authors: it.authors || [],
        year: it.year,
        publisher: it.publisher || it.venue || '',
        doi: it.doi,
        abstract: it.abstract || '',
        citations: it.citations || 0,
      })),
      query: slrQuery.value || paperTitle.value || '',
    })
    // Open floating AI Assistant (not the old right-panel chat)
    window.dispatchEvent(new CustomEvent('open-ai-assistant'))
    toast(`${checked.length} literatur siap di-review di AI Assistant`, 'success')
  }
  
  reviewBusy.value = true
  const checkedDuplicates = checked.filter(it => duplicateIds.value.has(it.id))
  if (checkedDuplicates.length > 0) {
    askConfirm('Paper duplikat terdeteksi',
      `${checkedDuplicates.length} paper duplikat terdeteksi!\nIni dapat mempengaruhi kualitas analisis.\n\nTetap lanjutkan review?`,
      'Lanjutkan',
      () => { doReview(); reviewBusy.value = false },
      () => { reviewBusy.value = false },
    )
  } else {
    doReview()
    reviewBusy.value = false
  }
}

function applyIntent(intent: any): void {
  if (!intent) return
  if (intent.query) slrQuery.value = intent.query
  if (intent.top_k) slrTopK.value = intent.top_k
  if (intent.job_id && !activeJobs.value.find(j => j.id === intent.job_id)) {
    activeJobs.value = [{
      id: intent.job_id,
      query: intent.query,
      status: 'queued',
      progress: 0,
      progress_message: 'Starting\u2026',
    }, ...activeJobs.value]
    slrRunning.value = true
  }
  loadJobs().finally(() => schedulePoll())
}

watch(currentPaperId, async (id) => {
  _lastJobIds.value = new Set()
  _lastJobStatus = {}
  _consecutiveFailures = 0
  _waitCursor = 0
  activeJobs.value = []
  lastSlrJob.value = null
  checkedIds.value = new Set()
  slrStreamItems.value = []
  expandedAbstract.value = new Set()
  loadError.value = ''
  currentPage.value = 1
  applySavedFilter(id ? loadFilterStateFor(id) : null)
  if (id) {
    try { await loadItems() } catch { /* handled in loadItems */ }
    try { await loadJobs() } catch { /* handled in loadJobs */ }
    schedulePoll()
  }
})

watch(() => litStore.pendingIntent, (intent) => {
  if (!intent) return
  // Jangan consume review_checked — ChatTab yang handle
  if (intent.action === 'review_checked') return
  applyIntent(litStore.consumeIntent())
})

onMounted(async () => {
  if (currentPaperId.value) {
    applySavedFilter(loadFilterStateFor(currentPaperId.value))
    try { await loadItems() } catch { /* handled in loadItems */ }
    try { await loadJobs() } catch { /* handled in loadJobs */ }
  }
  applyIntent(litStore.consumeIntent())
  schedulePoll()
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', _onVisibilityChange)
  }
})

onUnmounted(() => {
  if (_pollTimer) clearTimeout(_pollTimer)
  if (_filterSaveTimer) clearTimeout(_filterSaveTimer)
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', _onVisibilityChange)
  }
  disconnectAllSSE()
})
</script>

<style scoped>
.input-sm { @apply px-2 py-1 border border-ivory-300 dark:border-ash-500 rounded text-xs bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 placeholder-ivory-500 dark:placeholder-ash-400 outline-none focus:ring-1 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30; }
.btn-primary { @apply px-3 py-1.5 rounded-lg text-xs font-semibold bg-navy-700 dark:bg-navy-700 hover:bg-navy-800 dark:hover:bg-navy-600 text-cream-50 dark:text-ash-900 disabled:opacity-50 active:scale-95 transition-transform; }
.btn-cancel { @apply px-3 py-1.5 rounded-lg text-xs font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700; }
.sort-btn { @apply px-2 py-1 rounded-lg text-[10px] font-medium border border-ivory-300 dark:border-ash-500 text-ink-700 dark:text-ink-50 hover:bg-ivory-100 dark:hover:bg-ash-700 active:scale-95 transition-transform; }
.sort-btn.active { @apply bg-navy-700 dark:bg-navy-700 text-cream-50 dark:text-ash-900 border-navy-700 dark:border-navy-600; }
.line-clamp-4 { display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
</style>
