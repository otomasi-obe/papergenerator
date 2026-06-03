<template>
  <div class="h-screen flex flex-col bg-cream-50 dark:bg-ash-850 transition-colors">
    <AppHeader />

    <!-- Toolbar (natural height; never overlaps the header or content) -->
    <div class="bg-cream-50/95 dark:bg-ash-800/95 backdrop-blur border-b border-cream-300 dark:border-ash-700 z-30 shrink-0 shadow-[0_1px_0_rgba(15,14,11,0.05)]">
      <div class="px-4 lg:px-8 py-2">
        <div class="flex flex-wrap items-center gap-x-2 gap-y-1.5 min-w-0">
          <!-- Group A: navigation + title + save status (fills line 1 when wrapped) -->
          <div class="flex items-center gap-2 min-w-0 flex-[1_1_20rem]">
          <button
            type="button"
            @click="handlePapersBack"
            class="flex items-center gap-1 text-sm text-ink-700 dark:text-ink-200 hover:text-ink-900 dark:hover:text-ink-50 px-2 py-1.5 rounded hover:bg-cream-200 dark:hover:bg-ash-700 shrink-0 transition-colors active:scale-95 transition-transform"
          >
            ← Papers
          </button>
          <span class="text-cream-400 dark:text-ash-600 shrink-0">|</span>
          <input
            v-model="store.paper.title"
            placeholder="Untitled Paper"
            class="text-sm text-ink-900 dark:text-ink-50 font-medium bg-transparent border border-transparent hover:border-cream-400 dark:hover:border-ash-600 focus:border-navy-500 dark:focus:border-cream-400 focus:bg-cream-50 dark:focus:bg-ash-800 focus:outline-none focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 rounded px-2 py-1 truncate min-w-[8rem] w-0 flex-[1_1_12rem] max-w-none transition-colors"
            title="Klik untuk mengubah judul paper"
            aria-label="Paper title"
          />
          <span v-if="store.loading" class="text-[11px] text-ink-600 dark:text-anthracite-200 animate-pulse shrink-0">Saving…</span>
          <button v-else-if="saveStatus === 'saving'" class="text-[11px] text-ink-600 dark:text-anthracite-200 animate-pulse shrink-0 active:scale-95 transition-transform" type="button">Saving…</button>
          <button v-else-if="saveStatus === 'saved'" class="text-[11px] text-ink-700 dark:text-ink-200 shrink-0 active:scale-95 transition-transform" type="button">Saved · {{ savedRelative }}</button>
          <button v-else-if="saveStatus === 'error'" @click="retrySave" class="text-[11px] text-red-600 dark:text-red-300 hover:underline shrink-0 active:scale-95 transition-transform" type="button">Save failed</button>
          </div>

          <!-- Group B: actions + tabs + AI chat. Wraps to its own line when it no longer fits beside the title group -->
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1.5 min-w-0 flex-[0_1_auto]">
            <div class="flex items-center gap-1 shrink-0">
              <button @click="store.exportDocx()" :disabled="store.loading"
                class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600 disabled:opacity-50 shrink-0 active:scale-95 transition-transform"
                title="Export DOCX">
                📄 DOCX
              </button>
              <button @click="store.undo()" :disabled="!store.canUndo"
                class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600 disabled:opacity-30 shrink-0 active:scale-95 transition-transform"
                title="Undo (Ctrl/Cmd+Z)">
                ↶ Undo
              </button>
              <button @click="store.redo()" :disabled="!store.canRedo"
                class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600 disabled:opacity-30 shrink-0 active:scale-95 transition-transform"
                title="Redo (Ctrl/Cmd+Shift+Z)">
                ↷ Redo
              </button>
              <span v-if="store.pendingCount > 0"
                class="text-[11px] px-2 py-0.5 rounded-full bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-200 border border-cream-300 dark:border-ash-600 shrink-0">
                {{ store.pendingCount }} pending
              </span>
            </div>

            <!-- Editor / Preview / Tools — three buttons -->
            <div class="flex items-center gap-1 shrink-0">
              <button @click="activeTab = 'editor'"
                :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap active:scale-95 transition-transform',
                  activeTab === 'editor'
                    ? 'bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-ink-50'
                    : 'text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600']">
                📝 Editor
              </button>
              <button @click="activeTab = 'preview'"
                :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap active:scale-95 transition-transform',
                  activeTab === 'preview'
                    ? 'bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-ink-50'
                    : 'text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600']">
                👁 Preview
              </button>
              <button @click="toggleTools"
                :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1 shrink-0 whitespace-nowrap active:scale-95 transition-transform',
                  toolsOpen || rightPanel
                    ? 'bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-ink-50'
                    : 'text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600']">
                🛠 Tools
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Generation status banner (non-blocking) -->
    <div v-if="store.aiLoading"
         class="bg-cream-100 dark:bg-ash-700 border-b border-cream-300 dark:border-ash-600 px-4 lg:px-8 py-2.5 flex items-center gap-3 text-ink-700 dark:text-ink-200 text-sm shrink-0">
      <div class="relative w-6 h-6 shrink-0">
        <div class="absolute inset-0 rounded-full border-2 border-cream-300 dark:border-ash-500"></div>
        <div class="absolute inset-0 rounded-full border-2 border-t-ink-700 dark:border-t-ink-200 animate-spin"></div>
      </div>
      <div class="flex-1 min-w-0 leading-snug">
        <span class="font-medium">{{ store.aiLoadingMessage || 'AI sedang generate paper...' }}</span>
        <span class="opacity-70 ml-2">· Elapsed: {{ aiElapsedLabel }}</span>
        <span v-if="aiElapsedSeconds > 600" class="ml-2 opacity-80">(masih bekerja — paper besar bisa sampai 15 menit)</span>
      </div>
      <button v-if="canCancelAi" @click="chatStore.stopStreaming()"
              class="shrink-0 px-2.5 py-1 rounded text-xs font-medium border border-cream-400 dark:border-ash-500 hover:bg-cream-200 dark:hover:bg-ash-600 active:scale-95 transition-transform">Cancel</button>
    </div>

    <!-- Split layout: LEFT tools sidebar + RIGHT chat panel.
         Tools sidebar is always visible; chat is always on the right. -->
    <div ref="splitRoot" class="flex flex-1 min-h-0 overflow-hidden relative">
      <!-- LEFT pane: editor / preview. -->
      <div class="overflow-y-auto border-r border-cream-300 dark:border-ash-700 bg-cream-50/50 dark:bg-ash-850/50" :class="rightPanel || toolsOpen ? 'w-1/2' : 'w-full'">
        <div class="px-4 lg:px-8 py-6">

          <!-- TAB: EDITOR -->
          <div v-show="activeTab === 'editor'" role="tabpanel" id="panel-editor" aria-labelledby="tab-editor" class="space-y-4">
        <!-- Title -->
        <div class="card border-l-4 border-l-navy-500">
          <label class="label">Title</label>
          <input v-model="store.paper.title" class="input" placeholder="Paper title..." />
        </div>

        <!-- Authors -->
        <div class="card border-l-4 border-l-navy-500">
          <div class="flex items-center justify-between mb-3">
            <label class="label !mb-0">Authors</label>
            <button @click="store.addAuthor()" class="btn-add">+ Author</button>
          </div>
          <draggable :list="store.paper.authors" :item-key="stableKey" animation="150" handle=".author-drag" class="space-y-2"
                     :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
            <template #item="{ element: author, index: i }">
              <div class="group bg-ivory-100 dark:bg-anthracite-800 border border-ivory-300 dark:border-anthracite-500 rounded-lg p-3 flex gap-2 items-start">
                <span role="button" aria-label="Drag to reorder" class="author-drag cursor-grab active:cursor-grabbing text-ivory-500 dark:text-anthracite-200 hover:text-ink-700 dark:hover:text-anthracite-50 select-none text-xl leading-tight pt-1">⠿</span>
                <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                  <button @click="moveItem(store.paper.authors, i, i - 1)" :disabled="i === 0" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move up">↑</button>
                  <button @click="moveItem(store.paper.authors, i, i + 1)" :disabled="i === store.paper.authors.length - 1" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move down">↓</button>
                </div>
                <div class="flex-1">
                  <div class="flex justify-between mb-2">
                    <span class="text-xs text-ink-700 dark:text-anthracite-100 font-medium">Author {{ i + 1 }}</span>
                    <button v-if="store.paper.authors.length > 1" @click="store.removeAuthor(i)"
                      class="text-xs text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300">✕</button>
                  </div>
                  <div class="grid grid-cols-2 gap-2">
                    <input v-model="author.name" class="input-sm" placeholder="Name" />
                    <input v-model="author.email" class="input-sm" placeholder="Email" />
                    <input v-model="author.affiliation" class="input-sm col-span-2" placeholder="Affiliation" />
                    <input v-model="author.location" class="input-sm col-span-2" placeholder="Location" />
                  </div>
                </div>
              </div>
            </template>
          </draggable>
        </div>

        <!-- Abstract -->
        <div class="card border-l-4 border-l-navy-500">
          <label class="label">Abstract</label>
          <textarea v-model="store.paper.abstract" rows="2" @input="autoResize"
            ref="abstractRef"
            class="input resize-none overflow-hidden min-h-[4.5rem]" placeholder="Paper abstract..."></textarea>
        </div>

        <!-- Keywords -->
        <div class="card border-l-4 border-l-cream-500">
          <label class="label">Keywords</label>
          <div class="flex flex-wrap gap-1.5 mb-2">
            <span v-for="(_kw, i) in store.paper.keywords" :key="i"
              class="bg-cream-200 dark:bg-ash-700 text-navy-800 dark:text-ash-100 px-2 py-0.5 rounded text-sm flex items-center gap-1">
              {{ _kw }}
              <button @click="store.removeKeyword(i)" class="text-navy-400 dark:text-ash-300 hover:text-navy-700 dark:hover:text-ash-100 text-xs">✕</button>
            </span>
          </div>
          <div class="flex gap-2">
            <input v-model="newKeyword" class="input-sm flex-1" placeholder="Add keyword..." @keyup.enter="addKw" />
            <button @click="addKw" class="btn-add">Add</button>
          </div>
        </div>

        <!-- Sections -->
        <draggable :list="store.paper.sections" :item-key="stableKey" animation="150" handle=".section-drag" class="space-y-4"
                   :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
          <template #item="{ element: section, index: sIdx }">
            <div class="group card border-l-4 border-l-cream-600">
              <div class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2 flex-1 min-w-0">
                  <span role="button" aria-label="Drag to reorder" class="section-drag cursor-grab active:cursor-grabbing text-cream-400 dark:text-ash-400 hover:text-navy-500 dark:hover:text-cream-300 select-none text-xl leading-tight shrink-0">⠿</span>
                  <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                    <button @click="moveItem(store.paper.sections, sIdx, sIdx - 1)" :disabled="sIdx === 0" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move up">↑</button>
                    <button @click="moveItem(store.paper.sections, sIdx, sIdx + 1)" :disabled="sIdx === store.paper.sections.length - 1" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move down">↓</button>
                  </div>
                  <span class="text-[10px] text-ink-500 dark:text-ink-300 font-medium uppercase tracking-wide bg-transparent border-l-2 border-ivory-300 pl-2 shrink-0">
                    Section {{ toRoman(sIdx + 1) }}
                  </span>
                  <input v-model="section.title" class="input-sm flex-1 text-base font-semibold min-w-0"
                    placeholder="Section Title (e.g. INTRODUCTION)" />
                </div>
                <button @click="confirmDeleteSection(sIdx)"
                  class="text-xs text-red-400 hover:text-red-600 px-2 py-1 ml-2 shrink-0">✕</button>
              </div>

              <ContentList :items="section.content" :store="store" />
              <div class="flex gap-2 mt-3 flex-wrap">
                <button @click="store.addContent(section.content, 'text')" class="btn-content">+ Text</button>
                <button @click="store.addContent(section.content, 'gambar')" class="btn-content">+ Image</button>
                <button @click="store.addContent(section.content, 'tabel')" class="btn-content">+ Table</button>
                <button @click="store.addContent(section.content, 'rumus')" class="btn-content">+ Formula</button>
              </div>

              <draggable :list="section.subsections" :item-key="stableKey" animation="150" handle=".sub-drag" class="space-y-3 mt-4"
                         :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
                <template #item="{ element: sub, index: subIdx }">
                  <div class="group ml-4 border-l-2 border-cream-300 pl-4">
                    <div class="flex items-center justify-between mb-2">
                      <div class="flex items-center gap-2 flex-1 min-w-0">
                        <span role="button" aria-label="Drag to reorder" class="sub-drag cursor-grab active:cursor-grabbing text-cream-400 dark:text-ash-400 hover:text-navy-500 dark:hover:text-cream-300 select-none shrink-0">⠿</span>
                        <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                          <button @click="moveItem(section.subsections, subIdx, subIdx - 1)" :disabled="subIdx === 0" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move up">↑</button>
                          <button @click="moveItem(section.subsections, subIdx, subIdx + 1)" :disabled="subIdx === section.subsections.length - 1" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move down">↓</button>
                        </div>
                        <span class="text-[10px] text-ink-500 dark:text-ink-300 font-medium uppercase tracking-wide bg-transparent border-l-2 border-ivory-300 pl-2 shrink-0">
                          {{ String.fromCharCode(65 + subIdx) }}
                        </span>
                        <input v-model="sub.title" class="input-sm flex-1 text-base font-semibold min-w-0"
                          placeholder="Subsection Title" />
                      </div>
                      <button @click="confirmDeleteSubsection(sIdx, subIdx)"
                        class="text-xs text-red-400 hover:text-red-600 px-2 py-1 ml-2 shrink-0">✕</button>
                    </div>
                    <ContentList :items="sub.content" :store="store" />
                    <div class="flex gap-2 mt-2 flex-wrap">
                      <button @click="store.addContent(sub.content, 'text')" class="btn-content text-xs">+ Text</button>
                      <button @click="store.addContent(sub.content, 'gambar')" class="btn-content text-xs">+ Image</button>
                      <button @click="store.addContent(sub.content, 'tabel')" class="btn-content text-xs">+ Table</button>
                      <button @click="store.addContent(sub.content, 'rumus')" class="btn-content text-xs">+ Formula</button>
                    </div>
                  </div>
                </template>
              </draggable>

              <button @click="store.addSubsection(sIdx)"
                class="mt-3 w-full py-2 border border-dashed border-cream-400 dark:border-ash-600 text-navy-500 dark:text-ash-300 hover:bg-cream-100 dark:hover:bg-ash-700 text-sm transition-colors active:scale-95 transition-transform">
                + Add Subsection
              </button>
            </div>
          </template>
        </draggable>

        <button @click="store.addSection()"
          class="w-full py-3 border-2 border-dashed border-cream-300 dark:border-ash-600 text-navy-400 dark:text-ash-300 hover:border-navy-400 dark:hover:border-cream-400 hover:text-navy-700 dark:hover:text-cream-200 transition text-sm active:scale-95 transition-transform">
          + Add Section
        </button>

        <!-- References -->
        <div class="card border-l-4 border-l-red-400">
          <div class="flex items-center justify-between mb-3">
            <label class="label !mb-0">References</label>
            <button @click="store.addReference()" class="btn-add">+ Reference</button>
          </div>
          <draggable :list="store.paper.references" :item-key="(_, i) => i" animation="150" handle=".ref-drag" class="space-y-1.5"
                     :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
            <template #item="{ element: ref, index: i }">
              <div class="group flex gap-2 items-center">
                <span role="button" aria-label="Drag to reorder" class="ref-drag cursor-grab active:cursor-grabbing text-ink-300 hover:text-ink-500 select-none shrink-0">⠿</span>
                <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                  <button @click="moveItem(store.paper.references, i, i - 1)" :disabled="i === 0" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move up">↑</button>
                  <button @click="moveItem(store.paper.references, i, i + 1)" :disabled="i === store.paper.references.length - 1" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move down">↓</button>
                </div>
                <span class="text-[11px] text-ink-400 w-7 text-right shrink-0">[{{ i + 1 }}]</span>
                <input :value="ref" @input="store.paper.references[i] = $event.target.value"
                  class="input-sm flex-1 text-xs" placeholder="Reference text..." />
                <button @click="store.removeReference(i)" class="text-red-300 hover:text-red-500 text-xs shrink-0">✕</button>
              </div>
            </template>
          </draggable>
        </div>

        <div class="h-20"></div>
      </div>

      <!-- TAB: PREVIEW -->
      <div v-show="activeTab === 'preview'" role="tabpanel" id="panel-preview" aria-labelledby="tab-preview">
        <PreviewTab />
      </div>
        </div>
      </div>

      <!-- RIGHT: Tools menu / Chat / Journal / Literatur / Files / Data / Tool workspace -->
      <div v-if="toolsOpen" class="bg-cream-50 dark:bg-ash-800 shrink-0 overflow-y-auto min-h-0 flex flex-col w-1/2 border-l border-cream-300 dark:border-ash-700">
        <div class="px-4 lg:px-8 py-4 space-y-1">
          <!-- Chat -->
          <button @click="openRightPanel('chat')"
            class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-ink-700 dark:text-ink-200 hover:border-navy-500 dark:hover:border-cream-400 transition-colors text-left active:scale-[0.98]">
            <span class="text-base">💬</span>
            <span class="text-xs font-medium">AI Chat</span>
          </button>
          <!-- Journal -->
          <button @click="openRightPanel('journal')"
            class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-ink-700 dark:text-ink-200 hover:border-navy-500 dark:hover:border-cream-400 transition-colors text-left active:scale-[0.98]">
            <span class="text-base">📚</span>
            <span class="text-xs font-medium">Journal</span>
          </button>
          <!-- Literatur -->
          <button @click="openRightPanel('literature')"
            class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-ink-700 dark:text-ink-200 hover:border-navy-500 dark:hover:border-cream-400 transition-colors text-left active:scale-[0.98]">
            <span class="text-base">📖</span>
            <span class="text-xs font-medium">Literatur</span>
          </button>
          <!-- Files -->
          <button @click="openRightPanel('files')"
            class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-ink-700 dark:text-ink-200 hover:border-navy-500 dark:hover:border-cream-400 transition-colors text-left active:scale-[0.98]">
            <span class="text-base">📂</span>
            <span class="text-xs font-medium">Files</span>
          </button>
          <!-- Data -->
          <button @click="openRightPanel('data')"
            class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-ink-700 dark:text-ink-200 hover:border-navy-500 dark:hover:border-cream-400 transition-colors text-left active:scale-[0.98]">
            <span class="text-base">📊</span>
            <span class="text-xs font-medium">Data</span>
          </button>
          <div class="h-px bg-cream-300 dark:bg-ash-600 my-3"></div>
          <!-- Writing tools -->
          <button v-for="tool in toolsStore.TOOLS" :key="tool.id" @click="openToolWorkspace(tool)"
            class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-800 text-ink-700 dark:text-ink-200 hover:border-navy-500 dark:hover:border-cream-400 transition-colors text-left active:scale-[0.98]">
            <span class="text-base">{{ tool.icon }}</span>
            <span class="text-xs font-medium">{{ tool.title }}</span>
          </button>
        </div>
      </div>

      <div v-else-if="rightPanel === 'chat'" class="bg-cream-50 dark:bg-ash-800 shrink-0 overflow-hidden flex flex-col w-1/2 border-l border-cream-300 dark:border-ash-700">
        <ChatTab :paper-id="store.currentPaperId" @open-preview="activeTab = 'preview'" />
      </div>

      <div v-else-if="rightPanel === 'journal'" class="bg-cream-50 dark:bg-ash-800 shrink-0 overflow-y-auto flex flex-col w-1/2 border-l border-cream-300 dark:border-ash-700">
        <div class="px-4 lg:px-8 py-6"><JournalTab /></div>
      </div>

      <div v-else-if="rightPanel === 'literature'" class="bg-cream-50 dark:bg-ash-800 shrink-0 overflow-y-auto flex flex-col w-1/2 border-l border-cream-300 dark:border-ash-700">
        <div class="px-4 lg:px-8 py-6"><LiteratureTab /></div>
      </div>

      <div v-else-if="rightPanel === 'files'" class="bg-cream-50 dark:bg-ash-800 shrink-0 overflow-y-auto flex flex-col w-1/2 border-l border-cream-300 dark:border-ash-700">
        <div class="px-4 lg:px-8 py-6"><FilesTab /></div>
      </div>

      <div v-else-if="rightPanel === 'data'" class="bg-cream-50 dark:bg-ash-800 shrink-0 overflow-y-auto flex flex-col w-1/2 border-l border-cream-300 dark:border-ash-700">
        <div class="px-4 lg:px-8 py-6"><DataTab /></div>
      </div>

      <div v-else-if="rightPanel === 'tool-workspace'" class="bg-cream-50 dark:bg-ash-800 shrink-0 overflow-y-auto flex flex-col w-1/2 border-l border-cream-300 dark:border-ash-700">
        <div class="px-4 lg:px-8 py-6"><ToolsTab /></div>
      </div>
    </div>

    <!-- Toast -->
    <Teleport to="body">
      <div v-if="store.toast.show" class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60]">
        <div :class="['px-4 py-2.5 rounded-lg shadow-lg text-white text-sm font-medium',
          store.toast.type === 'success' ? 'bg-green-600' :
          store.toast.type === 'error' ? 'bg-red-600' : 'bg-blue-600']">
          {{ store.toast.message }}
        </div>
      </div>
    </Teleport>

    <!-- Delete Confirmation Dialog -->
    <AppDialog
      :open="!!deleteTarget"
      :title="deleteTarget?.type === 'section' ? 'Hapus Section?' : 'Hapus Subsection?'"
      @close="cancelDelete"
    >
      <p class="text-sm text-ink-700 dark:text-ink-200">
        <span class="font-semibold">"{{ deleteTarget?.title }}"</span> dan semua kontennya akan dihapus permanen.
      </p>
      <template #actions>
        <button
          @click="cancelDelete"
          class="px-4 py-2 rounded-lg text-sm font-medium text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700 transition-colors active:scale-95 transition-transform"
        >
          Batal
        </button>
        <button
          @click="doDelete"
          class="px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-700 text-white transition-colors active:scale-95 transition-transform"
        >
          Hapus
        </button>
      </template>
    </AppDialog>

    <!-- Keyboard Shortcuts Help -->
    <ShortcutsHelp
      :open="showShortcutsHelp"
      :shortcuts="shortcuts"
      @close="showShortcutsHelp = false"
    />
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import draggable from 'vuedraggable'
import { usePaperStore } from '../stores/paper.js'
import { useUiStore } from '../stores/ui.js'
import { useChatStore } from '../stores/chat.js'
import AppHeader from '../components/AppHeader.vue'
import AppDialog from '../components/AppDialog.vue'
import ShortcutsHelp from '../components/ShortcutsHelp.vue'
import ContentList from '../components/ContentList.vue'
import FilesTab from '../components/FilesTab.vue'
import JournalTab from '../components/JournalTab.vue'
import LiteratureTab from '../components/LiteratureTab.vue'
import PreviewTab from '../components/PreviewTab.vue'
import ChatTab from '../components/ChatTab.vue'
import DataTab from '../components/DataTab.vue'
import ToolsTab from '../components/ToolsTab.vue'
import { useToolsStore } from '../stores/tools.ts'
import { useImageGenStore } from '../stores/imageGen.js'
import { usePaperJobsStore } from '../stores/paperJobs.js'
import { useKeyboardShortcuts, type KeyboardShortcut } from '../composables/useKeyboardShortcuts'

