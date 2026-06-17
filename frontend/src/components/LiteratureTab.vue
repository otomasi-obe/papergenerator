<template>
  <div class="w-full">
    <div class="bg-white dark:bg-anthracite-700 rounded-2xl border border-ivory-300 dark:border-anthracite-500 shadow-sm p-6 space-y-5">
      <!-- Header -->
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div class="min-w-0">
          <h2 class="text-lg font-semibold text-ink-900 dark:text-anthracite-50 font-serif">📚 Literatur</h2>
          <p class="text-sm text-ink-700 dark:text-anthracite-100 mt-1">
            Tabel referensi paper. Hasil SLR otomatis tersimpan di sini, dan bisa juga ditambah / diedit manual.
            Data ini dipakai sebagai sumber utama saat generate paper lengkap.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button
            @click="importFromFiles"
            :disabled="loading"
            class="px-3 py-1.5 rounded-lg text-xs font-medium bg-ivory-200 hover:bg-ivory-300 dark:bg-anthracite-600 dark:hover:bg-anthracite-500 text-ink-900 dark:text-anthracite-50 disabled:opacity-50"
            title="Import file PDF/DOCX yang sudah diupload"
          >📂 Import dari File</button>
          <button
            @click="showAddManual = !showAddManual"
            class="px-3 py-1.5 rounded-lg text-xs font-medium bg-navy-700 dark:bg-cream-200 hover:bg-navy-800 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 active:scale-95 transition-transform"
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
          <h3 class="text-sm font-semibold text-ink-900 dark:text-anthracite-50 font-serif">🔍 Jalankan SLR</h3>
          <span class="text-[10px] text-ink-500 dark:text-anthracite-200">Multi-source (OpenAlex · Crossref · arXiv · IEEE · SINTA · ...)</span>
        </div>
        <div class="flex flex-col sm:flex-row gap-2">
          <input
            ref="slrInputRef"
            v-model="slrQuery"
            @keyup.enter="runSLR"
            type="text"
            autocomplete="off"
            placeholder="Ketik topik (mis. 'reinforcement learning untuk navigasi AGV')"
            class="flex-1 px-3 py-2 border border-ivory-300 dark:border-anthracite-500 rounded-lg text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 focus:ring-2 focus:ring-[#238f7f]/30 outline-none"
            :disabled="slrRunning"
          />
          <input
            v-model.number="slrTopK"
            type="number"
            min="5"
            max="500"
            class="w-20 px-2 py-2 border border-ivory-300 dark:border-anthracite-500 rounded-lg text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 text-center"
            :disabled="slrRunning"
            title="Jumlah paper yang ditampilkan"
          />
          <button
            @click="runSLR"
            :disabled="slrRunning || !slrQuery.trim()"
            class="px-4 py-2 rounded-lg text-sm font-semibold bg-navy-700 dark:bg-cream-200 hover:bg-navy-800 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-50 active:scale-95 transition-transform"
          >
            {{ slrRunning ? 'Mencari…' : 'Jalankan SLR' }}
          </button>
        </div>

        <!-- Setting button + collapsible panel -->
        <div class="mt-2">
          <button
            @click="showSlrSettings = !showSlrSettings"
            class="px-3 py-1.5 rounded-lg text-xs font-medium bg-ivory-200 hover:bg-ivory-300 dark:bg-anthracite-600 dark:hover:bg-anthracite-500 text-ink-700 dark:text-anthracite-100 active:scale-95 transition-transform"
          >⚙️ Setting {{ showSlrSettings ? '▲' : '▼' }}</button>
          <div v-if="showSlrSettings" class="mt-2 rounded-lg border border-cream-300 dark:border-ash-600 bg-white dark:bg-anthracite-700 p-3 space-y-3">
            <!-- Source checkboxes -->
            <div>
              <div class="text-xs font-medium text-ink-700 dark:text-anthracite-100 mb-1">Source:</div>
              <div class="flex flex-wrap gap-2">
                <label
                  v-for="src in availableSources"
                  :key="src"
                  class="flex items-center gap-1 text-[11px] text-ink-700 dark:text-anthracite-100 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    :value="src"
                    v-model="slrSources"
                    class="rounded border-ivory-300 dark:border-anthracite-500"
                  />
                  {{ src }}
                </label>
              </div>
              <div class="flex gap-2 mt-1">
                <button @click="slrSources = [...availableSources]" class="text-[10px] text-blue-600 dark:text-blue-400 hover:underline">Pilih semua</button>
                <button @click="slrSources = []" class="text-[10px] text-blue-600 dark:text-blue-400 hover:underline">Hapus semua</button>
              </div>
            </div>
            <!-- Year input -->
            <div>
              <div class="text-xs font-medium text-ink-700 dark:text-anthracite-100 mb-1">Tahun terakhir:</div>
              <input
                v-model.number="slrYearFrom"
                type="number"
                :min="1900"
                :max="new Date().getFullYear() + 1"
                placeholder="Contoh: 2020"
                class="w-28 px-2 py-1 border border-ivory-300 dark:border-anthracite-500 rounded-lg text-xs bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50"
              />
              <button v-if="slrYearFrom" @click="slrYearFrom = null" class="ml-2 text-[10px] text-red-500 hover:underline">Reset</button>
            </div>
          </div>
        </div>

        <!-- Active jobs -->
        <div v-if="activeJobs.length" class="mt-3 space-y-2">
          <div v-for="job in activeJobs" :key="job.id"
               class="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-3 py-2 text-xs">
            <div class="flex items-center justify-between gap-2">
              <span class="font-medium text-amber-900 dark:text-amber-100 truncate">
                {{ job.status === 'running' ? '⏳' : '⏸' }}
                {{ job.query }}
              </span>
              <button @click="cancelJob(job.id)"
                      class="text-amber-700 dark:text-amber-300 hover:underline shrink-0">cancel</button>
            </div>
            <div class="mt-1 flex items-center gap-2">
              <span
                class="px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0"
                :class="stageBadgeClass(job)"
              >{{ stageLabel(job.stage) || stageLabel(job.status) || '—' }}</span>
              <div class="flex-1 h-1.5 rounded-full bg-amber-200 dark:bg-amber-900/50 overflow-hidden">
                <div class="h-full bg-amber-500 transition-all" :style="{ width: `${job.progress || 0}%` }"></div>
              </div>
            </div>
            <div class="mt-1 text-amber-800 dark:text-amber-200 text-[11px] truncate">
              {{ job.progress_message || stageLabel(job.stage) || 'Menunggu worker…' }}
            </div>
          </div>
        </div>

      <!-- SLR stream notification removed -->
      </div>

      <!-- Add manual form -->
      <div v-if="showAddManual" class="rounded-xl border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 p-4 space-y-2">
        <h3 class="text-sm font-semibold text-ink-900 dark:text-anthracite-50 font-serif">＋ Tambah Literatur Manual</h3>
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

      <!-- Filters row -->
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <div class="text-[11px] text-ink-500 dark:text-anthracite-200 flex items-center gap-2">
          <button
            @click="reviewAllPinned"
            :disabled="reviewBusy || pinnedCount === 0"
            class="px-2 py-1 rounded-lg text-[10px] font-semibold bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50 active:scale-95 transition-transform"
            title="Review semua pinned literatur dengan AI"
          >🤖 Review Pinned</button>
          <span>{{ filteredItems.length }} / {{ items.length }} literatur · {{ pinnedCount }} pinned</span>
        </div>
        <!-- Page size selector -->
        <div class="flex items-center gap-1 text-[11px]">
          <span class="text-ink-500 dark:text-anthracite-200">Tampilkan:</span>
          <button @click="setPageSize(100)" :class="['px-2 py-0.5 rounded text-[10px] font-medium border transition-colors', pageSize === 100 ? 'bg-navy-700 text-cream-50 border-navy-700 dark:bg-cream-200 dark:text-ash-900 dark:border-cream-200' : 'border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700']">100</button>
          <button @click="setPageSize(200)" :class="['px-2 py-0.5 rounded text-[10px] font-medium border transition-colors', pageSize === 200 ? 'bg-navy-700 text-cream-50 border-navy-700 dark:bg-cream-200 dark:text-ash-900 dark:border-cream-200' : 'border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700']">200</button>
        </div>
      </div>

      <!-- Quick sort buttons -->
      <div class="flex items-center gap-1 flex-wrap">
        <span class="text-xs font-medium text-ink-700 dark:text-anthracite-100 mr-1">Filter:</span>
        <button @click="setSort('year')" class="sort-btn" :class="{ active: sortKey === 'year' }">Tahun {{ sortIndicator('year') }}</button>
        <button @click="setSort('citations')" class="sort-btn" :class="{ active: sortKey === 'citations' }">Sitasi {{ sortIndicator('citations') }}</button>
        <button @click="setSort('title')" class="sort-btn" :class="{ active: sortKey === 'title' }">Judul A-Z {{ sortIndicator('title') }}</button>
        <button @click="setSort('authors')" class="sort-btn" :class="{ active: sortKey === 'authors' }">Penulis A-Z {{ sortIndicator('authors') }}</button>
      </div>

      <!-- Bulk action toolbar removed: checkbox now = pin -->

      <!-- Pagination bar (top) -->
      <div v-if="totalPages > 1" class="flex items-center justify-end gap-2 flex-wrap">
        <div class="text-[11px] text-ink-500 dark:text-anthracite-200">
          Baris {{ pageOffset + 1 }}–{{ Math.min(pageOffset + pageSize, filteredItems.length) }} dari {{ filteredItems.length }}
        </div>
        <div class="flex items-center gap-1">
          <button
            @click="currentPage = 1"
            :disabled="currentPage <= 1"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700 disabled:opacity-40"
          >««</button>
          <button
            @click="currentPage--"
            :disabled="currentPage <= 1"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700 disabled:opacity-40"
          >« Prev</button>
          <template v-for="p in visiblePageNumbers" :key="'top-' + p">
            <button
              v-if="p !== '...'"
              @click="currentPage = p as number"
              :class="['px-2 py-1 rounded text-[10px] font-medium border transition-colors', currentPage === p ? 'bg-navy-700 text-cream-50 border-navy-700 dark:bg-cream-200 dark:text-ash-900 dark:border-cream-200' : 'border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700']"
            >{{ p }}</button>
            <span v-else class="px-1 text-[10px] text-ink-400 dark:text-anthracite-300">…</span>
          </template>
          <button
            @click="currentPage++"
            :disabled="currentPage >= totalPages"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700 disabled:opacity-40"
          >Next »</button>
          <button
            @click="currentPage = totalPages"
            :disabled="currentPage >= totalPages"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700 disabled:opacity-40"
          >»»</button>
        </div>
      </div>

      <!-- Table -->
      <div class="overflow-x-auto rounded-xl border border-ivory-300 dark:border-anthracite-500">
        <table class="min-w-full text-xs">
          <thead class="bg-ivory-100 dark:bg-anthracite-800 text-ink-700 dark:text-anthracite-100">
            <tr>
              <th class="px-2 py-2 text-left w-6">
                <input
                  type="checkbox"
                  @change="togglePinAllVisible"
                  title="Pin/unpin semua di halaman ini"
                />
              </th>
              <th class="px-2 py-2 text-left w-10">#</th>
              <th class="px-2 py-2 text-left min-w-[260px]">Judul</th>
              <th class="px-2 py-2 text-left min-w-[220px]">Info</th>
              <th class="px-2 py-2 text-left min-w-[280px]">Abstract</th>
              <th class="px-2 py-2 text-left min-w-[280px]">Review</th>
              <th class="px-2 py-2 text-left w-20">Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && items.length === 0">
              <td colspan="7" class="px-3 py-6 text-center text-ink-500 dark:text-anthracite-200">Memuat…</td>
            </tr>
            <tr v-else-if="items.length === 0">
              <td colspan="7" class="px-3 py-8 text-center text-ink-500 dark:text-anthracite-200">
                <div class="space-y-3">
                  <div>Belum ada literatur. Jalankan SLR atau tambah manual untuk mulai.</div>
                  <button
                    v-if="paperTitle"
                    @click="startSLRFromPaperTopic"
                    class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-navy-700 dark:bg-cream-200 hover:bg-navy-800 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 active:scale-95 transition-transform"
                  >Jalankan SLR otomatis dari topik paper ini</button>
                </div>
              </td>
            </tr>
            <tr v-else-if="filteredItems.length === 0">
              <td colspan="7" class="px-3 py-8 text-center text-ink-500 dark:text-anthracite-200">
                Tidak ada literatur yang cocok dengan filter ini. Coba ubah / kosongkan filter.
              </td>
            </tr>
            <template v-else>
              <tr
                v-for="(it, i) in paginatedItems"
                :key="it.id"
                :class="['border-t border-ivory-200 dark:border-anthracite-600',
                         it.pinned ? 'bg-cream-100 dark:bg-anthracite-700/60' : 'hover:bg-cream-50 dark:hover:bg-anthracite-700/30']"
              >
                <td class="px-2 py-2 align-top">
                  <input
                    type="checkbox"
                    :checked="it.pinned"
                    @change="togglePin(it)"
                    title="Centang = pin (prioritas tinggi)"
                  />
                </td>
                <td class="px-2 py-2 align-top text-ink-500 dark:text-anthracite-200">{{ pageOffset + i + 1 }}</td>
                <!-- Judul -->
                <td class="px-2 py-2 align-top">
                  <div class="font-medium text-ink-900 dark:text-anthracite-50 leading-snug break-words">{{ it.title }}</div>
                </td>
                <!-- Info: Tahun, Sitasi, Penulis, Jurnal, DOI, PDF -->
                <td class="px-2 py-2 align-top text-[11px] text-ink-700 dark:text-anthracite-100 leading-relaxed">
                  <div class="space-y-0.5">
                    <div v-if="it.year"><span class="text-ink-500 dark:text-anthracite-300">Tahun:</span> {{ it.year }}</div>
                    <div><span class="text-ink-500 dark:text-anthracite-300">Sitasi:</span> {{ it.citations ?? '–' }}</div>
                    <div v-if="it.authors && it.authors.length">
                      <span class="text-ink-500 dark:text-anthracite-300">Penulis:</span>
                      <span :title="(it.authors||[]).join(', ')">{{ formatAuthors(it.authors) }}</span>
                    </div>
                    <div v-if="it.venue || it.publisher" class="text-ink-500 dark:text-anthracite-200 italic">
                      {{ it.venue || it.publisher }}
                    </div>
                    <div v-if="it.doi">
                      <a :href="`https://doi.org/${it.doi}`" target="_blank" rel="noopener" class="text-blue-600 dark:text-blue-400 hover:underline break-all text-[10px]">https://doi.org/{{ it.doi }}</a>
                    </div>
                    <div v-if="it.pdf_url">
                      <a :href="it.pdf_url" target="_blank" rel="noopener" class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200 hover:bg-emerald-200 dark:hover:bg-emerald-800/60 text-[10px] font-medium transition-colors" title="Download PDF">
                        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path d="M4 18h12V6h-4V2H4v16zm8-14.5V6h2.5L12 3.5zM6 16V4h4v4h4v8H6z"/><path d="M8 12h1.5v-2h1v2H12v-3.5h-1v1h-1v-1H8.5v1H8V12z"/></svg>
                        PDF
                      </a>
                    </div>
                    <div v-if="!it.pdf_url && !it.doi && it.url">
                      <a :href="safeUrl(it.url)" target="_blank" rel="noopener" class="text-blue-600 hover:underline break-all text-[10px]">🔗 URL</a>
                    </div>
                  </div>
                </td>
                <!-- Abstract (expandable) -->
                <td class="px-2 py-2 align-top text-[11px] text-ink-700 dark:text-anthracite-100 leading-relaxed break-words max-w-[360px]">
                  <template v-if="it.abstract">
                    <div :class="expandedAbstract.has(it.id) ? '' : 'line-clamp-3'" class="whitespace-pre-wrap">{{ it.abstract }}</div>
                    <button
                      v-if="isLongText(it.abstract)"
                      @click="toggleExpand('abstract', it.id)"
                      class="mt-0.5 text-[10px] text-blue-600 dark:text-blue-400 hover:underline"
                    >{{ expandedAbstract.has(it.id) ? '▲ sembunyikan' : '▼ tampilkan semua' }}</button>
                  </template>
                  <span v-else class="text-ink-400 dark:text-anthracite-300 italic">—</span>
                </td>
                <!-- Review (expandable) -->
                <td class="px-2 py-2 align-top text-[11px] text-ink-700 dark:text-anthracite-100 leading-relaxed break-words max-w-[360px]">
                  <template v-if="reviewingId === it.id">
                    <span class="text-amber-600 dark:text-amber-400 animate-pulse">⏳ Mereview…</span>
                  </template>
                  <template v-else-if="it.review">
                    <div :class="expandedReview.has(it.id) ? '' : 'line-clamp-3'" class="whitespace-pre-wrap">{{ it.review }}</div>
                    <button
                      v-if="isLongText(it.review)"
                      @click="toggleExpand('review', it.id)"
                      class="mt-0.5 text-[10px] text-blue-600 dark:text-blue-400 hover:underline"
                    >{{ expandedReview.has(it.id) ? '▲ sembunyikan' : '▼ tampilkan semua' }}</button>
                  </template>
                  <template v-else>
                    <span class="text-ink-400 dark:text-anthracite-300 italic">Belum di-review</span>
                  </template>
                </td>
                <!-- Actions -->
                <td class="px-2 py-2 align-top">
                  <div class="flex flex-col gap-1">
                    <button
                      @click="reviewSingle(it)"
                      :disabled="reviewingId === it.id || !it.abstract"
                      class="px-2 py-1 rounded text-[10px] font-medium bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-40 active:scale-95 transition-transform"
                      title="Review dengan AI"
                    >🤖 Review</button>
                    <button
                      @click="deleteItem(it)"
                      class="px-2 py-1 rounded text-[10px] font-medium bg-red-600 hover:bg-red-700 text-white active:scale-95 transition-transform"
                      title="Hapus literatur"
                    >🗑 Hapus</button>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- Pagination bar -->
      <div v-if="totalPages > 1" class="flex items-center justify-between gap-2 flex-wrap">
        <div class="text-[11px] text-ink-500 dark:text-anthracite-200">
          Baris {{ pageOffset + 1 }}–{{ Math.min(pageOffset + pageSize, filteredItems.length) }} dari {{ filteredItems.length }}
        </div>
        <div class="flex items-center gap-1">
          <button
            @click="currentPage = 1"
            :disabled="currentPage <= 1"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700 disabled:opacity-40"
          >««</button>
          <button
            @click="currentPage--"
            :disabled="currentPage <= 1"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700 disabled:opacity-40"
          >« Prev</button>
          <template v-for="p in visiblePageNumbers" :key="p">
            <button
              v-if="p !== '...'"
              @click="currentPage = p as number"
              :class="['px-2 py-1 rounded text-[10px] font-medium border transition-colors', currentPage === p ? 'bg-navy-700 text-cream-50 border-navy-700 dark:bg-cream-200 dark:text-ash-900 dark:border-cream-200' : 'border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700']"
            >{{ p }}</button>
            <span v-else class="px-1 text-[10px] text-ink-400 dark:text-anthracite-300">…</span>
          </template>
          <button
            @click="currentPage++"
            :disabled="currentPage >= totalPages"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700 disabled:opacity-40"
          >Next »</button>
          <button
            @click="currentPage = totalPages"
            :disabled="currentPage >= totalPages"
            class="px-2 py-1 rounded text-[10px] font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700 disabled:opacity-40"
          >»»</button>
        </div>
      </div>

      <p class="text-[11px] text-ink-500 dark:text-anthracite-200">
        💡 <strong>Tip:</strong> hasil yang di-pin / must-read diprioritaskan oleh AI saat generate paper.
        Klik pada chat dan ketik <em>"buatkan literatur review tentang ..."</em> untuk menjalankan SLR otomatis.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { usePaperStore } from '../stores/paper'
