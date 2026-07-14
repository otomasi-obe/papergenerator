<template>
  <div class="space-y-4 pb-24">
    <div class="flex items-center gap-2">
      <svg class="w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
      <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">Generate Full</h2>
    </div>

    <p class="text-sm text-ink-600 dark:text-ink-300">
      Buat paper utuh dari sebuah topik. AI akan menghasilkan kerangka, mengisi section, lalu menyimpannya ke paper aktif.
    </p>

    <!-- Hidden file inputs: Data + File (PDF/DOCX/Excel/CSV) -->
    <input
      ref="dataInputRef"
      type="file"
      accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.md"
      multiple
      class="hidden"
      @change="onDataFileChange"
    />
    <input
      ref="refInputRef"
      type="file"
      accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.md"
      multiple
      class="hidden"
      @change="onRefFileChange"
    />

    <!-- Generating progress card -->
    <div
      v-if="generating || activeJob"
      class="rounded-xl border border-navy-200/60 dark:border-navy-700/60 bg-gradient-to-br from-navy-50 to-white dark:from-navy-900/40 dark:to-navy-900/20 px-4 py-3 text-xs space-y-2.5 shadow-sm"
    >
      <div class="flex items-center gap-3">
        <div class="relative">
          <span class="inline-block w-4 h-4 border-2 border-navy-300 border-t-navy-600 dark:border-t-cream-300 rounded-full animate-spin"></span>
        </div>
        <div class="flex-1 min-w-0">
          <span class="font-semibold text-navy-800 dark:text-navy-200 text-sm generating-text">
            Generating Paper
            <span class="gen-dots"><span>.</span><span>.</span><span>.</span></span>
          </span>
        </div>
        <span class="font-mono font-bold text-sm text-navy-700 dark:text-navy-300 tabular-nums">
          {{ displayProgress }}%
        </span>
      </div>

      <!-- Progress bar with glow effect -->
      <div class="h-1.5 rounded-full bg-navy-200 dark:bg-navy-800 overflow-hidden">
        <div
          class="h-full bg-gradient-to-r from-navy-500 via-emerald-500 to-navy-500 dark:from-cream-300 dark:via-emerald-400 dark:to-cream-300 transition-all duration-1000 ease-linear progress-glow"
          :style="{ width: displayProgress + '%' }"
        />
      </div>

      <div class="flex items-center gap-2">
        <div class="flex-1 text-navy-600 dark:text-navy-400 truncate text-[11px]">
          {{ activeJob?.prompt || generatingTopic || 'Generating paper...' }}
        </div>
        <div class="text-navy-600 dark:text-navy-400 text-[10px] font-mono tabular-nums shrink-0">
          {{ timeElapsed }}
        </div>
        <button
          @click="stopGeneration"
          class="px-2.5 py-1 min-h-[28px] text-[11px] font-semibold rounded-md bg-red-600 hover:bg-red-700 text-white active:scale-95 transition-all shadow-sm hover:shadow"
          title="Stop generation"
        >
          ⬛ Stop
        </button>
      </div>
    </div>

    <div>
      <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Topik paper</label>
      <textarea
        v-model="topic"
        rows="4"
        :disabled="generating || !!activeJob"
        placeholder="Masukkan topik paper (mis. 'optimasi rute AGV dengan reinforcement learning')"
        class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm disabled:opacity-50"
      ></textarea>
    <!-- Connection lost indicator -->
    <div
      v-if="connectionLost"
      class="rounded-lg border border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/30 px-3 py-2 text-xs flex items-center gap-2"
    >
      <span class="inline-block w-3 h-3 border-2 border-amber-400 border-t-amber-700 dark:border-t-amber-300 rounded-full animate-spin"></span>
      <span class="text-amber-800 dark:text-amber-200 font-medium">
        Koneksi terputus - paper masih digenerate di server. Memeriksa status...
      </span>
      <button
        @click="manualCheckDb"
        class="ml-auto px-2 py-0.5 text-[10px] font-semibold rounded bg-amber-600 hover:bg-amber-700 text-white transition-colors"
      >
        Cek Sekarang
      </button>
    </div>

    <!-- Generation options -->
    <div class="flex items-center gap-4 px-2 py-2 rounded-lg bg-cream-100 dark:bg-ash-700/50 text-xs">
      <label class="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" v-model="enablePaperReview" :disabled="generating || !!activeJob" class="rounded w-4 h-4 accent-navy-600" />
        <span class="text-ink-800 dark:text-ink-100 font-medium">Paper Review</span>
      </label>
      <label class="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" v-model="enableImageGen" :disabled="generating || !!activeJob" class="rounded w-4 h-4 accent-navy-600" />
        <span class="text-ink-800 dark:text-ink-100 font-medium">Generate Images</span>
      </label>
      <label class="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" v-model="enableRevisiSemua" :disabled="generating || !!activeJob" class="rounded w-4 h-4 accent-navy-600" />
        <span class="text-ink-800 dark:text-ink-100 font-medium">Revisi Semua</span>
      </label>
      <label class="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" v-model="enableRegenerateImages" :disabled="generating || !!activeJob" class="rounded w-4 h-4 accent-amber-600" />
        <span class="text-ink-800 dark:text-ink-100 font-medium">Re-generate Images</span>
      </label>
    </div>

    <!-- Language Selector -->
    <div>
      <label class="block text-sm font-medium text-ink-900 dark:text-anthracite-50 mb-2">🌐 Bahasa Paper</label>
      <select
        v-model="store.paper.language"
        :disabled="generating || !!activeJob"
        class="max-w-md w-full px-3 py-2 border border-ivory-300 dark:border-anthracite-500 rounded-xl text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 focus:border-navy-500 dark:focus:border-navy-400 outline-none disabled:opacity-50"
      >
        <option value="id">🇮🇩 Bahasa Indonesia</option>
        <option value="en">🔤 English</option>
      </select>
      <p class="text-xs text-ink-700 dark:text-anthracite-200 mt-1">
        Bahasa untuk penulisan paper hasil generate.
      </p>
    </div>

    <!-- Action buttons -->
    <div class="flex items-center gap-2">
      <button
        @click="generate"
        :disabled="(!topic.trim() && !enableRegenerateImages) || generating || !!activeJob"
        class="flex-1 px-4 py-2 bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30"
      >
        <span v-if="generating" class="inline-flex items-center gap-1">
          <span class="w-3 h-3 border-2 border-cream-200 border-t-transparent rounded-full animate-spin"></span>
          <span class="generating-btn-text">Generating</span>
        </span>
        <span v-else>Generate</span>
      </button>
    </div>


    <!-- Input file: dua bucket terpisah (Data + File) dengan inline file list -->
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <!-- DATA bucket -->
      <div
        @dragover.prevent="dataDragOver = true"
        @dragleave.prevent="dataDragOver = false"
        @drop="onDataDrop"
        :class="[
          'rounded-xl border-2 border-dashed px-3 py-3 transition-colors',
          dataDragOver ? 'border-navy-500 bg-navy-50 dark:bg-navy-900/30' : 'border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800',
          (generating || activeJob) ? 'opacity-50 pointer-events-none' : '',
        ]"
      >
        <div class="flex items-center gap-2 mb-1">
          <span class="text-base">📊</span>
          <span class="text-xs font-semibold text-ink-900 dark:text-ink-50">Data</span>
          <!-- + upload button -->
          <div class="relative ml-auto">
            <button
              @click.stop="dataPickerOpen = !dataPickerOpen"
              :disabled="generating || !!activeJob"
              class="w-6 h-6 flex items-center justify-center rounded-md text-xs font-bold text-navy-600 dark:text-navy-300 hover:bg-navy-100 dark:hover:bg-ash-600 transition-colors disabled:opacity-40"
              title="Tambah file"
            >＋</button>
            <div v-if="dataPickerOpen" class="absolute right-0 top-full mt-1 z-30 w-44 rounded-md border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-lg overflow-hidden" ref="dataPickerRef">
              <button type="button" @click="triggerDataInput(); dataPickerOpen = false"
                class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2">
                <span>📤</span><span>Upload file</span>
              </button>
              <button type="button" @click="openDataAnalysisPicker(); dataPickerOpen = false"
                class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2 border-t border-cream-300 dark:border-ash-600">
                <span>📊</span><span>Dari Data</span>
              </button>
            </div>
          </div>
        </div>
        <p class="text-[10px] text-ink-500 dark:text-ink-300 leading-snug">
          csv, xlsx, pdf — data mentah untuk tabel &amp; grafik
        </p>
        <!-- Inline paper files list with checkboxes -->
        <div v-if="paperFilesList.length" class="mt-2">
          <!-- Select All for Data -->
          <label class="flex items-center gap-2 px-2 py-1 cursor-pointer text-xs font-semibold hover:bg-cream-100 dark:hover:bg-ash-600 border-b border-cream-200 dark:border-ash-600">
            <input type="checkbox" :checked="areAllDataPicked" @change="toggleSelectAllData" class="rounded w-3.5 h-3.5 accent-navy-600" />
            <span class="flex-1">Pilih Semua</span>
            <span class="text-ink-500 dark:text-ink-300 text-[10px] shrink-0">{{ pickedDataFiles.length }} / {{ paperFilesList.length }}</span>
          </label>
          <div class="max-h-36 overflow-y-auto rounded-lg border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 divide-y divide-cream-200 dark:divide-ash-600">
            <label
              v-for="pf in paperFilesList"
              :key="pf.id"
              class="flex items-center gap-2 px-2 py-1 cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-600 text-xs"
            >
              <input type="checkbox" v-model="pickedDataFiles" :value="pf.id" class="rounded w-3.5 h-3.5 accent-navy-600" />
              <span class="flex-1 truncate text-ink-800 dark:text-ink-100" :title="pf.original_name || pf.filename">{{ pf.original_name || pf.filename }}</span>
            </label>
          </div>
          <button
            v-if="pickedDataFiles.length"
            @click="confirmDataFiles"
            class="mt-1.5 w-full px-2 py-1 text-[10px] font-semibold rounded-md bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 transition-colors"
          >Tambah Data ({{ pickedDataFiles.length }})</button>
        </div>
        <div v-if="dataFiles.length" class="flex flex-wrap gap-1.5 mt-2">
          <div
            v-for="(f, i) in dataFiles"
            :key="i"
            :class="[
              'flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] border text-ink-900 dark:text-ink-50',
              f.isDataAnalysis ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700' : 'bg-white dark:bg-ash-700 border-cream-300 dark:border-ash-600',
            ]"
          >
            <span>{{ f.isDataAnalysis ? '📊' : (f.stale ? '⟳' : (f.extracted ? '✓' : '📄')) }}</span>
            <span class="truncate max-w-[120px]" :title="f.stale ? f.name + ' (perlu re-attach)' : f.name">{{ f.name }}</span>
            <button @click.stop="removeDataFile(i)" class="text-ink-500 hover:text-red-500 dark:text-red-400 ml-1 active:scale-95 transition-transform">✕</button>
          </div>
        </div>
      </div>

      <!-- FILE bucket -->
      <div
        @dragover.prevent="refDragOver = true"
        @dragleave.prevent="refDragOver = false"
        @drop="onRefDrop"
        :class="[
          'rounded-xl border-2 border-dashed px-3 py-3 transition-colors',
          refDragOver ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/30' : 'border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800',
          (generating || activeJob) ? 'opacity-50 pointer-events-none' : '',
        ]"
      >
        <div class="flex items-center gap-2 mb-1">
          <span class="text-base">📚</span>
          <span class="text-xs font-semibold text-ink-900 dark:text-ink-50">File</span>
          <!-- + upload button -->
          <div class="relative ml-auto">
            <button
              @click.stop="refPickerOpen = !refPickerOpen"
              :disabled="generating || !!activeJob"
              class="w-6 h-6 flex items-center justify-center rounded-md text-xs font-bold text-emerald-600 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-ash-600 transition-colors disabled:opacity-40"
              title="Tambah file/draft"
            >＋</button>
            <div v-if="refPickerOpen" class="absolute right-0 top-full mt-1 z-30 w-44 rounded-md border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-lg overflow-hidden" ref="refPickerRef">
              <button type="button" @click="triggerRefInput(); refPickerOpen = false"
                class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2">
                <span>📤</span><span>Upload file</span>
              </button>
            </div>
          </div>
        </div>
        <p class="text-[10px] text-ink-500 dark:text-ink-300 leading-snug">
          paper, draft chat, atau referensi lain — konteks &amp; sumber sitasi
        </p>
        <!-- Inline paper files list with checkboxes -->
        <div v-if="paperFilesList.length" class="mt-2">
          <!-- Select All for File -->
          <label class="flex items-center gap-2 px-2 py-1 cursor-pointer text-xs font-semibold hover:bg-cream-100 dark:hover:bg-ash-600 border-b border-cream-200 dark:border-ash-600">
            <input type="checkbox" :checked="areAllRefPicked" @change="toggleSelectAllRef" class="rounded w-3.5 h-3.5 accent-emerald-600" />
            <span class="flex-1">Pilih Semua</span>
            <span class="text-ink-500 dark:text-ink-300 text-[10px] shrink-0">{{ pickedRefFiles.length }} / {{ paperFilesList.length }}</span>
          </label>
          <div class="max-h-36 overflow-y-auto rounded-lg border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 divide-y divide-cream-200 dark:divide-ash-600">
            <label
              v-for="pf in paperFilesList"
              :key="pf.id"
              class="flex items-center gap-2 px-2 py-1 cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-600 text-xs"
            >
              <input type="checkbox" v-model="pickedRefFiles" :value="pf.id" class="rounded w-3.5 h-3.5 accent-emerald-600" />
              <span class="flex-1 truncate text-ink-800 dark:text-ink-100" :title="pf.original_name || pf.filename">{{ pf.original_name || pf.filename }}</span>
            </label>
          </div>
          <button
            v-if="pickedRefFiles.length"
            @click="confirmRefFiles"
            class="mt-1.5 w-full px-2 py-1 text-[10px] font-semibold rounded-md bg-emerald-700 hover:bg-emerald-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 transition-colors"
          >Tambah File ({{ pickedRefFiles.length }})</button>
        </div>
        <div v-if="referenceFiles.length" class="flex flex-wrap gap-1.5 mt-2">
          <div
            v-for="(f, i) in referenceFiles"
            :key="i"
            :class="[
              'flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] border text-ink-900 dark:text-ink-50',
              f.isDraft ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-300 dark:border-emerald-700' : 'bg-white dark:bg-ash-700 border-cream-300 dark:border-ash-600',
            ]"
          >
            <span>{{ f.isDraft ? '💬' : (f.stale ? '⟳' : (f.extracted ? '✓' : '📄')) }}</span>
            <span class="truncate max-w-[120px]" :title="f.stale ? f.name + ' (perlu re-attach)' : f.name">{{ f.name }}</span>
            <button @click.stop="removeRefFile(i)" class="text-ink-500 hover:text-red-500 dark:text-red-400 ml-1 active:scale-95 transition-transform">✕</button>
          </div>
        </div>
      </div>
    </div>

      <!-- Literatur section (checked papers from SLR — auto-injected to prompt) -->
      <div
        class="rounded-xl border-2 border-dashed px-3 py-3 transition-colors border-emerald-300 dark:border-emerald-700 bg-emerald-50/50 dark:bg-emerald-900/10"
      >
        <div class="flex items-center gap-2 mb-1">
          <span class="text-base">📚</span>
          <span class="text-xs font-semibold text-ink-900 dark:text-ink-50">Literatur</span>
          <span v-if="literatureLoading" class="text-[10px] text-ink-500 dark:text-ink-300 italic ml-auto">Memuat...</span>
          <span v-else class="ml-auto text-[10px] font-medium px-1.5 py-0.5 rounded-full"
            :class="literatureItems.length ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300' : 'bg-ivory-100 dark:bg-ash-600 text-ink-500 dark:text-ink-300'"
          >{{ literatureItems.length }} checked</span>
        </div>
        <p class="text-[10px] text-emerald-600 dark:text-emerald-400 leading-snug">
          Otomatis dikirim ke AI saat generate. Check/uncheck di tab Literatur.
        </p>
        <div v-if="!literatureLoading && !literatureItems.length" class="mt-2 text-[11px] text-ink-500 dark:text-ink-300 italic p-2">
          Belum ada literatur yang di-check.
        </div>
        <div v-else-if="literatureItems.length" class="mt-2">
          <div class="max-h-48 overflow-y-auto rounded-lg border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-700 divide-y divide-cream-200 dark:divide-ash-600">
            <div v-for="lit in literatureItems" :key="lit.id" class="flex items-center gap-2 px-2 py-1.5 text-xs">
              <span class="text-[10px] text-emerald-500 shrink-0">✓</span>
              <div class="flex-1 min-w-0">
                <div class="truncate text-ink-800 dark:text-ink-100 font-medium">{{ lit.title }}</div>
                <div class="text-[10px] text-ink-500 dark:text-ink-300 truncate">
                  {{ Array.isArray(lit.authors) ? lit.authors.join(', ') : (lit.authors || '--') }} &middot; {{ lit.year || '--' }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Reasoning / Process output -->
    <div
      v-if="generating || activeJob || reasoningText"
      class="rounded-xl border border-cream-300/60 dark:border-ash-600/60 bg-cream-50 dark:bg-ash-800 overflow-hidden shadow-sm"
    >
      <div class="flex items-center gap-2 px-4 py-2.5 border-b border-cream-300/60 dark:border-ash-600/60 bg-gradient-to-r from-cream-100 to-cream-50 dark:from-ash-700 dark:to-ash-800">
        <span class="w-2 h-2 rounded-full animate-pulse" :class="generating ? 'bg-amber-500' : 'bg-blue-500'"></span>
        <span class="text-xs font-semibold text-ink-900 dark:text-ink-50">🧠 AI Reasoning</span>
        <span v-if="generating" class="text-[10px] text-amber-600 dark:text-amber-400 font-medium">(live)</span>
        <button
          v-if="!generating"
          @click="dismissGenerationPanel"
          class="ml-auto text-ink-500 hover:text-ink-900 dark:hover:text-ink-50 text-xs px-1.5 py-0.5 rounded hover:bg-cream-200 dark:hover:bg-ash-600 transition-colors"
          title="Dismiss"
        >✕</button>
      </div>
      <div ref="reasoningScroll" class="max-h-[350px] overflow-y-auto p-4 scroll-smooth reasoning-panel">
        <div v-if="!reasoningText" class="text-xs text-ink-500 dark:text-ink-300 italic flex items-center gap-2">
          <span class="w-3 h-3 border-2 border-navy-300 border-t-navy-600 dark:border-t-cream-300 rounded-full animate-spin"></span>
          <span>Menunggu data dari server...</span>
        </div>
        <div v-else>
          <div
            class="text-[11px] leading-relaxed whitespace-pre-wrap break-words text-ink-600 dark:text-ink-300 font-mono"
          >{{ reasoningText }}</div>
        </div>
        <div v-if="generating && !contentText" class="flex items-center gap-2 py-2 px-3 rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200/60 dark:border-amber-700/40 mt-3">
          <div class="thinking-dots">
            <span></span><span></span><span></span>
          </div>
          <span class="text-[11px] text-amber-700 dark:text-amber-300 animate-pulse">Menyusun paper...</span>
        </div>
      </div>
    </div>

    <!-- Content output box (separate from reasoning) -->
    <div
      v-if="contentText"
      class="rounded-xl border border-cream-300/60 dark:border-ash-600/60 bg-white dark:bg-ash-900 overflow-hidden shadow-sm"
    >
      <div class="flex items-center gap-2 px-4 py-2.5 border-b border-cream-300/60 dark:border-ash-600/60 bg-gradient-to-r from-emerald-50 to-cream-50 dark:from-emerald-900/20 dark:to-ash-800">
        <span class="w-2 h-2 rounded-full" :class="generating ? 'bg-emerald-500 animate-pulse' : 'bg-emerald-600'"></span>
        <span class="text-xs font-semibold text-emerald-800 dark:text-emerald-200">
          {{ generating ? '📄 Generating Paper...' : '✅ Generation Complete' }}
        </span>
        <span v-if="generating" class="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">(streaming)</span>
        <button
          v-if="!generating"
          @click="dismissGenerationPanel"
          class="ml-auto text-ink-500 hover:text-ink-900 dark:hover:text-ink-50 text-xs px-1.5 py-0.5 rounded hover:bg-cream-200 dark:hover:bg-ash-600 transition-colors"
          title="Dismiss"
        >✕</button>
      </div>
      <div ref="contentScrollRef" class="max-h-[600px] overflow-y-auto p-4 scroll-smooth">
        <div 
          ref="contentRenderEl"
          class="content-render text-[12px] leading-relaxed text-ink-800 dark:text-ink-100 whitespace-pre-wrap break-words"
          v-html="renderedContentHtml"
        ></div>
      </div>
    </div>

    <!-- Image Generation Progress — shown BELOW completion during image generation -->
    <div
      v-if="imageGenProgress.total > 0"
      class="rounded-xl border border-cream-300/60 dark:border-ash-600/60 bg-white dark:bg-ash-900 overflow-hidden shadow-sm"
    >
      <div class="flex items-center gap-2 px-4 py-2.5 border-b border-cream-300/60 dark:border-ash-600/60 bg-gradient-to-r from-blue-50 to-cream-50 dark:from-blue-900/20 dark:to-ash-800">
        <span class="w-2 h-2 rounded-full" :class="imageGenProgress.done < imageGenProgress.total ? 'bg-blue-500 animate-pulse' : 'bg-emerald-500'"></span>
        <span class="text-xs font-semibold text-blue-800 dark:text-blue-200">
          {{ imageGenProgress.done < imageGenProgress.total ? '🖼️ Generating Images...' : '✅ Images Complete' }}
        </span>
        <span class="text-[10px] text-blue-600 dark:text-blue-400 font-medium ml-auto tabular-nums">
          {{ imageGenProgress.done }}/{{ imageGenProgress.total }}
        </span>
      </div>
      <div class="p-4">
        <div class="w-full bg-cream-200 dark:bg-ash-700 rounded-full h-2.5 mb-2">
          <div 
            class="bg-blue-600 h-2.5 rounded-full transition-all duration-500 ease-out" 
            :style="{ width: `${imageGenProgress.total ? Math.floor((imageGenProgress.done / imageGenProgress.total) * 100) : 0}%` }"
          ></div>
        </div>
        <p v-if="imageGenProgress.message" class="text-[11px] text-ink-600 dark:text-ink-300 mt-1.5 animate-pulse">
          {{ imageGenProgress.message }}
        </p>
      </div>
    </div>

    <!-- Existing file picker dialog (dari paper ini) -->
    <AppDialog v-if="existingFilePickerOpen" :open="existingFilePickerOpen" title="Pilih file" @close="existingFilePickerOpen = false">
      <div class="space-y-2 max-h-60 overflow-y-auto">
        <div v-if="!paperFilesList.length" class="text-xs text-ink-500 dark:text-ink-300 italic p-2">
          Belum ada file yang diupload ke paper ini.
        </div>
        <!-- Select All -->
        <label
          v-if="paperFilesList.length"
          class="flex items-center gap-2 text-xs font-semibold cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-700 p-2 rounded border-b border-cream-200 dark:border-ash-600"
        >
          <input type="checkbox" :checked="areAllExistingPicked" @change="toggleSelectAllExisting" class="rounded" />
          <span class="flex-1">Pilih Semua</span>
          <span class="text-ink-500 dark:text-ink-300 text-[10px] shrink-0">{{ pickedExistingFiles.length }} / {{ paperFilesList.length }}</span>
        </label>
        <label
          v-for="pf in paperFilesList"
          :key="pf.id"
          class="flex items-center gap-2 text-xs cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-700 p-2 rounded"
        >
          <input type="checkbox" v-model="pickedExistingFiles" :value="pf.id" class="rounded" />
          <span class="flex-1 truncate" :title="pf.original_name || pf.filename">{{ pf.original_name || pf.filename }}</span>
          <span class="text-ink-500 dark:text-ink-300 text-[10px] shrink-0">{{ formatFileSize(pf.size) }}</span>
        </label>
      </div>
      <template #actions>
        <button @click="existingFilePickerOpen = false" class="px-3 py-1.5 text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button
          @click="confirmExistingFiles"
          :disabled="!pickedExistingFiles.length"
          class="px-3 py-1.5 text-sm rounded-lg bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-40"
        >Tambah ({{ pickedExistingFiles.length }})</button>
      </template>
    </AppDialog>

    <!-- Draft picker dialog -->
    <AppDialog v-if="draftPickerOpen" :open="draftPickerOpen" title="Pilih draft dari Chat" @close="draftPickerOpen = false">
      <div class="space-y-2 max-h-60 overflow-y-auto">
        <div v-if="!draftsList.length" class="text-xs text-ink-500 dark:text-ink-300 p-3 text-center space-y-1">
          <p>Belum ada draft dari Chat.</p>
          <p class="text-[10px]">Buka tab <strong>💬 AI Chat</strong>, lalu klik <strong>Export Draft</strong> untuk menyimpan percakapan sebagai draft.</p>
        </div>
        <label
          v-for="d in draftsList"
          :key="d.id"
          class="flex items-center gap-2 text-xs cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-700 p-2 rounded"
        >
          <input type="checkbox" v-model="pickedDrafts" :value="d.name" class="rounded" />
          <span class="flex-1 truncate font-medium">{{ d.name }}</span>
          <span class="text-ink-500 dark:text-ink-300 text-[10px] shrink-0">{{ (d.content_length || 0).toLocaleString() }} chars</span>
        </label>
      </div>
      <template #actions>
        <button @click="draftPickerOpen = false" class="px-3 py-1.5 text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button
          @click="confirmDraftPicker"
          :disabled="!pickedDrafts.length"
          class="px-3 py-1.5 text-sm rounded-lg bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-40"
        >Tambah ({{ pickedDrafts.length }})</button>
      </template>
    </AppDialog>

    <!-- Data analysis picker dialog (Dari Data) -->
    <AppDialog v-if="dataAnalysisPickerOpen" :open="dataAnalysisPickerOpen" title="Pilih hasil analisis Data" @close="dataAnalysisPickerOpen = false">
      <p class="text-xs text-ink-500 dark:text-ink-300 mb-2">Tabel, grafik, dan hasil analisis dari tab Data akan ditambahkan ke bucket Data.</p>
      <div class="space-y-2 max-h-72 overflow-y-auto">
        <label
          v-for="src in dataAnalysisSources"
          :key="src.idx"
          class="flex items-start gap-2 text-xs cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-700 p-2 rounded border border-transparent"
          :class="dataAnalysisSelected.has(src.idx) ? 'border-navy-400 dark:border-cream-400 bg-navy-50 dark:bg-ash-700' : ''"
        >
          <input type="checkbox" :checked="dataAnalysisSelected.has(src.idx)" @change="toggleDataAnalysisItem(src.idx)" class="rounded mt-0.5" />
          <div class="flex-1 min-w-0">
            <div class="font-medium text-ink-900 dark:text-ink-50 truncate">{{ src.name }}</div>
            <div class="text-[10px] text-ink-500 dark:text-ink-300 mt-0.5">
              <span v-if="src.tableCount">📋 {{ src.tableCount }} tabel</span>
              <span v-if="src.chartCount" class="ml-1">📈 {{ src.chartCount }} grafik</span>
              <span v-if="src.hasAnalysis" class="ml-1">💡 analisis</span>
              <span class="ml-1 text-ink-400 dark:text-ink-500">({{ src.type }})</span>
            </div>
            <div v-if="src.analysis" class="text-[10px] text-ink-400 dark:text-ink-500 mt-1 line-clamp-2">{{ src.analysis }}</div>
          </div>
        </label>
        <div v-if="!dataAnalysisSources.length" class="text-xs text-ink-500 dark:text-ink-300 p-3 text-center space-y-1">
          <p>Belum ada hasil analisis data.</p>
          <p class="text-[10px]">Buka tab <strong>📊 Data</strong>, upload file (CSV/Excel/PDF), lalu klik <strong>Mulai Ekstrak</strong> untuk menghasilkan tabel & grafik.</p>
        </div>
      </div>
      <template #actions>
        <button @click="dataAnalysisPickerOpen = false" class="px-3 py-1.5 text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button
          @click="confirmDataAnalysisPicker"
          :disabled="!dataAnalysisSelected.size"
          class="px-3 py-1.5 text-sm rounded-lg bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-40"
        >Tambah ({{ dataAnalysisSelected.size }})</button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { usePaperStore } from '../stores/paper'
import { useAuthStore } from '../stores/auth'
import { usePaperJobsStore } from '../stores/paperJobs'
import { useImageGenStore } from '../stores/imageGen'
import api from '../api'
import AppDialog from './AppDialog.vue'
import { useToolsStore } from '../stores/tools'
import { useUiStore } from '../stores/ui'

const store = usePaperStore()
const auth = useAuthStore()
const jobsStore = usePaperJobsStore()
const toolsStore = useToolsStore()
const uiStore = useUiStore()

const topic = ref('')
const generating = ref(false)
const generatingTopic = ref('')
const connectionLost = ref(false)  // SSE stream dropped - backend may still be running
const dataInputRef = ref(null)
const refInputRef = ref(null)

// Progress tracking
const displayProgress = ref(0)
let _progressTimer = null

// Streaming output — split into reasoning (thinking) and content (output)
const reasoningText = ref('')
const contentText = ref('')
const imageGenProgress = ref({ total: 0, done: 0, message: '' })
const reasoningScroll = ref<HTMLElement | null>(null)
const contentScrollRef = ref<HTMLElement | null>(null)
const contentRenderEl = ref<HTMLElement | null>(null)

// Render contentText with LaTeX support — uses bundled KaTeX via composable
import { renderRichText } from '../composables/useMathRender'
import { useSanitize } from '../composables/useSanitize'

const { sanitizeHtml } = useSanitize()

const renderedContentHtml = computed(() => {
  if (!contentText.value) return ''
  let text = contentText.value
  
  // Filter out raw JSON paper structure (backend may stream it for debug/recovery)
  // Match ```json...``` or {...} blocks that look like full paper structure
  text = text.replace(/```json\s*\{[\s\S]*?"sections"[\s\S]*?\}\s*```/gi, '[Paper JSON structure hidden]')
  
  // Also filter standalone JSON objects that span multiple lines with "sections" key
  text = text.replace(/^\s*\{[\s\S]*?"sections"[\s\S]*?\}\s*$/gm, '[Paper structure received]')
  
  // Filter individual streamed section objects (tables, formulas, etc.)
  // Pattern: {"id": "...", "TableNumber": "..."} or {"id": "...", "latex": "..."} etc.
  text = text.replace(/```json\s*\{[\s\S]*?"(?:TableNumber|FormulaNumber|Headers|Rows|latex)"[\s\S]*?\}\s*```/gi, '[Section data hidden]')
  text = text.replace(/^\s*\{[\s\S]*?"(?:TableNumber|FormulaNumber|Headers|Rows|latex)"[\s\S]*?\}\s*$/gm, '[Section data received]')
  
  // Always use rich text render (handles LaTeX, escapes HTML), then sanitize via DOMPurify
  return sanitizeHtml(renderRichText(text))
})

// Call checkActiveJob on mount
onMounted(async () => {
  // Clean up zombie stream states (>30min old) before checking
  jobsStore.clearStaleStreamState()
  const ss = jobsStore.streamState
  if (ss && ss.generating && ss.paperId === store.currentPaperId) {
    // Restore from persisted stream state (survives tab switch + refresh)
    generating.value = true
    generatingTopic.value = ss.generatingTopic || ''
    displayProgress.value = ss.displayProgress || 0
    reasoningText.value = ss.reasoningText || ''
    contentText.value = ss.contentText || ''
    _startTime = ss.startedAt || Date.now()
    // Stream state doesn't carry the selection fields — pull them from the
    // per-paper sessionStorage slot so checkbox selections (facts/files/
    // tables/drafts) survive a refresh that lands in this branch.
    try {
      const raw = sessionStorage.getItem(_sessionKey(store.currentPaperId))
      if (raw) {
        const st = JSON.parse(raw)
        if (st.selectedDrafts) selectedDrafts.value = st.selectedDrafts
      }
    } catch { /* ignore */ }
    startProgressTicker()
    startTimeTracker()
    // SSE connection is dead after refresh/tab-switch. Check if backend
    // already saved the paper (generation completed while we were away).
    try {
      const age = Date.now() - (ss._updatedAt || ss.startedAt || 0)
      if (age > 30000) {
        // Stream state >30s old — likely disconnected. Reload from DB.
        await store.loadPaperFromDb(store.currentPaperId)
        // If paper now has real content (sections with data), generation
        // finished while we were away → clear the zombie stream.
        if (store.paper.sections?.length > 0 && store.paper.sections.some(s => s.content?.length > 0)) {
          jobsStore.clearStreamState()
          generating.value = false
          displayProgress.value = 100
          stopProgressTicker()
          stopTimeTracker()
          // Keep reasoningText visible — user wants to see the thinking trace
          // Show completion marker in content panel
          contentText.value = '\n✅ [Paper selesai digenerate di server — konten sudah dimuat ke editor]\n'
        } else {
          // Paper not finished yet — start DB polling for recovery
          connectionLost.value = true
          _startDbPolling()
        }
      }
    } catch { /* DB load failed — keep streaming UI */ }
  } else {
    restoreState()
  }
  checkActiveJob()
  if (_pollTimer) clearInterval(_pollTimer)
  _pollTimer = setInterval(checkActiveJob, 4000)
  // Save state before page unload (F5 / close tab)
  window.addEventListener('beforeunload', _handleBeforeUnload)
  // Refresh drafts list when chat exports a new draft (cross-component signal)
  window.addEventListener('chat-draft-saved', _handleDraftSaved)
  window.addEventListener('data-sources-updated', _handleDataSourcesUpdated)
  // Close + picker dropdowns when clicking outside
  document.addEventListener('click', _handleClickOutside)
  // Load chat drafts for current paper
  if (store.currentPaperId) {
    loadDrafts(store.currentPaperId)
    loadPaperFilesList()
    loadLiterature()
  }
})

function _handleDraftSaved(e: any) {
  // Re-fetch the drafts list so the new draft shows up in the checkbox
  // selector without a manual reload. Scope to the current paper.
  const pid = e?.detail?.paperId || store.currentPaperId
  if (pid && pid === store.currentPaperId) loadDrafts(pid)
}

function _handleDataSourcesUpdated() {
  dataSourcesVersion.value++
}

function _handleBeforeUnload() {
  saveState()
  if (generating.value) {
    jobsStore.setStreamState({
      paperId: store.currentPaperId,
      generating: true,
      generatingTopic: generatingTopic.value,
      displayProgress: displayProgress.value,
      reasoningText: reasoningText.value,
      contentText: contentText.value,
      startedAt: _startTime,
      prompt: generatingTopic.value,
    })
  }
}

onUnmounted(() => {
  _stopStatusPoll()
  _stopChartRefreshPolling()
  window.removeEventListener('beforeunload', _handleBeforeUnload)
  window.removeEventListener('chat-draft-saved', _handleDraftSaved)
  window.removeEventListener('data-sources-updated', _handleDataSourcesUpdated)
  document.removeEventListener('click', _handleClickOutside)
  if (_pollTimer) clearInterval(_pollTimer)
  // Save state to Pinia store if actively generating (survives panel switch)
  if (generating.value) {
    jobsStore.setStreamState({
      paperId: store.currentPaperId,
      generating: true,
      generatingTopic: generatingTopic.value,
      displayProgress: displayProgress.value,
      reasoningText: reasoningText.value,
      contentText: contentText.value,
      startedAt: _startTime,
      prompt: generatingTopic.value,
    })
  }
  stopProgressTicker()
  stopTimeTracker()
  stopSSEPolling()
  _stopDbPolling()
  if (_cancelTimer) { clearTimeout(_cancelTimer); _cancelTimer = null }
})

// File attachments — DUA bucket terpisah:
//   dataFiles      → docx/csv/xlsx/pdf berisi DATA mentah (untuk tabel/grafik)
//   referenceFiles → paper sitasi atau draft user (konteks + sumber sitasi)
// Tiap entry: { name, file, text, extracted }
const dataFiles = ref([])       // sumber data
const referenceFiles = ref([])  // referensi/draft
const dataDragOver = ref(false)
const refDragOver = ref(false)

// Chat drafts
const selectedDrafts = ref<string[]>([])

// Chat drafts list
const draftsList = ref<any[]>([])

// + picker UI state
const dataPickerOpen = ref(false)
const refPickerOpen = ref(false)
const dataPickerRef = ref<HTMLElement | null>(null)
const refPickerRef = ref<HTMLElement | null>(null)
// Existing-file picker dialog (dari paper ini)
const existingFilePickerOpen = ref(false)
const existingFileTarget = ref<'data' | 'ref'>('ref')
// Data analysis picker (Dari Data)
const dataAnalysisPickerOpen = ref(false)
const dataAnalysisSources = ref<any[]>([])
const dataAnalysisSelected = ref<Set<number>>(new Set())
const dataSourcesVersion = ref(0)
// Check if data analysis is available (from DataTab localStorage)
const hasDataAnalysis = computed(() => {
  // Depend on version counter so we can force re-evaluation
  void dataSourcesVersion.value
  if (!store.currentPaperId) return false
  try {
    const lsKey = `pg_data_sources_${store.currentPaperId}`
    const raw = localStorage.getItem(lsKey)
    if (!raw) return false
    const arr = JSON.parse(raw)
    return Array.isArray(arr) && arr.length > 0
  } catch {
    return false
  }
})
const paperFilesList = ref<any[]>([])
const pickedExistingFiles = ref<any[]>([])
// Inline file list picks (Data & File)
const pickedDataFiles = ref<any[]>([])
const pickedRefFiles = ref<any[]>([])

// Literatur section
interface LitFullItem {
  id: number
  title: string
  authors?: string[]
  year?: number | null
  publisher?: string
  venue?: string
  doi?: string | null
  citations?: number
  abstract?: string
}
const literatureItems = ref<LitFullItem[]>([])
const literatureLoading = ref(false)

// Generation options
const enablePaperReview = ref(false)
const enableImageGen = ref(true)
const enableRevisiSemua = ref(false)
const enableRegenerateImages = ref(false)  // 4th checkbox: Re-generate Images

async function loadPaperFilesList() {
  if (!store.currentPaperId) { paperFilesList.value = []; return }
  try {
    const res = await api.get(`/api/papers/${store.currentPaperId}/files`)
    paperFilesList.value = res.data?.files || []
  } catch (e) {
    console.warn('[PaperfullTab] failed to load paper files:', e)
    paperFilesList.value = []
  }
}

async function confirmDataFiles() {
  for (const fileId of pickedDataFiles.value) {
    const pf = paperFilesList.value.find(p => p.id === fileId)
    if (!pf) continue
    if (dataFiles.value.some(f => f.name === (pf.original_name || pf.filename))) continue
    try {
      const res = await api.get(`/api/papers/${store.currentPaperId}/files/${fileId}/preview`)
      const text = res.data?.text || res.data?.preview || ''
      dataFiles.value.push({
        name: pf.original_name || pf.filename,
        file: null,
        text,
        extracted: true,
        isExisting: true,
        existingFileId: fileId,
      })
    } catch (e) {
      console.warn('[PaperfullTab] failed to load preview for file', fileId, e)
    }
  }
  pickedDataFiles.value = []
}

async function confirmRefFiles() {
  for (const fileId of pickedRefFiles.value) {
    const pf = paperFilesList.value.find(p => p.id === fileId)
    if (!pf) continue
    if (referenceFiles.value.some(f => f.name === (pf.original_name || pf.filename))) continue
    try {
      const res = await api.get(`/api/papers/${store.currentPaperId}/files/${fileId}/preview`)
      const text = res.data?.text || res.data?.preview || ''
      referenceFiles.value.push({
        name: pf.original_name || pf.filename,
        file: null,
        text,
        extracted: true,
        isExisting: true,
        existingFileId: fileId,
      })
    } catch (e) {
      console.warn('[PaperfullTab] failed to load preview for file', fileId, e)
    }
  }
  pickedRefFiles.value = []
}

// ── Select All helpers ──
const areAllDataPicked = computed(() => {
  return paperFilesList.value.length > 0 && pickedDataFiles.value.length === paperFilesList.value.length
})
function toggleSelectAllData(): void {
  if (areAllDataPicked.value) {
    pickedDataFiles.value = []
  } else {
    pickedDataFiles.value = paperFilesList.value.map(f => f.id)
  }
}
const areAllRefPicked = computed(() => {
  return paperFilesList.value.length > 0 && pickedRefFiles.value.length === paperFilesList.value.length
})
function toggleSelectAllRef(): void {
  if (areAllRefPicked.value) {
    pickedRefFiles.value = []
  } else {
    pickedRefFiles.value = paperFilesList.value.map(f => f.id)
  }
}
const areAllExistingPicked = computed(() => {
  return paperFilesList.value.length > 0 && pickedExistingFiles.value.length === paperFilesList.value.length
})
function toggleSelectAllExisting(): void {
  if (areAllExistingPicked.value) {
    pickedExistingFiles.value = []
  } else {
    pickedExistingFiles.value = paperFilesList.value.map(f => f.id)
  }
}
// ── End Select All ──

// Literatur functions — otomatis di-inject ke prompt oleh backend.
// Cukup check/uncheck di tab Literatur; PaperfullTab hanya preview.
async function loadLiterature(): Promise<void> {
  if (!store.currentPaperId) return
  literatureLoading.value = true
  try {
    const res = await api.get(`/api/papers/${store.currentPaperId}/literature/checked`)
    literatureItems.value = (res.data?.items || []).map((it: any) => ({
      id: it.id,
      title: it.title || '',
      authors: it.authors || [],
      year: it.year || null,
      publisher: it.publisher || it.venue || '',
      venue: it.venue || '',
      doi: it.doi || null,
      citations: it.citations ?? 0,
      abstract: it.abstract || '',
    }))
  } catch {
    literatureItems.value = []
  } finally {
    literatureLoading.value = false
  }
}

// Draft picker dialog
const draftPickerOpen = ref(false)
const pickedDrafts = ref<string[]>([])

let _pollTimer = null
const activeJob = ref(null)
let _startTime = null
let _timeTimer = null
let _cancelTimer = null
let _lastStreamSync = 0  // Timer-based stream sync (every 2s, not lossy modulo)

// Sync stream state to Pinia/localStorage every ~2 seconds.
// Called from both thinking and content event handlers.
function _syncStreamIfNeeded() {
  const now = Date.now()
  if (now - _lastStreamSync < 2000) return
  _lastStreamSync = now
  jobsStore.setStreamState({
    paperId: store.currentPaperId,
    generating: true,
    generatingTopic: generatingTopic.value,
    displayProgress: displayProgress.value,
    reasoningText: reasoningText.value,
    contentText: contentText.value,
    startedAt: _startTime,
    prompt: generatingTopic.value,
  })
}

const timeElapsed = ref('')

// Session persistence key — SCOPED PER PAPER. A single global key caused
// paper 1's reasoning/content/topic to bleed into paper 2 on restore.
// Each paper gets its own sessionStorage slot keyed by its id. Always call
// _sessionKey(store.currentPaperId) at the moment of read/write so it tracks
// the currently-open paper, never a stale id captured at setup time.
function _sessionKey(paperId) {
  return `paperfull_state:${paperId || '_none'}`
}

// Computed properties

// Save state to sessionStorage
function saveState() {
  try {
    const state = {
      topic: topic.value,
      generating: generating.value,
      generatingTopic: generatingTopic.value,
      displayProgress: displayProgress.value,
      reasoningText: reasoningText.value,
      contentText: contentText.value,
      startTime: _startTime,
      jobId: activeJob.value?.id || activeJob.value?.job_id || null,
      dataFiles: dataFiles.value.map(f => ({
        name: f.name,
        text: f.text || '',
        extracted: f.extracted || false,
        isExisting: f.isExisting || false,
        existingFileId: f.existingFileId || null,
        isDataAnalysis: f.isDataAnalysis || false,
      })),
      referenceFiles: referenceFiles.value.map(f => ({
        name: f.name,
        text: f.text || '',
        extracted: f.extracted || false,
        isDraft: f.isDraft || false,
        draftName: f.draftName || null,
        isExisting: f.isExisting || false,
        existingFileId: f.existingFileId || null,
      })),
      selectedDrafts: selectedDrafts.value,
    }
    sessionStorage.setItem(_sessionKey(store.currentPaperId), JSON.stringify(state))
  } catch { /* ignore */ }
}

// Restore state from sessionStorage
function restoreState() {
  try {
    const raw = sessionStorage.getItem(_sessionKey(store.currentPaperId))
    if (!raw) return
    const state = JSON.parse(raw)
    if (state.topic) topic.value = state.topic
    if (state.generatingTopic) generatingTopic.value = state.generatingTopic
    if (state.reasoningText) reasoningText.value = state.reasoningText
    if (state.contentText) contentText.value = state.contentText
    if (state.startTime) _startTime = state.startTime
    // Restore attached files per bucket. The File object isn't serializable, so
    // restored entries carry file:null and a `stale` flag — the UI shows them as
    // "perlu re-attach" (not a false ✓) and generate() skips them. This fixes the
    // old silent data-loss where chips looked attached but were never uploaded.
    const _restoreBucket = (arr) => (arr || []).map(f => ({
      name: f.name,
      file: null,
      text: f.text || '',
      extracted: f.extracted || false,
      // Virtual entries (draft/existing/data-analysis) have text content in sessionStorage → not stale.
      // Real uploaded files lose their File object → stale (need re-attach).
      stale: !f.isDraft && !f.isExisting && !f.isDataAnalysis,
      isDraft: f.isDraft || false,
      draftName: f.draftName || null,
      isExisting: f.isExisting || false,
      existingFileId: f.existingFileId || null,
      isDataAnalysis: f.isDataAnalysis || false,
    }))
    if (state.dataFiles && state.dataFiles.length) {
      dataFiles.value = _restoreBucket(state.dataFiles)
    }
    if (state.referenceFiles && state.referenceFiles.length) {
      referenceFiles.value = _restoreBucket(state.referenceFiles)
    }
    // Back-compat: old single-bucket key → treat as reference
    if (state.attachedFiles && state.attachedFiles.length && !state.referenceFiles) {
      referenceFiles.value = _restoreBucket(state.attachedFiles)
    }
    if (state.selectedDrafts) selectedDrafts.value = state.selectedDrafts
    if (state.generating) {
      generating.value = true
      displayProgress.value = state.displayProgress || 0
      // Start local progress ticker
      startProgressTicker()
      startTimeTracker()
      // Resume by reading the LIVE backend position (reasoning + content)
      // from Redis via /generate-status. Shows how far the backend got and
      // keeps updating progressively. Falls back to DB polling internally
      // when the snapshot is gone (TTL) or generation already finished.
      connectionLost.value = true
      _startStatusPoll()
    }
  } catch { /* ignore */ }
}

function clearState() {
  try { sessionStorage.removeItem(_sessionKey(store.currentPaperId)) } catch { /* ignore */ }
}

// Progress ticker: 0→60% in 10 min, 60→95% in 5 min, stuck at 95% until done
// ponytail: ticker is a floor — never regress progress from SSE/content events
function startProgressTicker() {
  stopProgressTicker()
  if (!_startTime) _startTime = Date.now()
  _progressTimer = setInterval(() => {
    const elapsed = (Date.now() - _startTime) / 1000
    let pct
    if (elapsed <= 600) {
      // Phase 1: 0→60% over 600s (10 min)
      pct = Math.floor((elapsed / 600) * 60)
    } else if (elapsed <= 900) {
      // Phase 2: 60→95% over 300s (5 min)
      pct = 60 + Math.floor(((elapsed - 600) / 300) * 35)
    } else {
      // Phase 3: stuck at 95% until done
      pct = 95
    }
    // Never regress — SSE content/progress events may have pushed higher
    if (pct > displayProgress.value) {
      displayProgress.value = pct
      jobsStore.updateStreamProgress(pct)
    }
    saveState()
  }, 5000)
}

function stopProgressTicker() {
  if (_progressTimer) { clearInterval(_progressTimer); _progressTimer = null }
}

function startTimeTracker() {
  stopTimeTracker()
  if (!_startTime) return
  const update = () => {
    const elapsed = Math.floor((Date.now() - _startTime) / 1000)
    const min = Math.floor(elapsed / 60)
    const sec = elapsed % 60
    timeElapsed.value = `⏱ ${min}m ${sec.toString().padStart(2, '0')}s elapsed`
  }
  update()
  _timeTimer = setInterval(update, 1000)
}

function stopTimeTracker() {
  if (_timeTimer) { clearInterval(_timeTimer); _timeTimer = null }
}

// ─── Chat Drafts ───
const allDraftsSelected = computed(() => {
  const total = draftsList.value.length
  return total > 0 && selectedDrafts.value.length === total
})

function toggleAllDrafts() {
  if (allDraftsSelected.value) {
    selectedDrafts.value = []
  } else {
    selectedDrafts.value = draftsList.value.map(d => d.name)
  }
}

async function loadDrafts(paperId) {
  if (!paperId) return
  try {
    const res = await api.get(`/api/papers/${paperId}/drafts`)
    draftsList.value = res.data?.drafts || []
    // Prune selectedDrafts to names that still exist
    const validNames = new Set(draftsList.value.map(d => d.name))
    selectedDrafts.value = selectedDrafts.value.filter(n => validNames.has(n))
  } catch (e) {
    console.warn('[PaperfullTab] loadDrafts failed:', e)
    draftsList.value = []
  }
}

// File handling — dua bucket: 'data' dan 'reference'
function triggerDataInput() {
  if (dataInputRef.value) dataInputRef.value.click()
}
function triggerRefInput() {
  if (refInputRef.value) refInputRef.value.click()
}

const _ACCEPT_RE = /\.(pdf|docx?|xlsx?|csv|txt|md)$/i
function _pushFiles(bucket, fileList) {
  if (!fileList || !fileList.length) return
  const target = bucket === 'data' ? dataFiles : referenceFiles
  for (const file of fileList) {
    if (!_ACCEPT_RE.test(file.name)) {
      store.showToast(`File "${file.name}" dilewati — format tidak didukung (pdf/docx/xlsx/csv/txt/md).`, 'warning')
      continue
    }
    // Dedupe by name: replace stale entries (file:null), skip if fresh already exists
    const staleIdx = target.value.findIndex(f => f.name === file.name && !f.file)
    if (staleIdx !== -1) {
      // Replace stale entry with fresh file
      target.value.splice(staleIdx, 1, { name: file.name, file, text: '', extracted: false })
      continue
    }
    if (target.value.some(f => f.name === file.name && f.file)) continue
    target.value.push({ name: file.name, file, text: '', extracted: false })
  }
  saveState()
}

function onDataFileChange(event) {
  _pushFiles('data', event.target.files)
  event.target.value = ''
}
function onRefFileChange(event) {
  _pushFiles('reference', event.target.files)
  event.target.value = ''
}

function removeDataFile(index) {
  dataFiles.value.splice(index, 1)
  saveState()
}
function removeRefFile(index) {
  referenceFiles.value.splice(index, 1)
  saveState()
}

// Drag-and-drop
function onDataDrop(event) {
  event.preventDefault()
  dataDragOver.value = false
  if (generating.value || activeJob.value) return
  _pushFiles('data', event.dataTransfer?.files)
}
function onRefDrop(event) {
  event.preventDefault()
  refDragOver.value = false
  if (generating.value || activeJob.value) return
  _pushFiles('reference', event.dataTransfer?.files)
}

// ── + picker: existing files (dari paper ini) ─────────────────────────
async function openExistingFilePicker(target: 'data' | 'ref') {
  if (!store.currentPaperId) {
    store.showToast('Simpan paper dulu sebelum memilih file', 'warning')
    return
  }
  existingFileTarget.value = target
  pickedExistingFiles.value = []
  existingFilePickerOpen.value = true
  // Fetch the paper's PaperFile list (already-uploaded files)
  try {
    const res = await api.get(`/api/papers/${store.currentPaperId}/files`)
    paperFilesList.value = res.data?.files || []
  } catch (e) {
    console.warn('[PaperfullTab] failed to load paper files:', e)
    paperFilesList.value = []
    store.showToast('Gagal memuat daftar file paper', 'error')
  }
}

function formatFileSize(bytes) {
  if (!bytes && bytes !== 0) return '?'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function confirmExistingFiles() {
  const target = existingFileTarget.value === 'data' ? dataFiles : referenceFiles
  // Fetch each picked file's preview text and add as a virtual entry.
  // We DON'T re-upload; we use the existing PaperFile preview as the text.
  for (const fileId of pickedExistingFiles.value) {
    const pf = paperFilesList.value.find(p => p.id === fileId)
    if (!pf) continue
    // Dedupe by name within the bucket
    if (target.value.some(f => f.name === (pf.original_name || pf.filename))) continue
    try {
      const res = await api.get(`/api/papers/${store.currentPaperId}/files/${fileId}/preview`)
      const text = res.data?.text || res.data?.preview || ''
      target.value.push({
        name: pf.original_name || pf.filename,
        file: null,           // no File object — sent as pre-extracted text
        text,
        extracted: true,
        isExisting: true,     // marker for dedupe + UI
        existingFileId: fileId,
      })
    } catch (e) {
      console.warn('[PaperfullTab] failed to load preview for file', fileId, e)
      store.showToast(`Gagal memuat preview ${pf.original_name || pf.filename}`, 'error')
    }
  }
  existingFilePickerOpen.value = false
  pickedExistingFiles.value = []
  saveState()
}

// ── + picker: chat drafts → masuk ke bucket File ─────────────────
function openDraftPicker() {
  pickedDrafts.value = []
  draftPickerOpen.value = true
}

async function confirmDraftPicker() {
  // Fetch each draft's full content and add to referenceFiles as a virtual entry.
  for (const name of pickedDrafts.value) {
    const d = draftsList.value.find(x => x.name === name)
    if (!d) continue
    if (referenceFiles.value.some(f => f.name === `💬 ${name}` || f.draftName === name)) continue
    try {
      const res = await api.get(`/api/papers/${store.currentPaperId}/drafts/${d.id}`)
      const content = res.data?.draft?.content || ''
      referenceFiles.value.push({
        name: `💬 ${name}`,
        file: null,
        text: content,
        extracted: true,
        isDraft: true,
        draftName: name,
      })
    } catch (e) {
      console.warn('[PaperfullTab] failed to load draft', name, e)
      store.showToast(`Gagal memuat draft "${name}"`, 'error')
    }
  }
  draftPickerOpen.value = false
  pickedDrafts.value = []
  saveState()
}

// ── + picker: data analysis results (Dari Data) → masuk ke bucket Data ──
function openDataAnalysisPicker() {
  if (!store.currentPaperId) {
    store.showToast('Simpan paper dulu', 'warning')
    return
  }
  // Read data sources from DataTab's localStorage
  const lsKey = `pg_data_sources_${store.currentPaperId}`
  try {
    const raw = localStorage.getItem(lsKey)
    if (!raw) {
      dataAnalysisSources.value = []
      dataAnalysisSelected.value = new Set()
      dataAnalysisPickerOpen.value = true
      return
    }
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr) || arr.length === 0) {
      dataAnalysisSources.value = []
      dataAnalysisSelected.value = new Set()
      dataAnalysisPickerOpen.value = true
      return
    }
    // Build picker items: each source with its tables, charts, and analysis
    const items: any[] = []
    arr.forEach((src, si) => {
      const tables = src.tables || []
      const hasTables = tables.length > 0
      const hasAnalysis = !!src.analysis || !!(src.aiAnalysis)
      const chartCount = (src.chartImages || []).length
      const chartIds = tables.flatMap((t: any) => t.chartIds || [])
      items.push({
        idx: si,
        name: src.name || `Sumber ${si + 1}`,
        type: src.type || 'upload',
        tableCount: tables.length,
        chartCount: chartCount || chartIds.length,
        hasAnalysis,
        analysis: src.analysis || src.aiAnalysis || '',
        // Snapshot data for embedding
        columns: src.columns || [],
        rows: src.rows || [],
        chartImages: src.chartImages || [],
        tables,
      })
    })
    dataAnalysisSources.value = items
    dataAnalysisSelected.value = new Set()
    dataAnalysisPickerOpen.value = true
  } catch (e) {
    console.warn('[PaperfullTab] failed to load data sources', e)
    store.showToast('Gagal membaca data analisis', 'error')
  }
}