const store = usePaperStore()
const ui = useUiStore()
const chatStore = useChatStore()
const toolsStore = useToolsStore()
const imageGenStore = useImageGenStore()
const paperJobsStore = usePaperJobsStore()
const route = useRoute()
const router = useRouter()

// rofiq.txt #2 + #3: tab & chat panel state per-paper, restore saat reload.
// Default paper baru = no tab + chat full (lihat ui.js).
// `activeTab` is a computed proxy onto the UI store so chat-triggered tab
// switches (e.g. SLR auto-open) take effect immediately.
const activeTab = computed({
  get: () => (store.currentPaperId ? ui.getTab(store.currentPaperId) : '') || 'editor',
  set: (v) => {
    if (store.currentPaperId) ui.setTab(store.currentPaperId, v || '')
  },
})
// Force a re-read whenever something external bumps the signal — even when
// the new tab id is the same as the old one.
watch(() => ui.tabSwitchSignal, () => { /* computed re-evaluates via getTab */ })

// Delete confirmation state
interface DeleteTarget {
  type: 'section' | 'subsection'
  sectionIndex: number
  subsectionIndex?: number
  title: string
}
const deleteTarget = ref<DeleteTarget | null>(null)
const newKeyword = ref('')
const abstractRef = ref<HTMLTextAreaElement | null>(null)
const saveStatus = ref('saved')
const lastSavedAt = ref<number | null>(null)
const nowTick = ref(Date.now())
const aiStartedAt = ref<number | null>(null)

