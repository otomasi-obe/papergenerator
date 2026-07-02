<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <PublicHeader />

    <main class="max-w-4xl mx-auto px-6 py-12">
      <div class="mb-6">
        <router-link to="/" class="inline-flex items-center gap-1.5 text-sm text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 font-medium transition-colors">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 19l-7-7 7-7"/></svg>
          Kembali ke Beranda
        </router-link>
      </div>
      <article class="prose prose-lg dark:prose-invert max-w-none">
        <h1 class="text-3xl font-bold text-ink-900 dark:text-ink-50 mb-8">Kontak</h1>

        <div class="bg-white dark:bg-ash-800 rounded-xl border border-cream-200 dark:border-ash-700 p-8 space-y-6">
          <div>
            <h2 class="text-xl font-bold text-ink-900 dark:text-ink-50 mb-2">Email</h2>
            <a href="mailto:anabilhisyam23@gmail.com" class="text-amber-700 dark:text-amber-400 hover:underline">
              anabilhisyam23@gmail.com
            </a>
          </div>

          <div>
            <h2 class="text-xl font-bold text-ink-900 dark:text-ink-50 mb-2">Nomor Telepon</h2>
            <a href="tel:+6281291493497" class="text-amber-700 dark:text-amber-400 hover:underline">
              +62 812-9149-3497
            </a>
          </div>

          <div>
            <h2 class="text-xl font-bold text-ink-900 dark:text-ink-50 mb-2">Alamat Usaha</h2>
            <p class="text-ink-700 dark:text-ink-200">
              Jl. Gubernur Mochtar, Tembalang<br>
              Kec. Tembalang, Kota Semarang<br>
              Jawa Tengah 50275
            </p>
          </div>
        </div>

        <p class="text-sm text-ink-500 dark:text-ink-400 mt-8">
          Kami akan merespons pertanyaan Anda dalam 1-2 hari kerja.
        </p>
      </article>
    </main>
  </div>
</template>

<script setup lang="ts">
import PublicHeader from '../components/PublicHeader.vue'
</script>