function toggleDataAnalysisItem(idx: number) {
  const s = new Set(dataAnalysisSelected.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  dataAnalysisSelected.value = s
}

function confirmDataAnalysisPicker() {
  for (const idx of dataAnalysisSelected.value) {
    const src = dataAnalysisSources.value[idx]
    if (!src) continue
    const entryName = `📊 ${src.name}`
    if (dataFiles.value.some(f => f.name === entryName)) continue

    // Build text content: tables + analysis + chart paths
    const parts: string[] = []
    parts.push(`# Data Analisis: ${src.name}`)
    parts.push(`Sumber: ${src.type} | ${src.tableCount} tabel | ${src.chartCount} grafik`)
    parts.push('')

    // Tables
    for (const t of src.tables) {
      parts.push(`## Tabel: ${t.name || 'Data'}`)
      if (t.columns?.length) {
        parts.push('| ' + t.columns.join(' | ') + ' |')
        parts.push('| ' + t.columns.map(() => '---').join(' | ') + ' |')
        for (const row of (t.rows || [])) {
          parts.push('| ' + row.map((c: any) => (c == null ? '' : String(c))).join(' | ') + ' |')
        }
        parts.push('')
      }
    }

    // Analysis text
    if (src.analysis) {
      parts.push('## Hasil Analisis')
      parts.push(src.analysis)
      parts.push('')
    }

    // Chart image paths
    if (src.chartImages?.length) {
      parts.push('## Grafik')
      for (const img of src.chartImages) {
        const imgPath = typeof img === 'string' ? img : (img.path || img.url || '')
        const imgTitle = typeof img === 'string' ? img.split('/').pop() : (img.title || img.name || 'chart')
        if (imgPath) parts.push(`- ${imgTitle}: ${imgPath}`)
      }
      parts.push('')
    }

    dataFiles.value.push({
      name: entryName,
      file: null,
      text: parts.join('\n'),
      extracted: true,
      isDataAnalysis: true,
      sourceIdx: idx,
    })
  }
  dataAnalysisPickerOpen.value = false
  dataAnalysisSelected.value = new Set()
  saveState()
}

// Close + picker dropdown when clicking outside
function _handleClickOutside(e) {
  const path = e.composedPath ? e.composedPath() : []
  if (dataPickerOpen.value) {
    const el = dataPickerRef.value
    const parentBtn = el?.closest('.relative')
    if (!path.includes(el) && !path.includes(parentBtn)) {
      dataPickerOpen.value = false
    }
  }
  if (refPickerOpen.value) {
    const el = refPickerRef.value
    const parentBtn = el?.closest('.relative')
    if (!path.includes(el) && !path.includes(parentBtn)) {
      refPickerOpen.value = false
    }
  }
}

// Extract text from file on frontend (for PDF/DOCX we send to backend)
// For CSV/Excel we can try client-side, but for simplicity we send all to backend

async function checkActiveJob() {
  if (!store.currentPaperId) return
  try {
    const { usePaperJobsStore } = await import('../stores/paperJobs.js')
    const jobsStore = usePaperJobsStore()
    await jobsStore.fetchActive(store.currentPaperId)
    const job = jobsStore.activeByPaper[store.currentPaperId]
    activeJob.value = (job && job.id) ? job : null
    
    // If we have an active job but local state doesn't know about it,
    // sync from server state
    if (activeJob.value && !generating.value) {
      generating.value = true
      generatingTopic.value = activeJob.value.prompt || ''
      displayProgress.value = activeJob.value.progress || 5
      _startTime = activeJob.value.started_at ? new Date(activeJob.value.started_at).getTime() : Date.now()
      startProgressTicker()
      startTimeTracker()
      saveState()
      // Start SSE polling for streaming output
      startSSEPolling(activeJob.value.id)
    }
    
    // Don't kill the direct stream just because checkActiveJob finds no RQ job.
    // generate_stream is direct SSE, not RQ — activeJob will always be null during streaming.
    // After refresh: _sseCtrl is null (component remounted) but generating=true from Pinia state.
    // DON'T call finishGeneration() immediately — check if DB has the paper first.
    if (!activeJob.value && generating.value && !_sseCtrl) {
      // Check if stream state is recent enough that generation might still be running
      const ss = jobsStore.streamState
      const age = Date.now() - (ss?._updatedAt || ss?.startedAt || 0)
      if (age < 120000) {
        // <2 min old — generation likely still running on backend.
        // Don't finish — wait for next checkActiveJob poll or DB to have content.
        // But also try to load from DB to see if it completed.
        try {
          await store.loadPaperFromDb(store.currentPaperId)
          if (store.paper.sections?.length > 0 && store.paper.sections.some(s => s.content?.length > 0)) {
            // Paper completed — clear generating state but keep reasoning for display
            generating.value = false
            displayProgress.value = 100
            stopProgressTicker()
            stopTimeTracker()
            jobsStore.clearStreamState()
            // Keep reasoningText visible (don't clear it)
          }
          // else: paper still empty — generation still running, keep waiting
        } catch { /* keep waiting */ }
      } else {
        // >2 min old and no RQ job — genuinely finished or abandoned
        // Try DB load one more time
        try {
          await store.loadPaperFromDb(store.currentPaperId)
        } catch { /* ignore */ }
        generating.value = false
        displayProgress.value = store.paper.sections?.length > 0 ? 100 : 0
        stopProgressTicker()
        stopTimeTracker()
        jobsStore.clearStreamState()
        saveState()
      }
    }
    
    // If job is done (progress >= 100 or status is done)
    if (activeJob.value && (activeJob.value.progress >= 100 || activeJob.value.status === 'done')) {
      finishGeneration()
    }
  } catch {
    activeJob.value = null
  }
}

// SSE polling for streaming output
let _sseCtrl = null
function startSSEPolling(jobId) {
  stopSSEPolling()
  _sseCtrl = new AbortController()
  
  const poll = async () => {
    const delays = [2000, 4000, 6000]
    let retries = 0
    while (true) {
      if (!_sseCtrl || _sseCtrl.signal.aborted) return
      try {
        const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/)
        const headers: Record<string, string> = { 'Accept': 'text/event-stream' }
        if (csrfMatch) headers['X-CSRF-TOKEN'] = decodeURIComponent(csrfMatch[1])
        const res = await fetch(`/api/jobs/${jobId}/stream`, {
          signal: _sseCtrl.signal,
          credentials: 'include',
          headers,
        })
        if (!res.ok) return
        
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        
        while (true) {
          let chunk
          try {
            chunk = await reader.read()
          } catch (readErr) {
            if (readErr.name === 'AbortError' || _sseCtrl?.signal.aborted) return
            throw readErr
          }
          const { done, value } = chunk
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                if (data.stage) {
                  reasoningText.value += `[${data.stage}] ${data.status || ''}\n`
                  if (data.percent) {
                    displayProgress.value = Math.max(displayProgress.value, data.percent)
                  }
                }
                if (data.status === 'complete') {
                  finishGeneration()
                  return
                }
                if (data.status === 'cancelled') {
                  // Don't call cancelGeneration() here — it aborts the stream we're reading from.
                  // Just return and let the outer catch/finally handle cleanup.
                  return
                }
              } catch { /* skip malformed */ }
            }
          }
        }
        // Stream ended cleanly without complete/cancelled — stop polling
        return
      } catch (e) {
        // Network error or abort
        if (_sseCtrl?.signal.aborted) return
        if (retries >= delays.length) return
        const delay = delays[retries++]
        await new Promise(r => setTimeout(r, delay))
      }
    }
  }
  
  poll()
}