// ─── Split layout state ───────────────────────────────────────────────────
// rightPanel: '' = closed | 'chat' | 'journal' | 'literature' | 'files' | 'data' | 'tool-workspace'
const rightPanel = ref('chat')
const toolsOpen = ref(false) // shows the tools menu list

function openRightPanel(panel) {
  toolsOpen.value = false
  rightPanel.value = panel
  // Ensure left pane shows something (default to editor if nothing selected)
  if (!activeTab.value) activeTab.value = 'editor'
}

function openToolWorkspace(tool) {
  toolsOpen.value = false
  toolsStore.setActiveTool(tool)
  rightPanel.value = 'tool-workspace'
  if (!activeTab.value) activeTab.value = 'editor'
}

function toggleTools() {
  if (toolsOpen.value) {
    toolsOpen.value = false
  } else {
    rightPanel.value = ''
    toolsOpen.value = true
  }
}

function handlePapersBack() {
  const onPaperChatHome = rightPanel.value === 'chat' && !toolsOpen.value && !chatStore.currentConversationId && activeTab.value === 'editor'
  if (!onPaperChatHome && store.currentPaperId) {
    rightPanel.value = 'chat'
    toolsOpen.value = false
    activeTab.value = 'editor'
    chatStore.currentConversationId = null
    return
  }
  router.push({ name: 'dashboard' })
}
const showShortcutsHelp = ref(false)

