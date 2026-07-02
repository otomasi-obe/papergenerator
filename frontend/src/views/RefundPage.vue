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
        <h1 class="text-3xl font-bold text-ink-900 dark:text-ink-50 mb-2">Kebijakan Refund</h1>
        <p class="text-sm text-ink-500 dark:text-ink-400 mb-8">Terakhir diperbarui: 30 Juni 2026</p>

        <p class="text-ink-700 dark:text-ink-200 mb-6">
          Kami berkomitmen memberikan layanan terbaik. Apabila terjadi kendala pada transaksi Anda, berikut ketentuan pengembalian dana (refund) yang berlaku di Paperfull.
        </p>

        <h2 class="text-2xl font-semibold text-ink-900 dark:text-ink-50 mt-8 mb-4">1. Kondisi yang Memenuhi Syarat Refund</h2>
        <p class="text-ink-700 dark:text-ink-200 mb-3">Pengguna berhak mengajukan refund apabila:</p>
        <ul class="list-disc pl-6 space-y-2 text-ink-700 dark:text-ink-200">
          <li>Pembayaran berhasil diproses oleh sistem, namun layanan/dokumen yang dipesan gagal dihasilkan akibat kesalahan teknis dari pihak Paperfull.</li>
          <li>Pengguna dikenakan biaya ganda (double charge) untuk satu transaksi yang sama akibat kegagalan sistem.</li>
          <li>Layanan yang diterima tidak sesuai dengan deskripsi paket yang dipesan (misalnya jumlah halaman, format template, atau fitur yang tidak diberikan sebagaimana dijanjikan).</li>
        </ul>

        <h2 class="text-2xl font-semibold text-ink-900 dark:text-ink-50 mt-8 mb-4">2. Kondisi yang Tidak Memenuhi Syarat Refund</h2>
        <p class="text-ink-700 dark:text-ink-200 mb-3">Refund tidak berlaku apabila:</p>
        <ul class="list-disc pl-6 space-y-2 text-ink-700 dark:text-ink-200">
          <li>Dokumen telah berhasil di-generate sesuai pesanan dan diunduh oleh pengguna, namun pengguna tidak puas dengan kualitas konten substantif/akademik yang dihasilkan AI (perlu disunting kembali oleh pengguna sebagai bagian dari proses normal).</li>
          <li>Kesalahan input data oleh pengguna sendiri (misalnya salah memilih template, salah memasukkan judul/konten sumber).</li>
          <li>Pengguna berubah pikiran setelah dokumen berhasil diunduh.</li>
          <li>Pengajuan dilakukan lebih dari 7 (tujuh) hari kalender setelah transaksi dilakukan.</li>
        </ul>

        <h2 class="text-2xl font-semibold text-ink-900 dark:text-ink-50 mt-8 mb-4">3. Cara Mengajukan Refund</h2>
        <p class="text-ink-700 dark:text-ink-200 mb-3">Kirimkan permintaan refund melalui halaman <router-link to="/contact" class="text-amber-700 dark:text-amber-400 hover:underline font-medium">Kontak</router-link> dengan menyertakan:</p>
        <ul class="list-disc pl-6 space-y-2 text-ink-700 dark:text-ink-200">
          <li>Bukti transaksi (ID transaksi/invoice)</li>
          <li>Tanggal dan waktu transaksi</li>
          <li>Alasan pengajuan refund</li>
        </ul>
        <p class="text-ink-700 dark:text-ink-200 mt-4">
          Tim kami akan meninjau pengajuan dalam waktu maksimal 3 (tiga) hari kerja.
        </p>
        <p class="text-ink-700 dark:text-ink-200 mt-2">
          Apabila disetujui, dana akan dikembalikan ke metode pembayaran asal dalam waktu 5–14 hari kerja, tergantung kebijakan dan proses dari penyedia jasa pembayaran (payment gateway) terkait.
        </p>

        <h2 class="text-2xl font-semibold text-ink-900 dark:text-ink-50 mt-8 mb-4">4. Catatan</h2>
        <p class="text-ink-700 dark:text-ink-200">
          Paperfull berhak menolak pengajuan refund yang tidak memenuhi syarat di atas atau yang terindikasi sebagai bentuk penyalahgunaan kebijakan ini. Keputusan akhir terkait persetujuan refund berada di tangan tim Paperfull setelah proses peninjauan.
        </p>

        <h2 class="text-2xl font-semibold text-ink-900 dark:text-ink-50 mt-8 mb-4">5. Kontak</h2>
        <p class="text-ink-700 dark:text-ink-200">
          Pertanyaan lebih lanjut mengenai kebijakan ini dapat disampaikan melalui halaman <router-link to="/contact" class="text-amber-700 dark:text-amber-400 hover:underline font-medium">Kontak</router-link> kami.
        </p>
      </article>
    </main>
  </div>
</template>

<script setup lang="ts">
import PublicHeader from '../components/PublicHeader.vue'
</script>