function stopSSEPolling() {
  if (_sseCtrl) { _sseCtrl.abort(); _sseCtrl = null }
}

// Live status polling for resume after refresh/disconnect.
// Mirrors the chat /stream-status pattern: reads the incremental reasoning +
// content snapshot the backend writes to Redis, so the UI shows HOW FAR the
// backend has gotten (progressive reasoning + completion) instead of just
// freezing the last sessionStorage snapshot and waiting for the finished DB row.
let _statusPollTimer = null
function _startStatusPoll() {
  _stopStatusPoll()  // Always clear old timer before starting new one
  if (!store.currentPaperId) return
  jobsStore.setConnectionLost(true)
  connectionLost.value = true
  const startedAt = Date.now()
  let _notFoundStreak = 0
  _statusPollTimer = setInterval(async () => {
    // 15min safety timeout
    if (Date.now() - startedAt > 900000) {
      _stopStatusPoll()
      _startDbPolling()  // fall back to DB polling
      return
    }
    try {
      const res = await api.get(`/api/papers/${store.currentPaperId}/generate-status`)
      const st = res.data || {}
      if (st.status === 'streaming') {
        _notFoundStreak = 0
        // Pull live position — replace (not append) since snapshot is cumulative
        if (typeof st.reasoning === 'string' && st.reasoning.length >= reasoningText.value.length) {
          reasoningText.value = st.reasoning
        }
        if (typeof st.content === 'string' && st.content.length >= contentText.value.length) {
          contentText.value = st.content
          displayProgress.value = Math.min(95, Math.max(displayProgress.value, Math.floor(st.content.length / 200)))
          jobsStore.updateStreamProgress(displayProgress.value)
        }
        // Auto-scroll reasoning panel
        nextTick(() => {
          const panel = document.querySelector('.reasoning-panel')
          if (panel) panel.scrollTop = panel.scrollHeight
        })
        saveState()
      } else if (st.status === 'done') {
        // Backend finished — pull the saved paper from DB and finalize
        _stopStatusPoll()
        if (typeof st.content === 'string' && st.content.length > contentText.value.length) {
          contentText.value = st.content
        }
        await manualCheckDb()
      } else if (st.status === 'error') {
        _stopStatusPoll()
        connectionLost.value = false
        jobsStore.setConnectionLost(false)
        generating.value = false
        stopProgressTicker()
        stopTimeTracker()
        contentText.value += `\n[ERROR] ${st.error || 'Generation gagal di server'}\n`
        jobsStore.clearStreamState()
        store.showToast('Generation error: ' + (st.error || 'unknown'), 'error')
        saveState()
      } else {
        // not_found — snapshot expired (TTL) or never written. After a few
        // misses, fall back to DB polling (paper may already be saved).
        _notFoundStreak++
        if (_notFoundStreak >= 3) {
          _stopStatusPoll()
          _startDbPolling()
        }
      }
    } catch { /* keep polling — transient */ }
  }, 2000)
}
function _stopStatusPoll() {
  if (_statusPollTimer) { clearInterval(_statusPollTimer); _statusPollTimer = null }
}