const shortcuts: KeyboardShortcut[] = [
  {
    key: 'k',
    ctrl: true,
    handler: () => { rightPanel.value = rightPanel.value === 'chat' ? '' : 'chat'; toolsOpen.value = false },
    description: 'Toggle AI Chat panel'
  },
  {
    key: 'z',
    ctrl: true,
    handler: () => {
      store.undo()
    },
    description: 'Undo last change'
  },
  {
    key: 'z',
    ctrl: true,
    shift: true,
    handler: () => {
      store.redo()
    },
    description: 'Redo last undone change'
  },
  {
    key: 's',
    ctrl: true,
    handler: async () => {
      if (!store.loading) {
        saveStatus.value = 'saving'
        try {
          await store.savePaperToDb(true)
          lastSavedAt.value = Date.now()
          saveStatus.value = 'saved'
        } catch (e) {
          saveStatus.value = 'error'
        }
      }
    },
    description: 'Save paper manually'
  },
  {
    key: 'e',
    ctrl: true,
    handler: () => {
      if (!store.loading) {
        store.exportDocx()
      }
    },
    description: 'Export paper to DOCX'
  },
  {
    key: '1',
    ctrl: true,
    handler: () => { activeTab.value = 'editor' },
    description: 'Switch to Editor tab'
  },
  {
    key: '2',
    ctrl: true,
    handler: () => { openRightPanel('journal') },
    description: 'Switch to Journal tab'
  },
  {
    key: '3',
    ctrl: true,
    handler: () => { openRightPanel('literature') },
    description: 'Switch to Literature tab'
  },
  {
    key: '4',
    ctrl: true,
    handler: () => { openRightPanel('files') },
    description: 'Switch to Files tab'
  },
  {
    key: '5',
    ctrl: true,
    handler: () => { openRightPanel('data') },
    description: 'Switch to Data tab'
  },
  {
    key: '6',
    ctrl: true,
    handler: () => { toggleTools() },
    description: 'Toggle Tools panel'
  },
  {
    key: 'n',
    ctrl: true,
    handler: () => {
      store.addSection()
    },
    description: 'Add new section'
  },
  {
    key: '/',
    ctrl: true,
    handler: () => {
      showShortcutsHelp.value = true
    },
    description: 'Show keyboard shortcuts help'
  }
]