import { useLiteratureStore } from '../stores/literature'
import api from '../api/index'

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
  pinned?: boolean
  must_read?: boolean
}

interface SLRJob {
  id: number
  query: string
  status: 'queued' | 'running' | 'done' | 'error'
  stage?: string
  progress?: number
  progress_message?: string
  queued_at?: string
  finished_at?: string
  stats?: {
    ai_summary_used?: boolean
    [key: string]: any
  }
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
  onlyPinned: boolean
  minYear: number | null
}

const store = usePaperStore()
const litStore = useLiteratureStore()
const { currentPaperId } = storeToRefs(store)

const items = ref<LiteratureItem[]>([])
const loading = ref(false)
const loadError = ref('')

const filter = ref('')
const filterSource = ref('')
const onlyPinned = ref(false)
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

// SLR live stream: items that arrived during active SLR
const slrStreamItems = ref<LiteratureItem[]>([])
let _knownIdsBeforeSlr = new Set<number>()

// SLR Settings
const showSlrSettings = ref(false)
const availableSources = ref([
  'openalex', 'crossref', 'arxiv', 'ieee', 'semantic_scholar',
  'pubmed', 'sinta', 'scopus', 'dblp', 'europepmc',
  'doaj', 'core', 'lens', 'zenodo', 'hal', 'cambridge',
  'plos', 'sciencedirect', 'openaire', 'datacite',
])
const slrSources = ref<string[]>([...availableSources.value])
const slrYearFrom = ref<number | null>(null)