// Chart refresh polling after paper generation completes.
// Charts are generated in background after paper is shown in editor.
let _chartRefreshTimer = null
function _startChartRefreshPolling() {
  if (_chartRefreshTimer) return
  const startedAt = Date.now()
  let lastChartCount = 0
  _chartRefreshTimer = setInterval(async () => {
    // 2min timeout - charts should be ready by then
    if (Date.now() - startedAt > 120000) {
      _stopChartRefreshPolling()
      return
    }
    try {
      await store.loadPaperCharts(store.currentPaperId)
      const currentCount = store.paperCharts?.length || 0
      if (currentCount > lastChartCount) {
        lastChartCount = currentCount
        // New charts detected - could show a notification
        if (currentCount > 0) {
          store.showToast(`📊 ${currentCount} chart(s) tersedia di galeri gambar`, 'info')
        }
      }
      // Stop if no new charts for 10 seconds (assume done)
      if (Date.now() - startedAt > 10000 && currentCount === lastChartCount) {
        _stopChartRefreshPolling()
      }
    } catch { /* ignore */ }
  }, 2000)
}
function _stopChartRefreshPolling() {
  if (_chartRefreshTimer) { clearInterval(_chartRefreshTimer); _chartRefreshTimer = null }
}

// DB polling for recovery after SSE disconnect.
// Backend continues generation (GeneratorExit handler saves to DB).
// Poll every 10s until paper has content or 15min timeout.
let _dbPollTimer = null
function _startDbPolling() {
  if (_dbPollTimer) return
  jobsStore.setConnectionLost(true)
  const startedAt = Date.now()
  _dbPollTimer = setInterval(async () => {
    // 15min safety timeout
    if (Date.now() - startedAt > 900000) {
      _stopDbPolling()
      connectionLost.value = false
      generating.value = false
      displayProgress.value = store.paper?.sections?.length > 0 ? 100 : 0
      stopProgressTicker()
      stopTimeTracker()
      jobsStore.clearStreamState()
      store.showToast('Generation timeout - cek tab Content untuk melihat apakah paper tersimpan.', 'warning')
      return
    }
    try {
      await store.loadPaperFromDb(store.currentPaperId)
      if (store.paper.sections?.length > 0 && store.paper.sections.some(s => s.content?.length > 0)) {
        // Paper completed!
        _stopDbPolling()
        connectionLost.value = false
        jobsStore.setConnectionLost(false)
        generating.value = false
        displayProgress.value = 100
        stopProgressTicker()
        stopTimeTracker()
        jobsStore.clearStreamState()
        // Append completion marker to streaming panels so user sees the result
        if (!contentText.value.includes('Paper selesai') && !contentText.value.includes('Paper generated')) {
          contentText.value += '\n✅ [Paper selesai digenerate di server — konten sudah dimuat ke editor]\n'
        }
        store.showToast('Paper selesai digenerate!', 'success')
        saveState()
      }
    } catch { /* DB load failed - keep polling */ }
  }, 10000)
}
function _stopDbPolling() {
  if (_dbPollTimer) { clearInterval(_dbPollTimer); _dbPollTimer = null }
  // Also stop the live status poller — every teardown path calls this, and
  // the two pollers never run simultaneously, so it's safe to colocate.
  _stopStatusPoll()
}
async function manualCheckDb() {
  try {
    await store.loadPaperFromDb(store.currentPaperId)
    if (store.paper.sections?.length > 0 && store.paper.sections.some(s => s.content?.length > 0)) {
      _stopDbPolling()
      connectionLost.value = false
      jobsStore.setConnectionLost(false)
      generating.value = false
      displayProgress.value = 100
      stopProgressTicker()
      stopTimeTracker()
      jobsStore.clearStreamState()
      // Append completion marker to streaming panels
      if (!contentText.value.includes('Paper selesai') && !contentText.value.includes('Paper generated')) {
        contentText.value += '\n✅ [Paper selesai digenerate di server — konten sudah dimuat ke editor]\n'
      }
      store.showToast('Paper selesai digenerate!', 'success')
      saveState()
    } else {
      store.showToast('Paper masih digenerate di server...', 'info')
    }
  } catch {
    store.showToast('Gagal memeriksa status.', 'error')
  }
}