useKeyboardShortcuts(shortcuts)

// ─── Topic / Style / PDF state (used by chat for file attach) ─────────────
const availableTopics = ref([])
const availableStyles = ref([])

const keyMap = new WeakMap()
let __kc = 0
function stableKey(obj: any) {
  if (typeof obj !== 'object' || !obj) return String(obj)
  if (!keyMap.has(obj)) keyMap.set(obj, String(++__kc))
  return keyMap.get(obj)
}

let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
let tickTimer: ReturnType<typeof setInterval> | null = null
const savedRelative = computed(() => lastSavedAt.value ? 'just now' : 'just now')
const aiElapsedSeconds = computed(() => aiStartedAt.value ? Math.floor((nowTick.value - aiStartedAt.value) / 1000) : 0)
const aiElapsedLabel = computed(() => aiElapsedSeconds.value < 60 ? `0:${String(aiElapsedSeconds.value).padStart(2, '0')}` : `${Math.floor(aiElapsedSeconds.value / 60)}m ${aiElapsedSeconds.value % 60}s`)
const canCancelAi = computed(() => typeof chatStore.stopStreaming === 'function')

watch(() => store.aiLoading, (v) => {
  aiStartedAt.value = v ? Date.now() : null
})

watch(() => store.paper, () => {
  if (!store.paper.title?.trim() && !store.currentPaperId) return
  clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(async () => {
    saveStatus.value = 'saving'
    try {
      const id = await store.savePaperToDb(true)
      lastSavedAt.value = Date.now()
      saveStatus.value = 'saved'
      if (id && route.name === 'editor-new') {
        router.replace({ name: 'editor', params: { paperId: id } })
      }
    } catch (e) {
      saveStatus.value = 'error'
    }
  }, 1800)
}, { deep: true })

