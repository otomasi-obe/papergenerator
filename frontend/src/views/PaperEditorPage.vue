<template>
 <div class="h-screen flex flex-col bg-cream-50 dark:bg-ash-850 transition">
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
 class="flex items-center gap-1.5 text-sm text-ink-700 dark:text-ink-200 hover:text-ink-900 dark:hover:text-ink-50 px-2 py-1.5 rounded hover:bg-cream-200 dark:hover:bg-ash-700 shrink-0 transition active:scale-95 "
 >
 ← Kembali ke Dashboard
 </button>
 <span class="h-5 w-px bg-cream-300 dark:bg-ash-600 shrink-0" aria-hidden="true"></span>
 <input
 v-model="store.paper.title"
 placeholder="Untitled Paper"
 class="text-sm text-ink-900 dark:text-ink-50 font-medium bg-transparent border border-transparent hover:border-cream-400 dark:hover:border-ash-600 focus:border-navy-500 dark:focus:border-cream-400 focus:bg-cream-50 dark:focus:bg-ash-800 focus:outline-none focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 rounded px-2 py-1 truncate min-w-[8rem] w-0 flex-[1_1_12rem] max-w-none transition"
 title="Klik untuk mengubah judul paper"
 aria-label="Paper title"
 />
 <span v-if="store.loading" class="text-[11px] text-ink-600 dark:text-anthracite-200 animate-pulse shrink-0">Saving…</span>
 <button v-else-if="saveStatus === 'saving'" class="text-[11px] text-ink-600 dark:text-anthracite-200 animate-pulse shrink-0 active:scale-95 " type="button">Saving…</button>
 <button v-else-if="saveStatus === 'saved'" class="text-[11px] text-ink-700 dark:text-ink-200 shrink-0 active:scale-95 " type="button">Saved · {{ savedRelative }}</button>
 <button v-else-if="saveStatus === 'error'" @click="retrySave" class="text-[11px] text-red-600 dark:text-red-300 hover:underline shrink-0 active:scale-95 " type="button">Save failed</button>
 </div>

 <!-- Group B: actions + tabs + AI chat. Wraps to its own line when it no longer fits beside the title group -->
 <div class="flex flex-wrap items-center gap-x-2 gap-y-1.5 min-w-0 flex-[0_1_auto]">
 <div class="flex items-center gap-1 shrink-0">
   <button @click="store.exportDocx()" :disabled="store.loading"
   class="px-3 py-1.5 rounded-lg text-xs font-medium transition text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600 disabled:opacity-50 shrink-0 active:scale-95"
   title="Export DOCX">
   📄 DOCX
   </button>
   <button @click="store.undo()" :disabled="!store.canUndo"
   class="px-3 py-1.5 rounded-lg text-xs font-medium transition text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600 disabled:opacity-40 shrink-0 active:scale-95"
   title="Undo (Ctrl/Cmd+Z)">
   ↶ Undo
   </button>
   <button @click="store.redo()" :disabled="!store.canRedo"
   class="px-3 py-1.5 rounded-lg text-xs font-medium transition text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600 disabled:opacity-40 shrink-0 active:scale-95"
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
 <button @click="toggleEditor"
 :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition whitespace-nowrap active:scale-95',
 activeTab === 'editor' && editorVisible
 ? 'bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-ink-50'
 : 'text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600']">
 📝 Editor
 </button>
 <button @click="togglePreview"
 :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition whitespace-nowrap active:scale-95',
 activeTab === 'preview' && editorVisible
 ? 'bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-ink-50'
 : 'text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600']">
 👁 Preview
 </button>

 <button @click="toggleTools"
 :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition flex items-center gap-1 shrink-0 whitespace-nowrap active:scale-95',
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

 <!-- Generation status banner (non-blocking, driven by paperJobs) -->
 <div v-if="currentActiveJob"
 class="bg-cream-100 dark:bg-ash-700 border-b border-cream-300 dark:border-ash-600 px-4 lg:px-8 py-2.5 flex items-center gap-3 text-ink-700 dark:text-ink-200 text-sm shrink-0">
 <div class="relative w-6 h-6 shrink-0">
 <div class="absolute inset-0 rounded-full border-2 border-cream-300 dark:border-ash-500"></div>
 <div class="absolute inset-0 rounded-full border-2 border-t-ink-700 dark:border-t-ink-200 animate-spin"></div>
 </div>
 <div class="flex-1 min-w-0 leading-snug">
 <span class="font-medium">AI sedang membuat paper...</span>
 <span class="opacity-70 ml-2">· Elapsed: {{ aiElapsedLabel }}</span>
 <span v-if="currentActiveJob.progress" class="opacity-70 ml-2">· {{ currentActiveJob.progress }}%</span>
 <span v-if="aiElapsedSeconds > 600" class="ml-2 opacity-80">(masih bekerja — paper besar bisa sampai 15 menit)</span>
 </div>
 <button @click="cancelCurrentJob"
 class="shrink-0 px-2.5 py-1 rounded text-xs font-medium border border-cream-400 dark:border-ash-500 hover:bg-cream-200 dark:hover:bg-ash-600 active:scale-95 ">Cancel</button>
 </div>

 <!-- Split layout: LEFT editor (max 60%) + RIGHT tools (40%) -->
 <div ref="splitRoot" class="flex flex-1 min-h-0 overflow-hidden relative">
   <!-- LEFT pane: editor / preview -->
   <div v-show="editorVisible" class="min-w-0 overflow-hidden bg-cream-50/50 dark:bg-ash-850/50"
        :style="leftStyle"
        :class="[activeTab === 'preview' ? 'flex flex-col min-h-0' : 'overflow-y-auto', (!toolsOpen && !rightPanel) ? 'flex-1' : '']">
          <div :class="activeTab === 'preview' ? 'p-0 h-full min-h-0 w-full flex flex-col overflow-hidden' : 'px-4 lg:px-8 py-6'">

        <!-- TAB: EDITOR -->
 <div v-show="activeTab === 'editor'" role="tabpanel" id="panel-editor" aria-labelledby="tab-editor" class="space-y-4">
 <!-- Title -->
 <div class="card" style="border-left: 4px solid #1265c8">
 <label class="label">Title</label>
 <textarea v-model="store.paper.title" v-autosize rows="1"
 ref="titleRef"
 class="input resize-none overflow-hidden" placeholder="Paper title..."></textarea>
 </div>

 <!-- Authors -->
 <div class="card" style="border-left: 4px solid #1265c8">
 <div class="flex items-center justify-between mb-3">
 <label class="label !mb-0">Authors</label>
 <button @click="store.addAuthor()" class="btn-add">+ Author</button>
 </div>
 <draggable :list="store.paper.authors" :item-key="stableKey" animation="150" handle=".author-drag" class="space-y-2"
 :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
 <template #item="{ element: author, index: i }">
 <div class="group bg-cream-50 dark:bg-ash-800 border border-cream-200/60 dark:border-ash-600/60 rounded-lg p-3 flex gap-2 items-start">
 <span role="button" aria-label="Drag to reorder" class="author-drag cursor-grab active:cursor-grabbing text-ivory-500 dark:text-anthracite-200 hover:text-ink-700 dark:hover:text-anthracite-50 select-none text-xl leading-tight pt-1">⠿</span>
 <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
 <button @click="moveItem(store.paper.authors, i, i - 1)" :disabled="i === 0" class="text-[10px] text-ink-500 dark:text-anthracite-200 disabled:opacity-30" aria-label="Move up">↑</button>
 <button @click="moveItem(store.paper.authors, i, i + 1)" :disabled="i === store.paper.authors.length - 1" class="text-[10px] text-ink-500 dark:text-anthracite-200 disabled:opacity-30" aria-label="Move down">↓</button>
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
 <div class="card" style="border-left: 4px solid #1265c8">
 <label class="label">Abstract</label>
 <textarea v-model="store.paper.abstract" v-autosize rows="2"
 ref="abstractRef"
 class="input resize-none overflow-hidden min-h-[4.5rem]"
 placeholder="Paper abstract..."
 :class="{ 'highlight-bg': isAbstractHighlighted }"></textarea>
 </div>

 <!-- Keywords -->
 <div class="card" style="border-left: 4px solid #9f7d54">
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
 <div class="group card" style="border-left: 4px solid #806044">
 <div class="flex items-center justify-between mb-3">
 <div class="flex items-center gap-2 flex-1 min-w-0">
 <span role="button" aria-label="Drag to reorder" class="section-drag cursor-grab active:cursor-grabbing text-cream-400 dark:text-ash-400 hover:text-navy-500 dark:hover:text-cream-300 select-none text-xl leading-tight shrink-0">⠿</span>
 <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
 <button @click="moveItem(store.paper.sections, sIdx, sIdx - 1)" :disabled="sIdx === 0" class="text-[10px] text-ink-500 dark:text-anthracite-200 disabled:opacity-30" aria-label="Move up">↑</button>
 <button @click="moveItem(store.paper.sections, sIdx, sIdx + 1)" :disabled="sIdx === store.paper.sections.length - 1" class="text-[10px] text-ink-500 dark:text-anthracite-200 disabled:opacity-30" aria-label="Move down">↓</button>
 </div>
 <span class="text-[10px] text-ink-500 dark:text-ink-300 font-medium uppercase tracking-wide bg-transparent border-l-2 border-ivory-300 pl-2 shrink-0">
 Section {{ toRoman(sIdx + 1) }}
 </span>
 <input v-model="section.title" class="input-sm flex-1 text-base font-semibold min-w-0"
 placeholder="Section Title (e.g. INTRODUCTION)" />
 </div>
 <button @click="confirmDeleteSection(sIdx)"
 class="text-xs text-red-400 hover:text-red-600 dark:hover:text-red-300 dark:text-red-400 px-2 py-1 ml-2 shrink-0">✕</button>
 </div>

 <ContentList :items="section.content" :store="store" :section-title="section.title" />
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
 <button @click="moveItem(section.subsections, subIdx, subIdx - 1)" :disabled="subIdx === 0" class="text-[10px] text-ink-500 dark:text-anthracite-200 disabled:opacity-30" aria-label="Move up">↑</button>
 <button @click="moveItem(section.subsections, subIdx, subIdx + 1)" :disabled="subIdx === section.subsections.length - 1" class="text-[10px] text-ink-500 dark:text-anthracite-200 disabled:opacity-30" aria-label="Move down">↓</button>
 </div>
 <span class="text-[10px] text-ink-500 dark:text-ink-300 font-medium uppercase tracking-wide bg-transparent border-l-2 border-ivory-300 pl-2 shrink-0">
 {{ String.fromCharCode(65 + subIdx) }}
 </span>
 <input v-model="sub.title" class="input-sm flex-1 text-base font-semibold min-w-0"
 placeholder="Subsection Title" />
 </div>
 <button @click="confirmDeleteSubsection(sIdx, subIdx)"
 class="text-xs text-red-400 hover:text-red-600 dark:hover:text-red-300 dark:text-red-400 px-2 py-1 ml-2 shrink-0">✕</button>
 </div>
 <ContentList :items="sub.content" :store="store" :section-title="section.title + ' > ' + sub.title" />
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
 class="mt-3 w-full py-2 border border-dashed border-cream-400 dark:border-ash-600 text-navy-500 dark:text-ash-300 hover:bg-cream-100 dark:hover:bg-ash-700 text-sm transition active:scale-95 ">
 + Add Subsection
 </button>
 </div>
 </template>
 </draggable>

 <button @click="store.addSection()"
 class="w-full py-3 border-2 border-dashed border-cream-300 dark:border-ash-600 text-navy-400 dark:text-ash-300 hover:border-navy-400 dark:hover:border-cream-400 hover:text-navy-700 dark:hover:text-cream-200 transition text-sm active:scale-95 ">
 + Add Section
 </button>

 <!-- References -->
 <div class="card" style="border-left: 4px solid #f87171">
 <div class="flex items-center justify-between mb-3">
 <label class="label !mb-0">References</label>
 <button @click="store.addReference()" class="btn-add">+ Reference</button>
 </div>
 <draggable :list="store.paper.references" :item-key="(_, i) => i" animation="150" handle=".ref-drag" class="space-y-1.5"
 :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
 <template #item="{ element: ref, index: i }">
 <div class="group flex gap-2 items-center">
 <span role="button" aria-label="Drag to reorder" class="ref-drag cursor-grab active:cursor-grabbing text-ink-300 dark:text-anthracite-300 hover:text-ink-500 dark:hover:text-anthracite-200 select-none shrink-0">⠿</span>
 <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
 <button @click="moveItem(store.paper.references, i, i - 1)" :disabled="i === 0" class="text-[10px] text-ink-500 dark:text-anthracite-200 disabled:opacity-30" aria-label="Move up">↑</button>
 <button @click="moveItem(store.paper.references, i, i + 1)" :disabled="i === store.paper.references.length - 1" class="text-[10px] text-ink-500 dark:text-anthracite-200 disabled:opacity-30" aria-label="Move down">↓</button>
 </div>
 <span class="text-[11px] text-ink-400 dark:text-anthracite-300 w-7 text-right shrink-0">[{{ i + 1 }}]</span>
 <input :value="displayRef(ref)" @input="store.paper.references[i] = $event.target.value"
 class="input-sm flex-1 text-xs" placeholder="Reference text..." />
 <button @click="store.removeReference(i)" class="text-red-300 dark:text-red-400 hover:text-red-500 dark:hover:text-red-300 text-xs shrink-0">✕</button>
 </div>
 </template>
 </draggable>
 </div>

 <div class="h-20"></div>
 </div>

 <!-- TAB: PREVIEW -->
 <div v-show="activeTab === 'preview'" role="tabpanel" id="panel-preview" aria-labelledby="tab-preview" class="h-full min-h-0 w-full flex flex-col overflow-hidden">
 <PreviewTab ref="previewTabRef" :show-zoom="!rightPanel && !toolsOpen && editorVisible" />
 </div>
 </div>
 </div>

 <!-- DIVIDER (draggable) -->
 <div
   v-if="editorVisible && (toolsOpen || rightPanel)"
   class="w-1 hover:w-1.5 bg-cream-300 dark:bg-ash-700 hover:bg-[#2969ac] dark:hover:bg-[#2969ac] cursor-col-resize transition-all shrink-0 select-none"
   @mousedown="startResize"
 ></div>

 <!-- RIGHT PANEL (animated slide-in) -->
 <Transition name="panel-slide">
 <div v-if="toolsOpen || rightPanel" :style="editorVisible ? rightStyle : undefined" :class="editorVisible ? '' : 'w-full'" class="bg-cream-50 dark:bg-ash-800 shrink-0 overflow-y-auto min-h-0 flex flex-col">

   <!-- Single cream-padded back button (ALL sub-panels incl. Generate Full) -->
   <div v-if="!toolsOpen && rightPanel" class="sticky top-0 z-10 bg-cream-50/95 dark:bg-ash-800/95 backdrop-blur-sm border-b border-cream-200/60 dark:border-ash-700/60 px-4 lg:px-6 py-3">
     <button @click="backToTools" class="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-navy-700 dark:text-cream-200 bg-cream-100 dark:bg-ash-700 hover:bg-cream-200 dark:hover:bg-ash-600 border border-cream-300 dark:border-ash-600 transition active:scale-95">
       <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
       Tools
     </button>
   </div>

   <!-- Tools grid -->
   <template v-if="toolsOpen">
     <ToolsTab @openPanel="openRightPanel" />
   </template>

   <!-- Sub-panels -->
   <template v-else-if="rightPanel === 'paperfull'">
     <div class="px-4 lg:px-8 py-6"><PaperfullTab /></div>
   </template>

   <template v-else-if="rightPanel === 'journal'">
     <div class="px-4 lg:px-8 py-6"><JournalTab /></div>
   </template>

   <template v-else-if="rightPanel === 'literature'">
     <div class="px-4 lg:px-8 py-6"><LiteratureTab /></div>
   </template>

   <template v-else-if="rightPanel === 'files'">
     <div class="px-4 lg:px-8 py-6"><FilesTab /></div>
   </template>

   <template v-else-if="rightPanel === 'data'">
     <div class="px-4 lg:px-8 py-6"><DataTab /></div>
   </template>

   <template v-else-if="rightPanel === 'image'">
     <div class="px-4 lg:px-8 py-6"><ImageTab /></div>
   </template>

   <template v-else-if="rightPanel === 'tool-workspace'">
     <div class="px-4 lg:px-8 py-6"><ToolsTab @openPanel="openRightPanel" /></div>
   </template>

 </div>
 </Transition>
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
 class="px-4 py-2 rounded-lg text-sm font-medium text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700 transition active:scale-95 "
 >
 Batal
 </button>
 <button
 @click="doDelete"
 class="px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-700 text-white transition active:scale-95 "
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

 <WordAddonInstallModal 
 :show="showWordAddonModal" 
 @close="showWordAddonModal = false" 
 />
 </div>

