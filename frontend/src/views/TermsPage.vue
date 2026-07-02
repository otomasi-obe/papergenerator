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
        <h1 class="text-3xl font-bold text-ink-900 dark:text-ink-50 mb-2">Syarat & Ketentuan</h1>
        <p class="text-sm text-ink-500 dark:text-ink-400 mb-8">Terakhir diperbarui: 30 Juni 2026</p>

        <p class="text-ink-700 dark:text-ink-200">
          Selamat datang di Paperfull. Dengan mengakses dan menggunakan layanan kami, Anda dianggap telah membaca, memahami, dan menyetujui seluruh ketentuan berikut.
        </p>

        <h2 class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-8 mb-4">1. Tentang Layanan</h2>
        <p class="text-ink-700 dark:text-ink-200">
          Paperfull adalah platform berbasis kecerdasan buatan (AI) yang membantu pengguna menghasilkan dokumen paper akademik dalam format DOCX, dengan pilihan template jurnal yang dapat disesuaikan dengan kebutuhan pengguna.
        </p>

        <h2 class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-8 mb-4">2. Penggunaan Layanan</h2>
        <ul class="list-disc pl-6 space-y-2 text-ink-700 dark:text-ink-200">
          <li>Pengguna wajib berusia minimal 17 tahun atau memiliki izin dari orang tua/wali untuk menggunakan layanan ini.</li>
          <li>Pengguna bertanggung jawab penuh atas keakuratan data dan materi yang dimasukkan ke dalam sistem untuk diproses oleh AI.</li>
          <li>Paperfull hanya berfungsi sebagai alat bantu penyusunan dokumen. Pengguna tetap bertanggung jawab untuk memeriksa, menyunting, dan memverifikasi keakuratan, orisinalitas, serta kesesuaian akademik dari hasil yang dihasilkan sebelum digunakan atau dipublikasikan.</li>
          <li>Pengguna dilarang menggunakan layanan untuk tujuan yang melanggar hukum, termasuk namun tidak terbatas pada plagiarisme, pemalsuan data penelitian, atau pelanggaran hak cipta pihak lain.</li>
        </ul>

        <h2 class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-8 mb-4">3. Akun Pengguna</h2>
        <ul class="list-disc pl-6 space-y-2 text-ink-700 dark:text-ink-200">
          <li>Pengguna wajib mendaftarkan akun dengan data yang benar dan terkini.</li>
          <li>Pengguna bertanggung jawab menjaga kerahasiaan informasi akun dan kata sandi.</li>
          <li>Paperfull berhak menangguhkan atau menghentikan akun yang terindikasi melanggar ketentuan ini.</li>
        </ul>

        <h2 class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-8 mb-4">4. Pembayaran</h2>
        <ul class="list-disc pl-6 space-y-2 text-ink-700 dark:text-ink-200">
          <li>Layanan tertentu pada Paperfull bersifat berbayar dan dikenakan biaya sesuai dengan paket/nominal yang tertera saat transaksi.</li>
          <li>Pembayaran diproses melalui mitra penyedia jasa pembayaran (payment gateway) resmi yang bekerja sama dengan Paperfull.</li>
          <li>Bukti pembayaran yang sah adalah notifikasi yang diterima melalui sistem Paperfull setelah transaksi berhasil diverifikasi oleh penyedia jasa pembayaran.</li>
          <li>Paperfull tidak menyimpan data kartu pembayaran atau rekening pengguna; seluruh proses pembayaran ditangani oleh mitra payment gateway yang telah memenuhi standar keamanan yang berlaku.</li>
        </ul>

        <h2 class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-8 mb-4">5. Hak Kekayaan Intelektual</h2>
        <ul class="list-disc pl-6 space-y-2 text-ink-700 dark:text-ink-200">
          <li>Dokumen yang dihasilkan melalui Paperfull menjadi hak pengguna setelah pembayaran (jika berlaku) diselesaikan, dengan tetap memperhatikan bahwa konten yang dihasilkan AI dapat memerlukan tinjauan dan penyuntingan lebih lanjut oleh pengguna.</li>
          <li>Template jurnal yang tersedia di platform disediakan untuk tujuan referensi format dan dapat tunduk pada ketentuan hak cipta dari penerbit jurnal terkait. Pengguna bertanggung jawab memastikan kepatuhan terhadap ketentuan penerbit jurnal yang dituju.</li>
          <li>Paperfull tidak mengklaim kepemilikan atas konten substantif/ilmiah yang dimasukkan oleh pengguna.</li>
        </ul>

        <h2 class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-8 mb-4">6. Batasan Tanggung Jawab</h2>
        <ul class="list-disc pl-6 space-y-2 text-ink-700 dark:text-ink-200">
          <li>Paperfull berupaya memberikan hasil terbaik dari sistem AI, namun tidak menjamin bahwa hasil yang dihasilkan akan 100% bebas dari kesalahan, bias, atau ketidakakuratan.</li>
          <li>Paperfull tidak bertanggung jawab atas konsekuensi penggunaan dokumen hasil generate, termasuk namun tidak terbatas pada penolakan publikasi, tuduhan plagiarisme, atau sanksi akademik yang mungkin timbul akibat kelalaian pengguna dalam memverifikasi hasil.</li>
          <li>Layanan disediakan "sebagaimana adanya" tanpa jaminan ketersediaan tanpa gangguan.</li>
        </ul>

        <h2 class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-8 mb-4">7. Perubahan Layanan dan Ketentuan</h2>
        <p class="text-ink-700 dark:text-ink-200">
          Paperfull berhak mengubah, menambah, atau menghentikan sebagian maupun seluruh layanan, serta memperbarui ketentuan ini sewaktu-waktu. Perubahan akan diinformasikan melalui platform.
        </p>

        <h2 class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-8 mb-4">8. Hukum yang Berlaku</h2>
        <p class="text-ink-700 dark:text-ink-200">
          Ketentuan ini diatur dan ditafsirkan berdasarkan hukum yang berlaku di Republik Indonesia.
        </p>

        <h2 class="text-2xl font-bold text-ink-900 dark:text-ink-50 mt-8 mb-4">9. Kontak</h2>
        <p class="text-ink-700 dark:text-ink-200">
          Pertanyaan terkait Syarat & Ketentuan ini dapat disampaikan melalui halaman <router-link to="/contact" class="text-amber-700 dark:text-amber-400 hover:underline">Kontak</router-link> kami.
        </p>
      </article>
    </main>
  </div>
</template>

<script setup lang="ts">
import PublicHeader from '../components/PublicHeader.vue'
</script>