async function finishGeneration(paperData?: any) {
  generating.value = false
  displayProgress.value = 100
  generatingTopic.value = ''
  connectionLost.value = false
  _startTime = null
  stopProgressTicker()
  stopTimeTracker()
  stopSSEPolling()
  _stopDbPolling()
  timeElapsed.value = ''
  jobsStore.clearStreamState()
  // Save completion state so panels persist across refresh
  saveState()
  // Apply paper data directly from SSE (preferred) or fetch from DB (fallback)
  if (paperData) {
    store.applyPaperData(paperData)
  } else if (store.currentPaperId) {
    await store.loadPaperFromDb(store.currentPaperId)
  }
  // Start polling for chart generation (runs in background after paper is shown)
  _startChartRefreshPolling()
}

function dismissGenerationPanel() {
  reasoningText.value = ''
  contentText.value = ''
  jobsStore.clearStreamState()
  clearState()
}

function cancelGeneration() {
  generating.value = false
  generatingTopic.value = ''
  connectionLost.value = false
  jobsStore.setConnectionLost(false)
  _startTime = null
  stopProgressTicker()
  stopTimeTracker()
  stopSSEPolling()
  _stopDbPolling()
  jobsStore.clearStreamState()
  timeElapsed.value = ''
  contentText.value += '\n[Dibatalkan oleh pengguna]\n'
  clearState()
  _cancelTimer = setTimeout(() => { reasoningText.value = ''; contentText.value = '' }, 3000)
}