const manualForm = ref<ManualForm>({
  title: '', authors_str: '', year: null,
  venue: '', doi: '', url: '', summary: '',
})

const selectedIds = ref<Set<number>>(new Set())
const bulkBusy = ref(false)
const bulkMsg = ref('')
const selectionCount = computed(() => selectedIds.value.size)

const sortKey = ref<'default' | 'title' | 'year' | 'score' | 'citations' | 'authors'>('default')
const sortDir = ref<'asc' | 'desc'>('desc')

const reviewingId = ref<number | null>(null)
const reviewBusy = ref(false)

const paperTitle = computed<string>(() => store.paper?.title || '')

// Pagination
const pageSize = ref(100)
const currentPage = ref(1)

// Expandable abstract/review — Set of item IDs that are expanded (default = collapsed via line-clamp-3)
const expandedAbstract = ref<Set<number>>(new Set())
const expandedReview = ref<Set<number>>(new Set())

function isLongText(text: string | undefined): boolean {
  if (!text) return false
  // Rough: > 3 lines ≈ > 200 chars or has 3+ newlines
  return text.length > 200 || (text.split('\n').length > 3)
}

function toggleExpand(field: 'abstract' | 'review', id: number): void {
  const set = field === 'abstract' ? expandedAbstract : expandedReview
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
  return items.value.filter(it => {
    if (filterSource.value && (it.source || it.source_kind) !== filterSource.value) return false
    if (onlyPinned.value && !it.pinned) return false
    if (minY != null && (it.year == null || Number(it.year) < minY)) return false
    if (!q) return true
    const hay = [
      it.title, it.venue, it.publisher, it.doi, it.url, it.pdf_url,
      ((it.authors || []).join(', ')),
    ].join(' ').toLowerCase()
    return hay.includes(q)
  })
})