</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, watch, onMounted, onUnmounted, nextTick, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import draggable from 'vuedraggable'
import { usePaperStore } from '../stores/paper.js'
import { useUiStore } from '../stores/ui.js'
import { useChatStore } from '../stores/chat.js'
import { useAuthStore } from '../stores/auth.ts'
import AppHeader from '../components/AppHeader.vue'
import AppDialog from '../components/AppDialog.vue'
import ShortcutsHelp from '../components/ShortcutsHelp.vue'
import ContentList from '../components/ContentList.vue'
import { useToolsStore } from '../stores/tools.ts'
import { useImageGenStore } from '../stores/imageGen.js'
import { usePaperJobsStore } from '../stores/paperJobs.js'
import { useQuotaStore } from '../stores/quota.js'
import { useUserStateStore } from '../stores/userState'
import { useKeyboardShortcuts, type KeyboardShortcut } from '../composables/useKeyboardShortcuts'

// Lazy-loaded tab components (shown conditionally; no need to bundle eagerly)
const PreviewTab = defineAsyncComponent(() => import('../components/PreviewTab.vue'))
const JournalTab = defineAsyncComponent(() => import('../components/JournalTab.vue'))
const LiteratureTab = defineAsyncComponent(() => import('../components/LiteratureTab.vue'))
const FilesTab = defineAsyncComponent(() => import('../components/FilesTab.vue'))
const DataTab = defineAsyncComponent(() => import('../components/DataTab.vue'))
const PaperfullTab = defineAsyncComponent(() => import('../components/PaperfullTab.vue'))
const ImageTab = defineAsyncComponent(() => import('../components/ImageTab.vue'))
const ToolsTab = defineAsyncComponent(() => import('../components/ToolsTab.vue'))
const WordAddonInstallModal = defineAsyncComponent(() => import('@/components/WordAddonInstallModal.vue'))

