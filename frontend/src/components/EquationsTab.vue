<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-gray-800">Equations</h2>
      <button @click="store.addEquation()"
        class="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:brightness-95 text-sm font-medium">
        + Add Equation
      </button>
    </div>

    <p class="text-sm text-gray-500 mb-4">
      Write LaTeX equations. Use <code class="bg-gray-100 px-1 rounded">$$latex$$</code> in section content for display equations,
      or <code class="bg-gray-100 px-1 rounded">$latex$</code> for inline.
    </p>

    <div v-if="store.paper.equations.length === 0"
      class="text-center py-12 text-gray-400">
      <svg class="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M4.871 4A17.926 17.926 0 003 12c0 2.874.673 5.59 1.871 8m14.13 0A17.926 17.926 0 0021 12c0-2.874-.673-5.59-1.871-8M9 9h1.246a1 1 0 01.961.725l1.586 5.55a1 1 0 00.961.725H15m1-7h-.08a2 2 0 00-1.519.698L9.6 15.302A2 2 0 018.08 16H8" />
      </svg>
      <p>No equations yet.</p>
    </div>

    <div v-for="(eq, index) in store.paper.equations" :key="eq.id"
      class="border rounded-xl p-4 mb-4 bg-gray-50">
      <div class="flex items-start justify-between mb-3">
        <span class="text-sm font-semibold text-gray-700">Equation ({{ eq.number }})</span>
        <button @click="store.removeEquation(index)"
          class="text-red-400 hover:text-red-600 text-sm">✕ Remove</button>
      </div>

      <div class="space-y-3">
        <!-- LaTeX Input -->
        <div>
          <label class="block text-xs text-gray-500 mb-1">LaTeX</label>
          <textarea v-model="eq.latex" rows="2" v-autosize
            placeholder="e.g.: E = mc^2 or \frac{a}{b}"
            class="w-full px-3 py-2 border rounded font-mono text-sm focus:ring-2 focus:ring-blue-200 outline-none resize-y"></textarea>
        </div>

        <!-- Preview -->
        <div class="bg-white rounded p-3 border text-center">
          <div v-html="renderKatex(eq.latex)" class="katex-preview"></div>
          <span class="text-sm text-gray-400 ml-4">({{ eq.number }})</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { usePaperStore } from '../stores/paper.js'
import katex from 'katex'
import DOMPurify from 'dompurify'

const store = usePaperStore()

function renderKatex(latex) {
  if (!latex) return '<span class="text-gray-300">Enter equation...</span>'
  try {
    const rendered = katex.renderToString(latex, {
      throwOnError: false,
      displayMode: true,
      trust: false,
      strict: 'ignore',
    })
    return DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true, mathMl: true, svg: true } })
  } catch (e) {
    return `<span class="text-red-500 text-sm">${DOMPurify.sanitize(String(e.message))}</span>`
  }
}
</script>