const displayedItems = computed<LiteratureItem[]>(() => {
  const arr = filteredItems.value.slice()
  if (sortKey.value === 'default') {
    arr.sort((a, b) => {
      const pinDiff = (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0)
      if (pinDiff !== 0) return pinDiff
      const sa = a.score_total ?? -Infinity
      const sb = b.score_total ?? -Infinity
      return sb - sa
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
        va = ((a.authors || [])[0] || (a.authors || []).join(',')).toLowerCase()
        vb = ((b.authors || [])[0] || (b.authors || []).join(',')).toLowerCase()
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

function setPageSize(size: number): void {
  pageSize.value = size
  currentPage.value = 1
}

const pinnedCount = computed<number>(() => items.value.filter(i => i.pinned).length)

const allVisibleSelected = computed<boolean>(() => {
  const arr = paginatedItems.value
  if (arr.length === 0) return false
  for (const it of arr) {
    if (!selectedIds.value.has(it.id)) return false
  }
  return true
})

const someVisibleSelected = computed<boolean>(() => {
  for (const it of paginatedItems.value) {
    if (selectedIds.value.has(it.id)) return true
  }
  return false
})

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

const STAGE_LABELS: Record<string, string> = {
  queued: 'Antri',
  fetching: 'Mencari sumber',
  source_done: 'Mengambil hasil',
  dedup_done: 'Dedup selesai',
  scoring: 'Ranking',
  scored: 'Ranking selesai',
  summarizing: 'Scoring programmatik',
  summarized: 'Scoring selesai',
  complete: 'Selesai',
  running: 'Berjalan',
  done: 'Selesai',
  error: 'Gagal',
}

function stageLabel(stage: string | undefined): string {
  if (!stage) return ''
  return STAGE_LABELS[stage] || stage
}

function stageBadgeClass(job: SLRJob | null): string {
  if (job?.status === 'error') {
    return 'bg-red-200 text-red-900 dark:bg-red-900 dark:text-red-100'
  }
  if (job?.status === 'done' || job?.stage === 'complete') {
    return 'bg-emerald-200 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100'
  }
  if (job?.status === 'queued' || job?.stage === 'queued') {
    return 'bg-cream-100 text-ink-700 dark:bg-anthracite-700 dark:text-anthracite-100'
  }
  return 'bg-amber-200 text-amber-900 dark:bg-amber-800 dark:text-amber-100'
}

function filterStorageKey(paperId: string): string {
  return `lit.filter.${paperId}`
}

function isAllFiltersDefault(): boolean {
  return !filter.value
    && !filterSource.value
    && !onlyPinned.value
    && (minYear.value == null || minYear.value === '')
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
      onlyPinned: onlyPinned.value,
      minYear: minYear.value,
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
    onlyPinned.value = false
    minYear.value = null
    return
  }
  filter.value = saved.filter || ''
  filterSource.value = saved.filterSource || ''
  onlyPinned.value = !!saved.onlyPinned
  minYear.value = (saved.minYear === '' || saved.minYear == null) ? null : Number(saved.minYear)
}

watch(
  [filter, filterSource, onlyPinned, minYear],
  () => { saveFilterState() }
)

async function loadItems(): Promise<void> {
  if (!currentPaperId.value) return
  // Don't show full loading spinner during SLR streaming
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

    if (slrRunning.value) {
      // Merge mode: update existing in place, append new at bottom
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
        // Track stream items for the live indicator
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
  }
}

let _lastJobIds = new Set<number>()
let _lastJobStatus: Record<number, string> = {}
let _consecutiveFailures = 0
let _waitCursor = 0
const _TRANSIENT_STATUSES = new Set([0, 408, 429, 502, 503, 504, 520, 521, 522, 523, 524])

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
    const active = jobs.filter(j => j.status === 'queued' || j.status === 'running')
    activeJobs.value = active
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
      (!_lastJobIds.has(j.id) || _lastJobStatus[j.id] !== 'done')
    )
    const justFinished = jobs.some(j =>
      (j.status === 'done' || j.status === 'error') &&
      (!_lastJobIds.has(j.id) || _lastJobStatus[j.id] !== j.status)
    )
    if (justFinished) {
      _extraFastPolls = 1
      await loadItems()
      if (newlyDone.length > 0) {
        const n = items.value.length
        toast(`SLR selesai. ${n} literatur masuk.`, 'success')
        try {
          const { useChatStore } = await import('../stores/chat')
          const chatStore = useChatStore()
          const j = newlyDone[0]
          const q = j?.query || ''
          const body = [
            `✅ **SLR selesai.** ${n} literatur berhasil dikumpulkan` +
              (q ? ` untuk query *"${q}"*.` : '.'),
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
    // Update slrRunning
    const wasRunning = slrRunning.value
    slrRunning.value = active.length > 0
    // If SLR just started, snapshot known IDs for stream tracking
    if (!wasRunning && slrRunning.value) {
      _knownIdsBeforeSlr = new Set(items.value.map(i => i.id))
    }
    _lastJobIds = new Set(jobs.map(j => j.id))
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
  await Promise.all([loadItems(), loadJobs()])
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
    if (hasActive) {
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
  slrRunning.value = true
  _knownIdsBeforeSlr = new Set(items.value.map(i => i.id))
  slrStreamItems.value = []
  try {
    await api.post(`/api/papers/${currentPaperId.value}/slr/jobs`, {
      query: q,
      top_k: slrTopK.value,
      ai_summarize: false,
      sources: slrSources.value.length > 0 && slrSources.value.length < availableSources.value.length ? slrSources.value : null,
      year_from: slrYearFrom.value || null,
    })
    await loadJobs()
    schedulePoll()
  } catch (e: any) {
    const msg = e?.response?.data?.error || e?.message || 'SLR failed'
    toast('SLR error: ' + msg, 'error')
  } finally {
    slrRunning.value = false
  }
}

async function cancelJob(jobId: number): Promise<void> {
  if (!confirm('Hentikan job SLR ini? Hasil parsial dihilangkan.')) return
  try {
    await api.delete(`/api/slr/jobs/${jobId}`)
    await loadJobs()
  } catch (e: any) {
    toast('Cancel failed: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  }
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

async function importFromFiles(): Promise<void> {
  if (!currentPaperId.value) return
  loading.value = true
  try {
    const res = await api.post(`/api/papers/${currentPaperId.value}/literature/from-files`)
    const created = (res?.data?.created || []).length
    toast(created > 0 ? `Imported ${created} file${created === 1 ? '' : 's'}` : '0 new files', created > 0 ? 'success' : 'info')
    await loadItems()
  } catch (e: any) {
    toast('Import failed: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  } finally {
    loading.value = false
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
  if (!confirm(`Hapus "${it.title?.slice(0, 80) || 'literatur ini'}"?`)) return
  try {
    await api.delete(`/api/papers/${currentPaperId.value}/literature/${it.id}`)
    await loadItems()
    toast('Dihapus', 'success')
  } catch (e: any) {
    toast('Hapus gagal: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  }
}

function toggleSelect(id: number): void {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function toggleSelectAllVisible(): void {
  const ids = paginatedItems.value.map(i => i.id)
  if (allVisibleSelected.value) {
    const next = new Set(selectedIds.value)
    for (const id of ids) next.delete(id)
    selectedIds.value = next
  } else {
    const next = new Set(selectedIds.value)
    for (const id of ids) next.add(id)
    selectedIds.value = next
  }
}

function clearSelection(): void {
  selectedIds.value = new Set()
}

function pruneSelection(): void {
  const known = new Set(items.value.map(i => i.id))
  const next = new Set<number>()
  for (const id of selectedIds.value) {
    if (known.has(id)) next.add(id)
  }
  selectedIds.value = next
}

async function runBulk(label: string, fn: (id: number) => Promise<any>): Promise<number> {
  const ids = Array.from(selectedIds.value)
  if (ids.length === 0) return 0
  bulkBusy.value = true
  bulkMsg.value = `${label} ${ids.length}…`
  let okCount = 0
  try {
    const results = await Promise.all(ids.map(id => fn(id).then(() => true).catch(() => false)))
    okCount = results.filter(Boolean).length
  } finally {
    bulkBusy.value = false
    bulkMsg.value = ''
  }
  return okCount
}

async function bulkDelete(): Promise<void> {
  if (!currentPaperId.value) return
  const total = selectedIds.value.size
  if (total === 0) return
  if (!confirm(`Hapus ${total} literatur terpilih? Tindakan ini tidak bisa dibatalkan.`)) return
  const ok = await runBulk('Menghapus', (id) =>
    api.delete(`/api/papers/${currentPaperId.value}/literature/${id}`)
  )
  clearSelection()
  await loadItems()
  if (ok === total) toast(`Dihapus ${ok} literatur`, 'success')
  else toast(`Dihapus ${ok}/${total} (sisanya gagal)`, ok > 0 ? 'info' : 'error')
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

function formatAuthors(authors: string[] | undefined): string {
  if (!authors || authors.length === 0) return '–'
  if (authors.length <= 3) return authors.join(', ')
  return `${authors.slice(0, 3).join(', ')}, et al.`
}

async function togglePin(it: LiteratureItem): Promise<void> {
  if (!currentPaperId.value) return
  const newVal = !it.pinned
  try {
    await api.patch(`/api/papers/${currentPaperId.value}/literature/${it.id}`, {
      pinned: newVal,
    })
    it.pinned = newVal
  } catch (e: any) {
    toast('Gagal mengubah pin: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  }
}

async function togglePinAllVisible(): Promise<void> {
  if (!currentPaperId.value) return
  const items_visible = paginatedItems.value
  if (items_visible.length === 0) return
  // If all visible are pinned → unpin all, else → pin all
  const allPinned = items_visible.every(it => it.pinned)
  const newVal = !allPinned
  const ids = items_visible.map(it => it.id)
  try {
    await api.post(`/api/papers/${currentPaperId.value}/literature/bulk-patch`, {
      ids,
      patch: { pinned: newVal },
    })
    for (const it of items_visible) {
      it.pinned = newVal
    }
  } catch (e: any) {
    toast('Gagal mengubah pin: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  }
}

async function reviewSingle(it: LiteratureItem): Promise<void> {
  if (!currentPaperId.value || !it.abstract) return
  reviewingId.value = it.id
  try {
    const res = await api.post(`/api/papers/${currentPaperId.value}/literature/${it.id}/review`)
    if (res.data && res.data.review) {
      it.review = res.data.review
    }
    toast('Review selesai', 'success')
  } catch (e: any) {
    toast('Review gagal: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  } finally {
    reviewingId.value = null
  }
}

async function reviewAllPinned(): Promise<void> {
  if (!currentPaperId.value) return
  reviewBusy.value = true
  try {
    const res = await api.post(`/api/papers/${currentPaperId.value}/literature/review-pinned`)
    const results = res.data?.results || []
    const successCount = results.filter((r: any) => r.status === 'success').length
    for (const r of results) {
      if (r.status === 'success' && r.review) {
        const item = items.value.find(i => i.id === r.id)
        if (item) item.review = r.review
      }
    }
    toast(`Review selesai: ${successCount}/${results.length} literatur`, 'success')
  } catch (e: any) {
    toast('Review gagal: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  } finally {
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
      progress_message: 'Starting…',
    }, ...activeJobs.value]
    slrRunning.value = true
  }
  loadJobs().finally(() => schedulePoll())
}

watch(currentPaperId, async (id) => {
  _lastJobIds = new Set()
  _lastJobStatus = {}
  _consecutiveFailures = 0
  _waitCursor = 0
  activeJobs.value = []
  lastSlrJob.value = null
  selectedIds.value = new Set()
  slrStreamItems.value = []
  expandedAbstract.value = new Set()
  expandedReview.value = new Set()
  loadError.value = ''
  currentPage.value = 1
  applySavedFilter(id ? loadFilterStateFor(id) : null)
  if (id) {
    await Promise.all([loadItems(), loadJobs()])
    schedulePoll()
  }
})

watch(() => litStore.pendingIntent, (intent) => {
  if (intent) applyIntent(litStore.consumeIntent())
})

onMounted(async () => {
  if (currentPaperId.value) {
    applySavedFilter(loadFilterStateFor(currentPaperId.value))
    await Promise.all([loadItems(), loadJobs()])
  }
  applyIntent(litStore.consumeIntent())
  schedulePoll()
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', _onVisibilityChange)
  }
})

onUnmounted(() => {
  if (_pollTimer) clearTimeout(_pollTimer)
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', _onVisibilityChange)
  }
})
</script>

<style scoped>
.input-sm { @apply px-2 py-1 border border-ivory-300 dark:border-anthracite-500 rounded text-xs bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 outline-none focus:ring-1 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30; }
.btn-primary { @apply px-3 py-1.5 rounded-lg text-xs font-semibold bg-navy-700 dark:bg-cream-200 hover:bg-navy-800 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-50 active:scale-95 transition-transform; }
.btn-cancel { @apply px-3 py-1.5 rounded-lg text-xs font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700; }
.sort-btn { @apply px-2 py-1 rounded-lg text-[10px] font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700 active:scale-95 transition-transform; }
.sort-btn.active { @apply bg-navy-700 dark:bg-cream-200 text-cream-50 dark:text-ash-900 border-navy-700 dark:border-cream-200; }
.line-clamp-3 { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
</style>