onUnmounted(() => {
  clearTimeout(autoSaveTimer)
  clearInterval(tickTimer)
  window.removeEventListener('resize', resizeAbstract)
  paperJobsStore.stopPolling()
  chatStore.stopActiveJobPolling()
})

onMounted(async () => {
  tickTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
  window.addEventListener('resize', resizeAbstract)
  imageGenStore.resume()
  // Global recent-done poller (10s); guarded so multiple mounts don't stack.
  paperJobsStore.startGlobalPolling()
  const paperId = route.params.paperId
  if (paperId && paperId !== 'null' && paperId !== 'undefined') {
    const paperIdStr = Array.isArray(paperId) ? paperId[0] : paperId
    await store.loadPaperFromDb(paperIdStr)
    rightPanel.value = 'chat'
  } else {
    store.newPaper()
    rightPanel.value = 'chat'
    const newId = await store.savePaperToDb(true)
    if (newId) {
      router.replace({ name: 'editor', params: { paperId: newId } })
      rightPanel.value = 'chat'
    }
  }
  // Start active-job poller for whichever paper we ended up on.
  if (store.currentPaperId) {
    paperJobsStore.startPolling(store.currentPaperId)
  }
  try {
    const [tRes, sRes] = await Promise.all([
      store.apiGet('/api/topics'),
      store.apiGet('/api/styles'),
    ])
    availableTopics.value = tRes?.data?.topics || []
    availableStyles.value = sRes?.data?.styles || []
  } catch (e) { /* non-critical */ }

  if (route.query.tab) {
    activeTab.value = String(route.query.tab)
  }

  nextTick(() => {
    resizeAbstract()
  })
})