const store = usePaperStore()
const ui = useUiStore()
const chatStore = useChatStore()
const authStore = useAuthStore()
const toolsStore = useToolsStore()
const imageGenStore = useImageGenStore()
const paperJobsStore = usePaperJobsStore()
const quotaStore = useQuotaStore()
const userState = useUserStateStore()
const route = useRoute()
const router = useRouter()

// Highlight for Abstract (AI stabilo effect)
const isAbstractHighlighted = computed(() => store.highlightedBlocks?.abstract?.includes(0))

// Display helper for references — handles strings and structured objects
function displayRef(ref: any): string {
 if (typeof ref === 'string') return ref
 if (ref && ref.text) return ref.text
 return store.formatRef(ref) || ''
}

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
const titleRef = ref<HTMLTextAreaElement | null>(null)
const abstractRef = ref<HTMLTextAreaElement | null>(null)
const saveStatus = ref('saved')
const previewTabRef = ref<InstanceType<typeof PreviewTab> | null>(null)
const lastSavedAt = ref<number | null>(null)
const nowTick = ref(Date.now())

// ─── Split layout state ───────────────────────────────────────────────────
// rightPanel: '' = closed | 'journal' | 'literature' | 'files' | 'data' | 'image' | 'tool-workspace'
// Persisted state via userState store (per-paper)
// All four layout fields route through the `ui` store (single source of truth =
// perPaper) so the deep-watcher in ui.ts never clobbers userState with a stale
// perPaper value. (Bug: writing toolsOpen directly to userState left perPaper.toolsOpen
// stale → switching tabs re-synced the stale `false`, closing the tools panel.)
const rightPanel = computed({
 get: () => ui.getRightPanel(store.currentPaperId || ''),
 set: (val) => ui.setRightPanel(store.currentPaperId || '', val),
})
const toolsOpen = computed({
 get: () => ui.getToolsOpen(store.currentPaperId || ''),
 set: (val) => ui.setToolsOpen(store.currentPaperId || '', val),
})
const editorVisible = computed({
 get: () => ui.getEditorVisible(store.currentPaperId || ''),
 set: (val) => ui.setEditorVisible(store.currentPaperId || '', val),
})