// Watch for paper change to reload status AND reset local state
watch(() => store.currentPaperId, (newId, oldId) => {
  // Reset all in-memory display refs when switching to a different paper so
  // the previous paper's reasoning/content never lingers on screen.
  if (newId !== oldId) {
    reasoningText.value = ''
    contentText.value = ''
    generating.value = false
    generatingTopic.value = ''
    displayProgress.value = 0
    imageGenProgress.value = { total: 0, done: 0, message: '' }
    _startTime = null
    _resetLiveState()
    jobsStore.clearStreamState()
    // NOTE: do NOT clearState() here — currentPaperId is already newId, so it
    // would wipe the NEW paper's saved slot. Instead restore the new paper's
    // own per-paper sessionStorage state (resumes its in-progress generation
    // if any; stays blank otherwise). Keys are scoped via _sessionKey().
    restoreState()
  }
  if (newId) {
    loadDrafts(newId)
    loadPaperFilesList()
    loadLiterature()
    checkActiveJob()
  }
})

// Auto-scroll reasoning to bottom when new lines arrive
watch([reasoningText, contentText], () => {
  nextTick(() => {
    if (reasoningScroll.value) {
      reasoningScroll.value.scrollTop = reasoningScroll.value.scrollHeight
    }
    if (contentScrollRef.value) {
      contentScrollRef.value.scrollTop = contentScrollRef.value.scrollHeight
    }
  })
})