watch(activeTab, (newTab) => {
  router.replace({ query: { ...route.query, tab: newTab || undefined } })
}, { immediate: false })

watch(() => store.paper.abstract, () => resizeAbstract())
watch(() => rightPanel.value, () => resizeAbstract())

watch(() => route.params.paperId, async (newId, oldId) => {
  if (newId && newId !== 'null' && newId !== 'undefined' && newId !== oldId && newId !== store.currentPaperId) {
    const newIdStr = Array.isArray(newId) ? newId[0] : newId
    await store.loadPaperFromDb(newIdStr)
    rightPanel.value = 'chat'
    resizeAbstract()
  }
})

// Restart per-paper job polling whenever the active paper changes.
watch(() => store.currentPaperId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    paperJobsStore.startPolling(newId)
  } else if (!newId) {
    paperJobsStore.stopPolling()
  }
})

function toRoman(num: number) { return store.toRoman(num) }
function toggleTab(id: string) {
  activeTab.value = activeTab.value === id ? '' : id
}
function onTabKeydown(e: KeyboardEvent) {
  // Arrow key navigation not needed with simplified toolbar
  return
}
function moveItem(list: any[], from: number, to: number) {
  if (!Array.isArray(list) || to < 0 || to >= list.length || from === to) return
  const [item] = list.splice(from, 1)
  list.splice(to, 0, item)
}
async function retrySave() {
  saveStatus.value = 'saving'
  try {
    await store.savePaperToDb(true)
    lastSavedAt.value = Date.now()
    saveStatus.value = 'saved'
  } catch (e) {
    saveStatus.value = 'error'
  }
}
function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}
function resizeAbstract() {
  nextTick(() => {
    const el = abstractRef.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = el.scrollHeight + 'px'
  })
}
function addKw() {
  if (newKeyword.value.trim()) { store.addKeyword(newKeyword.value.trim()); newKeyword.value = '' }
}