const showWordAddonModal = ref(false)

// ─── Split pane percentage (persisted, draggable divider) ─────────────────
const splitRoot = ref<HTMLElement | null>(null)
const rightPanelPercent = computed({
  get: () => ui.getRightPanelPercent(store.currentPaperId || ''),
  set: (val: number) => ui.setRightPanelPercent(store.currentPaperId || '', val),
})
const leftStyle = computed(() => {
  if (!editorVisible.value) return undefined
  if (!toolsOpen.value && !rightPanel.value) return undefined
  return { flex: `0 0 calc(${100 - rightPanelPercent.value}% - 2px)` }
})
const rightStyle = computed(() => {
  if (!editorVisible.value) return undefined
  return { flex: `0 0 calc(${rightPanelPercent.value}% - 2px)` }
})
const isResizing = ref(false)

function startResize(e: MouseEvent) {
  e.preventDefault()
  isResizing.value = true
  const root = splitRoot.value
  if (!root) return
  const onMove = (ev: MouseEvent) => {
    const rect = root.getBoundingClientRect()
    const pct = ((ev.clientX - rect.left) / rect.width) * 100
    // pct is where divider is from left → right panel = 100 - pct
    rightPanelPercent.value = 100 - pct
  }
  const onUp = () => {
    isResizing.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function openRightPanel(panel) {
 toolsOpen.value = false
 rightPanel.value = panel
 if (!activeTab.value) activeTab.value = 'editor'
 // Don't force editor open — respect user's last close state
}

function backToTools() {
 toolsOpen.value = true
 rightPanel.value = ''
 toolsStore.clearActiveTool()
}

function openToolWorkspace(tool) {
 if (tool.external) {
 if (tool.id === 'word-addon') {
 showWordAddonModal.value = true
 }
 return
 }
 
 toolsOpen.value = false
 toolsStore.setActiveTool(tool)
 rightPanel.value = 'tool-workspace'
 // Don't force editor/preview open — respect user's last close state
}

function toggleTools() {
 if (toolsOpen.value) {
 toolsOpen.value = false
 // If no right panel is open, re-show editor so page isn't blank
 if (!rightPanel.value) editorVisible.value = true
 } else {
 rightPanel.value = ''
 toolsOpen.value = true
 // Don't re-show editor — user wants tools full-width
 }
}

function toggleEditor() {
 if (activeTab.value === 'editor' && editorVisible.value) {
 editorVisible.value = false
 // Ensure something is open on the right so page isn't blank
 if (!toolsOpen.value && !rightPanel.value) {
 toolsOpen.value = true
 }
 } else {
 editorVisible.value = true
 activeTab.value = 'editor'
 }
}

function togglePreview() {
 if (activeTab.value === 'preview' && editorVisible.value) {
 editorVisible.value = false
 if (!toolsOpen.value && !rightPanel.value) {
 toolsOpen.value = true
 }
 } else {
 editorVisible.value = true
 activeTab.value = 'preview'
 // Auto-refresh PDF when switching to Preview tab
 nextTick(() => previewTabRef.value?.renderPdf())
 }
}

function handlePapersBack() {
  // Chat is now floating AI Assistant — no right panel for chat
  // Back button: go to dashboard
  router.push({ name: 'dashboard' })
}
const showShortcutsHelp = ref(false)

const shortcuts: KeyboardShortcut[] = [
 {
 key: 'k',
 ctrl: true,
 handler: () => {
 // Toggle: if any right panel open, close it; otherwise open paperfull
 if (rightPanel.value) {
 rightPanel.value = ''
 toolsOpen.value = false
 if (!editorVisible.value) editorVisible.value = true
 } else {
 rightPanel.value = 'paperfull'
 toolsOpen.value = false
 if (!editorVisible.value) editorVisible.value = true
 }
 },
 description: 'Toggle right panel'
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
 },
 {
   key: 'ArrowLeft',
   ctrl: true,
   shift: true,
   handler: () => {
     if (toolsOpen.value || rightPanel.value) {
       rightPanelPercent.value = rightPanelPercent.value - 5
     }
   },
   description: 'Shrink right panel'
 },
 {
   key: 'ArrowRight',
   ctrl: true,
   shift: true,
   handler: () => {
     if (toolsOpen.value || rightPanel.value) {
       rightPanelPercent.value = rightPanelPercent.value + 5
     }
   },
   description: 'Expand tools panel width'
 }
 ]

useKeyboardShortcuts(shortcuts)

const keyMap = new WeakMap()
let __kc = 0
function stableKey(obj: any) {
 if (typeof obj !== 'object' || !obj) return String(obj)
 if (!keyMap.has(obj)) keyMap.set(obj, String(++__kc))
 return keyMap.get(obj)
}

let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
let _justLoaded = false
let tickTimer: ReturnType<typeof setInterval> | null = null
const savedRelative = computed(() => {
 if (!lastSavedAt.value) return ''
 const diff = Math.floor((nowTick.value - lastSavedAt.value) / 1000)
 if (diff < 5) return 'just now'
 if (diff < 60) return `${diff}s ago`
 if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
 return `${Math.floor(diff / 3600)}h ago`
})

const currentActiveJob = computed(() => {
 if (!store.currentPaperId) return null
 return paperJobsStore.activeByPaper[store.currentPaperId] || null
})

const aiElapsedSeconds = computed(() => {
 const job = currentActiveJob.value
 if (!job?.created_at) return 0
 return Math.floor((nowTick.value - new Date(job.created_at).getTime()) / 1000)
})
const aiElapsedLabel = computed(() => aiElapsedSeconds.value < 60 ? `0:${String(aiElapsedSeconds.value).padStart(2, '0')}` : `${Math.floor(aiElapsedSeconds.value / 60)}m ${aiElapsedSeconds.value % 60}s`)

function cancelCurrentJob() {
 const job = currentActiveJob.value
 if (job?.id) {
 paperJobsStore.cancel(job.id)
 }
}

watch(() => store.paper, () => {
 if (_justLoaded) { _justLoaded = false; return }
 // Skip auto-save when paper is being reloaded from DB (e.g., paper_applied event)
 // to prevent the stale frontend data from overwriting the AI's edits
 if (store._loadingFromDb) return
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
 window.removeEventListener('resize', handleResize)
 paperJobsStore.stopPolling()
 paperJobsStore.stopGlobalPolling()
 imageGenStore.stopPoller()
 quotaStore.stopPolling()
 chatStore.stopActiveJobPolling()
})

onMounted(async () => {
 tickTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
 window.addEventListener('resize', handleResize)
 imageGenStore.resume()
 // Global recent-done poller (10s); guarded so multiple mounts don't stack.
 paperJobsStore.startGlobalPolling()
 const paperId = route.params.paperId
 const lang = authStore.user?.preferred_language || 'id'

 // Helper: restore right panel from persisted state, defaulting to '' (closed).
 function _restorePanel(): void {
 const saved = store.currentPaperId ? ui.getRightPanel(store.currentPaperId) : ''
 rightPanel.value = saved || ''
 }

 const paperIdRaw = Array.isArray(paperId) ? paperId[0] : paperId
 if (paperIdRaw && paperIdRaw !== 'null' && paperIdRaw !== 'undefined') {
 const loaded = await store.loadPaperFromDb(paperIdRaw)
 if (loaded) _justLoaded = true
 if (!loaded && !store.currentPaperId) {
 await store.newPaper(lang)
 const newId = await store.savePaperToDb(true)
 if (newId) {
 router.replace({ name: 'editor', params: { paperId: newId } })
 }
 }
 _restorePanel()
 } else {
 await store.newPaper(lang)
 _restorePanel()
 const newId = await store.savePaperToDb(true)
 if (newId) {
 router.replace({ name: 'editor', params: { paperId: newId } })
 _restorePanel()
 }
 }
 // Start active-job poller for whichever paper we ended up on.
 if (store.currentPaperId) {
 paperJobsStore.startPolling(store.currentPaperId)
 await userState.loadForPaper(store.currentPaperId)
 }

if (route.query.tab) {
activeTab.value = String(route.query.tab)
editorVisible.value = true
}

 if (route.query.panel) {
const p = String(route.query.panel)
 if (p === 'paperfull' || p === 'chat' || p === 'journal' || p === 'literature' || p === 'files' || p === 'data' || p === 'image') {
 toolsOpen.value = false
 rightPanel.value = p
 }
 }

 nextTick(() => {
 resizeTitle()
 resizeAbstract()
 })
})

watch(activeTab, (newTab) => {
 const nextQuery = { ...route.query, tab: newTab || undefined }
 if (newTab === 'preview') {
 }
 router.replace({ query: nextQuery })
}, { immediate: false })

watch(() => store.paper.title, () => resizeTitle())
watch(() => store.paper.abstract, () => resizeAbstract())
watch(() => rightPanel.value, () => { resizeTitle(); resizeAbstract() })

watch(() => route.params.paperId, async (newId, oldId) => {
 // Guard: handle array and various nullish values.
 const pid = Array.isArray(newId) ? newId[0] : newId
 if (!pid || pid === 'null' || pid === 'undefined') return
 if (pid !== oldId && pid !== store.currentPaperId) {
 const loaded = await store.loadPaperFromDb(pid)
 if (!loaded && !store.currentPaperId) {
 // Paper deleted — redirect to dashboard to pick a valid paper.
 router.replace({ name: 'dashboard' })
 return
 }
 // Restore right panel from per-paper state; fallback '' (closed).
 const saved = store.currentPaperId ? ui.getRightPanel(store.currentPaperId) : ''
 rightPanel.value = saved || ''
 resizeTitle()
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
function resizeTitle() {
 nextTick(() => {
 const el = titleRef.value
 if (!el) return
 const scrollParent = el.closest('.overflow-y-auto') as HTMLElement | null
 const st = scrollParent?.scrollTop ?? 0
 el.style.height = 'auto'
 el.style.height = el.scrollHeight + 'px'
 if (scrollParent && scrollParent.scrollTop !== st) {
 scrollParent.scrollTop = st
 }
 })
}
function resizeAbstract() {
 nextTick(() => {
 const el = abstractRef.value
 if (!el) return
 const scrollParent = el.closest('.overflow-y-auto') as HTMLElement | null
 const st = scrollParent?.scrollTop ?? 0
 el.style.height = 'auto'
 el.style.height = el.scrollHeight + 'px'
 if (scrollParent && scrollParent.scrollTop !== st) {
 scrollParent.scrollTop = st
 }
 })
}
const handleResize = () => { resizeTitle(); resizeAbstract() }
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
.card { @apply bg-white dark:bg-ash-800 rounded-2xl shadow-[0_1px_3px_rgba(15,14,11,0.06)] dark:shadow-[0_1px_0_rgba(0,0,0,0.25),0_2px_8px_rgba(0,0,0,0.3)] border border-cream-200/60 dark:border-ash-600/60 p-5 transition-shadow duration-200; }
.card:hover { box-shadow: 0 1px 0 rgba(15,14,11,0.04), 0 4px 12px rgba(15,14,11,0.1); }
.dark .card:hover { box-shadow: 0 1px 0 rgba(0,0,0,0.25), 0 4px 16px rgba(0,0,0,0.4); }
.label { @apply block text-xs font-semibold font-sans uppercase tracking-wide text-ink-500 dark:text-ink-200 mb-1.5; }
.input { @apply w-full px-3 py-2 border border-cream-200/60 dark:border-ash-600/60 rounded-lg text-sm bg-white dark:bg-ash-900 text-ink-900 dark:text-cream-50 placeholder-ink-400 dark:placeholder-ash-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 focus:border-navy-500 dark:focus:border-cream-300 outline-none transition duration-150; }
.input-sm { @apply px-2.5 py-1.5 border border-cream-200/60 dark:border-ash-600/60 rounded-lg text-sm bg-white dark:bg-ash-900 text-ink-900 dark:text-cream-50 placeholder-ink-400 dark:placeholder-ash-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 focus:border-navy-500 dark:focus:border-cream-300 outline-none transition duration-150; }
.btn-add { @apply px-3 py-1 bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600 text-ink-700 dark:text-cream-50 rounded-lg text-xs font-medium transition active:scale-95 ; }
.btn-content { @apply px-2.5 py-1 bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600 text-ink-700 dark:text-cream-50 rounded text-xs transition active:scale-95 ; }

/* Panel slide-in animation */
.panel-slide-enter-active { transition: transform 0.25s ease-out, opacity 0.2s ease-out; }
.panel-slide-leave-active { transition: transform 0.15s ease-in, opacity 0.15s ease-in; }
.panel-slide-enter-from { transform: translateX(24px); opacity: 0; }
.panel-slide-leave-to { transform: translateX(12px); opacity: 0; }
</style>