async function stopGeneration() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null }
  const jobId = activeJob.value?.id || activeJob.value?.job_id
  if (jobId) {
    // RQ job — cancel via API
    try {
      await api.post(`/api/jobs/${jobId}/cancel`)
      cancelGeneration()
      activeJob.value = null
    } catch (err) {
      console.warn('Failed to cancel job:', err)
    }
  } else if (_sseCtrl) {
    // Direct SSE stream — abort the fetch controller
    _sseCtrl.abort()
    _sseCtrl = null
    cancelGeneration()
  }
}

async function regenerateSelectedImages() {
  if (!store.currentPaperId) return

  generating.value = true
  generatingTopic.value = 'Re-generate images'
  displayProgress.value = 0
  imageGenProgress.value = { total: 0, done: 0, message: 'Menyiapkan re-generate images...' }
  startTimeTracker()

  try {
    const res = await api.post('/api/image-jobs/regenerate', { paper_id: store.currentPaperId })
    const jobs = res.data?.jobs || []
    if (!jobs.length) throw new Error('Tidak ada image untuk di-re-generate')

    imageGenProgress.value = { total: jobs.length, done: 0, message: `Re-generating ${jobs.length} images...` }

    const pending = new Set(jobs.map(j => j.id))
    while (pending.size > 0) {
      await new Promise(resolve => setTimeout(resolve, 2500))
      const results = await Promise.all([...pending].map(id => api.get(`/api/image-jobs/${id}`).then(r => r.data).catch(() => null)))
      for (const job of results) {
        if (job && ['done', 'error', 'cancelled'].includes(job.status)) pending.delete(job.id)
      }
      const done = jobs.length - pending.size
      imageGenProgress.value = { total: jobs.length, done, message: `Re-generate images ${done}/${jobs.length}` }
      displayProgress.value = Math.floor((done / jobs.length) * 100)
    }

    await store.loadPaperFromDb(store.currentPaperId)
    await store.loadPaperImages?.(store.currentPaperId)
    store.showToast('Re-generate images selesai.', 'success')
  } catch (e: any) {
    store.showToast('Re-generate images gagal: ' + (e.response?.data?.error || e.message || e), 'error')
  } finally {
    generating.value = false
    generatingTopic.value = ''
    displayProgress.value = 100
    stopTimeTracker()
    saveState()
  }
}

async function generate() {
  // Prevent double-generate on the same paper
  if (generating.value) {
    store.showToast('Sedang generating, tunggu sampai selesai.', 'warning')
    return
  }
  if (!store.currentPaperId) {
    store.showToast('Simpan paper dulu sebelum generate.', 'error')
    return
  }
  const t = topic.value.trim()

  // ── Re-generate Images branch ───────────────────────────────────────
  if (enableRegenerateImages.value) {
    await regenerateSelectedImages()
    return
  }

  // ── Normal Generate Full ────────────────────────────────────────────
  if (!t) return

  // ── Confirm overwrite if paper already has content ──────────────────
  // content is an array of blocks: check for non-empty text, not just array length.
  // Skip image/table placeholder blocks (id='gambar'/'tabel').
  const hasContent = store.paper?.sections?.some((s: any) =>
    (s.content || []).some((block: any) =>
      block.id === 'text' && typeof block.text === 'string' && block.text.trim().length > 0
    )
  ) || (store.paper?.abstract && store.paper.abstract.trim().length > 20)
  if (hasContent && !confirm('Paper sudah memiliki konten. Generate Full akan menimpa seluruh isi paper.\n\nLanjutkan?')) {
    return
  }
  
  generating.value = true
  generatingTopic.value = t
  displayProgress.value = 0
  reasoningText.value = ''
  contentText.value = ''
  imageGenProgress.value = { total: 0, done: 0, message: '' }
  _startTime = Date.now()
  _resetLiveState()  // Reset incremental section parser
  startProgressTicker()
  startTimeTracker()
  saveState()
  // Sync to Pinia store for bell + cross-panel persistence
  jobsStore.setStreamState({
    paperId: store.currentPaperId,
    generating: true,
    generatingTopic: t,
    displayProgress: 0,
    reasoningText: '',
    contentText: '',
    startedAt: _startTime,
    prompt: t,
  })
  
  try {
    // Build request body
    let requestBody
    let contentType = 'application/json'
    
    // Files that still hold a live File object (restored stale entries have file:null)
    const liveDataFiles = dataFiles.value.filter(f => f.file)
    const liveRefFiles = referenceFiles.value.filter(f => f.file)
    // Pre-extracted text entries (existing files from paper + drafts)
    const preExtractedData = dataFiles.value.filter(f => !f.file && f.extracted && f.text)
    const preExtractedRef = referenceFiles.value.filter(f => !f.file && f.extracted && f.text && !f.isDraft)
    const draftEntries = referenceFiles.value.filter(f => f.isDraft && f.text)
    const hasFiles = liveDataFiles.length > 0 || liveRefFiles.length > 0

    if (hasFiles) {
      // Use FormData for file attachments
      const formData = new FormData()
      formData.append('prompt', t)
      formData.append('paper_id', store.currentPaperId)
      formData.append('language', store.paper?.language || auth.user?.preferred_language || 'id')
      if (store.paper?.citation_style) {
        formData.append('style', store.paper.citation_style)
      }
      // Generation options from checkboxes
      formData.append('generate_images', String(enableImageGen.value))
      formData.append('revisi_semua', String(enableRevisiSemua.value))
      if (enablePaperReview.value) formData.append('paper_kind', 'review')
      
      // Selected chat drafts (now from referenceFiles, not separate checkbox)
      if (draftEntries.length > 0) {
        const draftTexts = draftEntries.map(f => `## Draft: ${f.draftName}\n${f.text}`).join('\n\n')
        formData.append('selected_drafts', draftTexts)
      }
      
      // Attach files — DUA bucket terpisah: backend membaca 'data_files' &
      // 'reference_files' dan menyuntikkannya ke prompt dengan header berbeda.
      for (const af of liveDataFiles) {
        formData.append('data_files', af.file)
        af.extracted = true
      }
      for (const af of liveRefFiles) {
        formData.append('reference_files', af.file)
        af.extracted = true
      }
      // Pre-extracted text entries (existing files, drafts, data analysis) —
      // send as JSON strings so backend can include them without file upload.
      if (preExtractedData.length > 0) {
        formData.append('data_texts', JSON.stringify(preExtractedData.map(f => f.text)))
      }
      if (preExtractedRef.length > 0) {
        formData.append('reference_texts', JSON.stringify(preExtractedRef.map(f => f.text)))
      }
      requestBody = formData
      contentType = null // Let browser set multipart boundary
    } else {
      // Standard JSON request
      const payload = {
        prompt: t,
        paper_id: store.currentPaperId,
        include_status: true,
        language: store.paper?.language || auth.user?.preferred_language || 'id',
        style: store.paper?.citation_style || null,
        generate_images: enableImageGen.value,
        revisi_semua: enableRevisiSemua.value,
        ...(enablePaperReview.value ? { paper_kind: 'review' } : {}),
      }
      
      // Selected chat drafts (now from referenceFiles, not separate checkbox)
      if (draftEntries.length > 0) {
        const draftTexts = draftEntries.map(f => `## Draft: ${f.draftName}\n${f.text}`).join('\n\n')
        payload.selected_drafts = draftTexts
      }
      // Pre-extracted text entries (existing files, data analysis)
      if (preExtractedData.length > 0) {
        payload.data_texts = preExtractedData.map(f => f.text)
      }
      if (preExtractedRef.length > 0) {
        payload.reference_texts = preExtractedRef.map(f => f.text)
      }
      requestBody = JSON.stringify(payload)
    }
    
    // Use native fetch for true SSE streaming (axios buffers the response)
    const headers = {}
    if (contentType) headers['Content-Type'] = contentType
    
    // Add CSRF token (required by JWT cookie auth)
    const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/)
    if (csrfMatch) headers['X-CSRF-TOKEN'] = decodeURIComponent(csrfMatch[1])
    
    const streamCtrl = new AbortController()
    _sseCtrl = streamCtrl  // allow cancel to abort this stream
    const res = await fetch(`/api/papers/${store.currentPaperId}/generate-stream`, {
      method: 'POST',
      headers,
      body: requestBody,
      credentials: 'include',
      signal: streamCtrl.signal,
    })
    
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      throw new Error(errData.error || `HTTP ${res.status}`)
    }
    
    if (!res.body) {
      throw new Error('Response body is null')
    }
    
    // Stream SSE events in real-time
    await consumeSSEStream(res)
    
  } catch (err) {
    // Don't show abort errors to user (intentional cancel or stream close)
    if (err.name === 'AbortError' || err.message?.includes('aborted') || err.message?.includes('BodyStreamBuffer')) return

    // Network error - backend may still be running. Don't kill generating state.
    // Show connectionLost indicator and start DB polling for recovery.
    connectionLost.value = true
    store.showToast('Koneksi terputus. Paper masih digenerate di server - memantau status...', 'warning')
    _startDbPolling()
  } finally {
    checkActiveJob()
  }
}

// ── Incremental section parser ────────────────────────────────────────
// Tracks which sections have been pushed to editor so we only push new ones.
const _liveState = {
  pushedSections: new Set<string>(),  // section keys already applied to editor
  braceDepth: 0,                       // current brace depth in top-level object
  inString: false,                     // inside a JSON string
  escape: false,                       // previous char was backslash
  topLevelKeys: [] as string[],        // ordered list of top-level keys found
  currentKey: '',                      // key currently being parsed
  keyBuffer: '',                       // buffer for key name
  lastPushedAt: 0,                     // timestamp of last push (throttle)
  accumulatedPaper: null as Record<string, any> | null,  // accumulated paper for live editor
}

function _resetLiveState() {
  _liveState.pushedSections.clear()
  _liveState.braceDepth = 0
  _liveState.inString = false
  _liveState.escape = false
  _liveState.topLevelKeys = []
  _liveState.currentKey = ''
  _liveState.keyBuffer = ''
  _liveState.lastPushedAt = 0
  _liveState.accumulatedPaper = null
}

// Scan content tokens to find complete top-level JSON sections.
// When section N+1 starts, section N is complete → push section N to editor.
function tryLiveUpdateEditor() {
  const text = contentText.value
  if (!text || text.length < 20) return
  
  // Throttle: at most once per 800ms to avoid editor flicker
  const now = Date.now()
  if (now - _liveState.lastPushedAt < 800) return
  
  // Strip markdown code fences
  const jsonStr = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '')
  if (!jsonStr.startsWith('{')) return
  
  // Find all complete top-level key:value pairs by scanning brace depth
  const sections = _extractCompleteSections(jsonStr)
  
  if (sections.length === 0) return
  
  // Build a partial paper object from complete sections only
  const partial: Record<string, any> = {}
  let hasNew = false
  
  for (const { key, value } of sections) {
    if (_liveState.pushedSections.has(key)) continue
    _liveState.pushedSections.add(key)
    partial[key] = value
    hasNew = true
  }
  
  if (!hasNew) return
  _liveState.lastPushedAt = now
  
  // Accumulate sections so applyPaperData gets all previously pushed sections too
  if (!_liveState.accumulatedPaper) _liveState.accumulatedPaper = {}
  Object.assign(_liveState.accumulatedPaper, partial)
  
  // Apply to editor — use applyPaperData which handles full paper shape
  try {
    store.applyPaperData({ ..._liveState.accumulatedPaper })
  } catch {
    // Partial may be incomplete for editor — ignore
  }
}