function confirmDeleteSection(sIdx: number) {
  const section = store.paper.sections[sIdx]
  deleteTarget.value = {
    type: 'section',
    sectionIndex: sIdx,
    title: section?.title || 'Untitled Section'
  }
}

function confirmDeleteSubsection(sIdx: number, subIdx: number) {
  const subsection = store.paper.sections[sIdx]?.subsections?.[subIdx]
  deleteTarget.value = {
    type: 'subsection',
    sectionIndex: sIdx,
    subsectionIndex: subIdx,
    title: subsection?.title || 'Untitled Subsection'
  }
}

function doDelete() {
  if (!deleteTarget.value) return
  
  if (deleteTarget.value.type === 'section') {
    store.removeSection(deleteTarget.value.sectionIndex)
  } else if (deleteTarget.value.type === 'subsection') {
    store.removeSubsection(deleteTarget.value.sectionIndex, deleteTarget.value.subsectionIndex)
  }
  
  deleteTarget.value = null
}

function cancelDelete() {
  deleteTarget.value = null
}

</script>

<style scoped>
.card { @apply bg-white dark:bg-anthracite-700 rounded-2xl shadow-[0_1px_0_rgba(15,14,11,0.04),0_1px_3px_rgba(15,14,11,0.06)] border border-ivory-300 dark:border-anthracite-500 p-5; }
.label { @apply block text-sm font-medium font-serif text-ink-900 dark:text-ink-50 mb-1.5; }
.input { @apply w-full px-3 py-2 border border-ivory-300 dark:border-anthracite-500 rounded-lg text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 focus:border-ink-700 dark:focus:border-anthracite-100 outline-none; }
.input-sm { @apply px-2.5 py-1.5 border border-ivory-300 dark:border-anthracite-500 rounded-lg text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 focus:border-ink-700 dark:focus:border-anthracite-100 outline-none; }
.btn-add { @apply px-3 py-1 bg-ivory-200 hover:bg-ivory-300 dark:bg-anthracite-600 dark:hover:bg-anthracite-500 text-ink-900 dark:text-anthracite-50 rounded-lg text-xs font-medium transition-colors active:scale-95 transition-transform; }
.btn-content { @apply px-2.5 py-1 bg-ivory-200 hover:bg-ivory-300 dark:bg-anthracite-600 dark:hover:bg-anthracite-500 text-ink-900 dark:text-anthracite-50 rounded text-xs transition-colors active:scale-95 transition-transform; }
</style>