// Walk JSON string tracking brace depth to find complete top-level values.
// Returns array of { key, value } for sections whose value is fully closed.
function _extractCompleteSections(json: string): Array<{ key: string, value: any }> {
  const results: Array<{ key: string, value: any }> = []
  let depth = 0
  let inStr = false
  let esc = false
  let i = 0
  
  // Skip opening {
  while (i < json.length && json[i] !== '{') i++
  if (i >= json.length) return results
  i++ // skip {
  depth = 1
  
  let state: 'ws' | 'key' | 'colon' | 'value' = 'ws'
  let currentKey = ''
  let valueStart = -1
  
  while (i < json.length) {
    const ch = json[i]
    
    if (esc) {
      esc = false
      // Handle \uXXXX: skip the 'u' and 4 hex digits
      if (ch === 'u') {
        i += 5 // skip u + 4 hex chars
        continue
      }
      i++
      continue
    }
    
    if (ch === '\\' && inStr) {
      esc = true
      i++
      continue
    }
    
    if (ch === '"' && !esc) {
      inStr = !inStr
      if (state === 'ws' && inStr) {
        state = 'key'
        currentKey = ''
      } else if (state === 'key' && !inStr) {
        // Key complete, look for colon
        state = 'colon'
      }
      i++
      continue
    }
    
    if (inStr) {
      if (state === 'key') currentKey += ch
      i++
      continue
    }
    
    // Outside string
    if (state === 'colon') {
      if (ch === ':') {
        state = 'value'
        // Find where the value starts (skip whitespace)
        let j = i + 1
        while (j < json.length && /\s/.test(json[j])) j++
        valueStart = j
        i = j
        continue
      }
      i++
      continue
    }
    
    if (state === 'value') {
      const vc = json[valueStart]
      
      // String value — find closing quote
      if (vc === '"') {
        if (ch === '"') {
          // Value complete
          try {
            const raw = json.slice(valueStart, i + 1)
            results.push({ key: currentKey, value: JSON.parse(raw) })
          } catch { /* skip unparseable */ }
          state = 'ws'
        } else if (ch === '\\') {
          esc = true
        }
        i++
        continue
      }
      
      // Number, boolean, null — ends at , or } or whitespace
      if (vc !== '{' && vc !== '[') {
        if (ch === ',' || ch === '}' || ch === '\n') {
          const raw = json.slice(valueStart, i).trim()
          if (raw) {
            try { results.push({ key: currentKey, value: JSON.parse(raw) }) } catch {}
          }
          state = ch === '}' ? 'done' : 'ws'
          if (ch === '}') break
        }
        i++
        continue
      }
      
      // Object or array — track depth
      if (ch === '{' || ch === '[') depth++
      if (ch === '}' || ch === ']') {
        depth--
        if (depth <= 1) {
          // Top-level value complete
          try {
            const raw = json.slice(valueStart, i + 1)
            results.push({ key: currentKey, value: JSON.parse(raw) })
          } catch { /* incomplete — skip */ }
          state = 'ws'
        }
      }
      i++
      continue
    }
    
    // state === 'ws' — between key:value pairs
    if (ch === ',') { i++; continue }
    if (ch === '}') break // end of top-level object
    if (ch === '"') {
      state = 'key'
      currentKey = ''
      // Don't increment i — let the quote handler above process it
      continue
    }
    i++
  }
  
  return results
}

// Consume SSE stream from fetch response — real-time token display
async function consumeSSEStream(res) {
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = null
  let doneReceived = false
  
  try {
  while (true) {
    let chunk
    try {
      chunk = await reader.read()
    } catch (readErr) {
      // Stream aborted (user cancel or network) — exit gracefully
      if (readErr.name === 'AbortError' || readErr.message?.includes?.('aborted') || _sseCtrl?.signal.aborted) return
      throw readErr
    }
    const { done, value } = chunk
    if (done) break
    
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() // Keep incomplete line in buffer
    
    for (const line of lines) {
      if (line.startsWith(':')) {
        // SSE comment (heartbeat) - ignore
        continue
      } else if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        try {
          const payload = JSON.parse(line.slice(6))
          
          if (currentEvent === 'thinking') {
            // Filter out internal system markers (e.g. "[Starting generation with MODEL...]")
            const tok = payload.token ?? ''
            if (payload.stage === 'start' && tok.startsWith('[')) {
              // skip system marker — don't show to user
            } else {
              reasoningText.value += tok
            }
            // Sync to store every ~2 seconds via timer (reliable, not lossy)
            _syncStreamIfNeeded()
            // Auto-scroll
            nextTick(() => {
              const panel = document.querySelector('.reasoning-panel')
              if (panel) panel.scrollTop = panel.scrollHeight
            })
          } else if (currentEvent === 'content') {
            contentText.value += payload.token ?? ''
            if (payload.total_tokens && (payload.total_tokens / 10) > displayProgress.value) displayProgress.value = Math.min(95, Math.floor(payload.total_tokens / 10))
            jobsStore.updateStreamProgress(displayProgress.value)
            // Sync to store every ~2 seconds via timer (reliable, not lossy)
            _syncStreamIfNeeded()
            // Try to detect completed sections and push to editor
            tryLiveUpdateEditor()
          } else if (currentEvent === 'progress') {
            // Image/chart generation progress (backend waits for images before done)
            if (payload.stage === 'image_generation') {
              // Image generation has its own progress bar. The main 0–100 bar is only for paper text generation.
              // ponytail: keep one SSE stream; split into two UI progress models.
              // Update separate image progress panel instead of appending to content
              imageGenProgress.value = {
                total: payload.total || 0,
                done: payload.done || 0,
                message: payload.message || '',
              }
            }
          } else if (currentEvent === 'done') {
            doneReceived = true
            contentText.value += `\n[Paper generated in ${payload.elapsed || '?'}s — ${payload.tokens || '?'} tokens]\n`
            // Backend now sends done BEFORE images, so JSON is parsed to editor first
            const imgJobCount = payload.image_jobs ? payload.image_jobs.length : 0
            const totalImgJobs = payload.total_jobs || imgJobCount
            if (totalImgJobs > 0) {
              contentText.value += `\n✅ Paper content loaded! ${totalImgJobs} image(s) generating in background...\n`
              // Show initial progress immediately — progress events update incrementally
              imageGenProgress.value = {
                total: totalImgJobs,
                done: 0,
                message: `Generating ${totalImgJobs} images...`,
              }
            }
            // Pass paper_data from backend directly to editor (faster than fetching from DB)
            // ponytail: DON'T call finishGeneration() here — it kills _sseCtrl which
            // aborts the reader loop, so we never receive progress/images_complete.
            // Do the finish logic inline but keep the stream alive for image events.
            generating.value = false
            displayProgress.value = 100
            generatingTopic.value = ''
            connectionLost.value = false
            _startTime = null
            stopProgressTicker()
            stopTimeTracker()
            _stopDbPolling()
            timeElapsed.value = ''
            jobsStore.clearStreamState()
            saveState()
            if (payload.paper) {
              store.applyPaperData(payload.paper)
            } else if (store.currentPaperId) {
              await store.loadPaperFromDb(store.currentPaperId)
            }
            // Hint about placeholder values
            store.showToast('💡 Paper berhasil di-generate! Periksa dan ganti nilai placeholder (x1, x2, x3, dst.) dengan data asli Anda.', 'info', 8000)
            _startChartRefreshPolling()
            // If no images pending, stop SSE and return
            if (!totalImgJobs) {
              imageGenProgress.value = { total: 0, done: 0, message: '' }
              stopSSEPolling()
              return
            }
            // Don't return — continue listening for progress/images_complete events
          } else if (currentEvent === 'images_complete') {
            // All images done — reload paper (image paths reconciled) + refresh charts
            const errCount = payload.errors || 0
            const totalCount = payload.total || 0
            if (errCount > 0) {
              imageGenProgress.value = { total: totalCount, done: totalCount, message: `${totalCount - errCount}/${totalCount} images — ${errCount} failed!` }
              contentText.value += `\n⚠️ ${totalCount - errCount}/${totalCount} images generated — ${errCount} errors\\n`
            } else {
              imageGenProgress.value = { total: totalCount, done: totalCount, message: 'All images complete!' }
              contentText.value += `\n✅ All images generated and embedded!\n`
            }
            await store.loadPaperFromDb(store.currentPaperId)
            await store.loadPaperCharts(store.currentPaperId)
            stopSSEPolling()
            return
          } else if (currentEvent === 'error') {
            doneReceived = true
            contentText.value += `\n[ERROR] ${payload.error}\n`
            store.showToast('Generation error: ' + payload.error, 'error')
            // Clean up generating state — don't leave UI stuck spinning
            generating.value = false
            stopProgressTicker()
            stopTimeTracker()
            jobsStore.clearStreamState()
            saveState()
            return
          }
        } catch {
          // Skip malformed JSON lines
        }
      }
      // Don't reset currentEvent — it persists until next event line
    }
  }
  } finally {
    // Always release reader lock — prevents "BodyStreamBuffer was aborted" error
    try { reader.releaseLock() } catch { /* stream already closed/errored */ }
  }
  
  // Stream ended - only finish if we got a proper done event
  if (doneReceived) return

  // Stream interrupted without done event - backend may still be running.
  // Don't finish or cancel. Set connectionLost and start DB polling.
  connectionLost.value = true
  _startDbPolling()
}
</script>

<style scoped>
@keyframes gen-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes gen-dots-blink {
  0%, 20% { opacity: 0; }
  40% { opacity: 1; }
  60%, 100% { opacity: 0; }
}

.generating-text {
  animation: gen-pulse 1.5s ease-in-out infinite;
}

.generating-btn-text {
  animation: gen-pulse 1.5s ease-in-out infinite;
}

.gen-dots {
  display: inline-flex;
  gap: 0;
}

.gen-dots span {
  font-weight: bold;
  animation: gen-dots-blink 1.4s ease-in-out infinite;
}

.gen-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.gen-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

/* Reasoning panel */
.reasoning-content > div {
  border-bottom: 1px solid rgba(0,0,0,0.04);
  padding: 3px 4px;
}
.dark .reasoning-content > div {
  border-bottom-color: rgba(255,255,255,0.04);
}
.reasoning-content > div:last-child {
  border-bottom: none;
}

/* Thinking dots animation */
.thinking-dots {
  display: flex;
  gap: 3px;
  align-items: center;
}
.thinking-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d97706; /* amber-600 */
  animation: thinking-bounce 1.2s ease-in-out infinite;
}
.dark .thinking-dots span {
  background: #fbbf24; /* amber-400 */
}
.thinking-dots span:nth-child(2) {
  animation-delay: 0.15s;
}
.thinking-dots span:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes thinking-bounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

/* KaTeX block math */
.content-render .katex-block {
  margin: 8px 0;
  overflow-x: auto;
  text-align: center;
}
.content-render .katex {
  font-size: 1em;
}
.content-render .katex-error {
  color: #dc2626;
  font-family: monospace;
  font-size: 0.85em;
}
.dark .content-render .katex-error { color: #f87171; }
.content-render .katex-fallback {
  color: #6b7280;
  font-family: monospace;
  font-style: italic;
}
.dark .content-render .katex-fallback { color: var(--text-muted); }

/* Progress bar glow animation */
@keyframes progress-glow-pulse {
  0%, 100% { opacity: 0.7; }
  50% { opacity: 1; }
}
.progress-glow {
  animation: progress-glow-pulse 2s ease-in-out infinite;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);
}

/* Reasoning panel subtle styling */
.reasoning-panel {
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;
}
.reasoning-panel::-webkit-scrollbar {
  width: 6px;
}
.reasoning-panel::-webkit-scrollbar-track {
  background: transparent;
}
.reasoning-panel::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 3px;
}
.dark .reasoning-panel { scrollbar-color: #2a4a72 transparent; }
.dark .reasoning-panel::-webkit-scrollbar-thumb { background-color: #2a4a72; }
</style>
