<template>
  <div v-if="isOpen" class="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-8 sm:pt-10">
    <!-- Backdrop (z-60, below modal content) -->
        <div
          class="fixed inset-0 bg-black/30 transition-opacity z-0"
          @click="close"
          aria-hidden="true"
        />

    <!-- Modal card (z-[70], above backdrop) -->
    <div class="relative z-[70] w-full max-w-3xl h-[84vh] sm:h-[88vh] bg-white dark:bg-ash-900 rounded-2xl shadow-xl flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-cream-200 dark:border-ash-700 shrink-0">
        <h2 class="text-lg font-bold text-ink-900 dark:text-ink-50">
          {{ step === 'package' ? 'Beli Paket Token' : step === 'method' ? 'Pilih Metode Pembayaran' : (method === 'qris' ? 'Bayar dengan QRIS' : 'Bayar dengan Virtual Account') }}
        </h2>
        <button
          @click="close"
          class="p-1.5 min-h-[36px] min-w-[36px] rounded-lg text-ink-400 hover:text-ink-600 dark:hover:text-ink-300 hover:bg-cream-100 dark:hover:bg-ash-800 transition-colors"
          aria-label="Tutup"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Body -->
      <div class="px-5 py-4 overflow-y-auto space-y-4 flex-1">
        <!-- Step 1: Package Selection -->
        <div v-show="step === 'package'">
          <p class="text-sm text-ink-800 dark:text-ink-200 mb-3">Pilih paket token yang ingin Anda beli:</p>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div
              v-for="pkg in packages"
              :key="pkg.id"
              @click="selectPackage(pkg)"
              :class="[
                'relative rounded-xl border-2 p-3 sm:p-4 transition-all duration-300',
                pkg.maintenance ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
                selectedPackageId === pkg.id
                  ? 'border-[var(--accent)] bg-cream-50 dark:bg-ash-800 shadow-lg dark:shadow-[0_0_24px_rgba(130,200,255,0.45)]'
                  : pkg.maintenance
                    ? 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800'
                    : 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 hover:border-[var(--accent)] hover:shadow-[0_0_22px_rgba(130,200,255,0.35)] dark:hover:shadow-[0_0_22px_rgba(130,200,255,0.5)]'
              ]"
            >
              <div
                v-if="pkg.popular"
                class="absolute -top-2 left-1/2 -translate-x-1/2 bg-[var(--accent)] text-white text-xs font-bold px-2 py-0.5 rounded-full"
              >
                Populer
              </div>
              <div
                v-if="pkg.maintenance"
                class="absolute -top-2 right-2 bg-amber-500 text-white text-xs font-bold px-2 py-0.5 rounded-full"
              >
                Maintenance
              </div>
              <div class="text-center">
                <div class="text-2xl mb-1">{{ pkg.icon }}</div>
                <h3 class="font-semibold text-ink-900 dark:text-ink-50 text-sm">{{ pkg.name }}</h3>
                <p class="text-xs text-ink-500 dark:text-cream-100 mb-2">{{ pkg.duration }}</p>
                <div class="text-base sm:text-lg font-bold text-ink-900 dark:text-ink-50">{{ formatIDR(pkg.price) }}</div>
                <p class="text-xs font-bold text-cream-700 dark:text-cream-200">{{ formatTokenShort(pkg.tokens) }} token</p>
                <!-- Badge -->
                <BadgeTier :badge="pkg.badge" size="sm" class="mt-2" />
                <!-- Benefits -->
                <ul class="mt-2 text-left text-[11px] text-ink-600 dark:text-cream-100 space-y-0.5 border-t border-cream-200 dark:border-ash-700 pt-2">
                  <li v-for="b in BADGE_TIERS[pkg.badge].benefits" :key="b" class="flex items-center gap-1.5">
                    <svg class="w-3 h-3 text-emerald-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>
                    {{ b }}
                  </li>
                  <!-- Image Generation Benefit -->
                  <li class="flex items-center gap-1.5 pt-1 border-t border-cream-200 dark:border-ash-700 mt-1">
                    <svg class="w-3 h-3 text-blue-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                    <span class="text-blue-600 dark:text-blue-400">{{ BADGE_TIERS[pkg.badge].imageModels[0] }}</span>
                    <span class="text-ink-400 dark:text-ink-500">({{ BADGE_TIERS[pkg.badge].imageQuality }})</span>
                  </li>
                </ul>
                <!-- Estimates -->
                <div class="mt-2 pt-2 border-t border-cream-200 dark:border-ash-700 text-xs text-ink-500 dark:text-cream-100 space-y-1">
                  <div>Generate Full ~{{ pkg.fullGenEstimate }}x</div>
                  <div>SLR ~{{ pkg.slrEstimate }}x</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Step 2: Payment Method Selection -->
        <div v-show="step === 'method'">
          <button
            @click="step = 'package'"
            class="text-xs text-ink-500 hover:text-ink-700 dark:hover:text-ink-200 mb-3 flex items-center gap-1"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
            </svg>
            Kembali ke pilih paket
          </button>
          <p class="text-sm text-ink-800 dark:text-ink-200 mb-3">Pilih metode pembayaran:</p>
          <div class="space-y-3 max-w-xl mx-auto">
            <!-- QRIS -->
            <button
              @click="method = 'qris'"
              :disabled="true"
              :class="[
                'w-full rounded-xl border-2 p-4 transition-all text-left hover:shadow-md',
                method === 'qris'
                  ? 'border-[var(--accent)] bg-cream-100 dark:bg-ash-700'
                  : 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 opacity-50 cursor-not-allowed'
              ]"
            >
              <div class="flex items-center gap-4">
                <div class="w-14 h-14 rounded-xl bg-[#E31937] flex items-center justify-center shrink-0">
                  <span class="text-white font-black text-sm tracking-tight">QRIS</span>
                </div>
                <div class="flex-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <h4 class="font-bold text-ink-900 dark:text-ink-50">QRIS</h4>
                    <span class="text-xs px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 font-semibold">Maintenance</span>
                  </div>
                  <p class="text-xs text-ink-500 dark:text-ink-400">Bayar instan dengan QRIS</p>
                </div>
                <div
                  :class="[
                    'w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0',
                    method === 'qris'
                      ? 'border-[var(--accent)] bg-[var(--accent)]'
                      : 'border-cream-300 dark:border-ash-600'
                  ]"
                >
                  <svg v-if="method === 'qris'" class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
            </button>

            <!-- Virtual Account -->
            <button
              @click="method = 'va'"
              :class="[
                'w-full rounded-xl border-2 p-4 transition-all text-left hover:shadow-md',
                method === 'va'
                  ? 'border-[var(--accent)] bg-cream-100 dark:bg-ash-700'
                  : 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 hover:border-[var(--accent)]'
              ]"
            >
              <div class="flex items-center gap-4">
                                <div class="w-14 h-14 rounded-xl bg-[#1A3A5C] flex items-center justify-center shrink-0">
                                  <span class="text-white font-black text-lg tracking-wider">VA</span>
                                </div>
                                <div class="flex-1">
                                  <div class="flex items-center gap-2 flex-wrap">
                                    <h4 class="font-bold text-ink-900 dark:text-ink-50">Virtual Account</h4>
                                    <span class="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 font-semibold">Active</span>
                                  </div>
                                  <p class="text-xs text-ink-500 dark:text-ink-400">Transfer ke nomor rekening virtual bank</p>
                                </div>
                <div
                  :class="[
                    'w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0',
                    method === 'va'
                      ? 'border-[var(--accent)] bg-[var(--accent)]'
                      : 'border-cream-300 dark:border-ash-600'
                  ]"
                >
                  <svg v-if="method === 'va'" class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
            </button>

            <!-- Bank grid (shown when VA selected) -->
            <div v-if="method === 'va'" class="ml-4 space-y-2">
              <label class="text-xs font-medium text-ink-500 dark:text-ink-400">Pilih Bank:</label>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <button
                  v-for="bank in banks"
                  :key="bank.channel"
                  :disabled="!bank.active"
                  @click="selectedBank = bank.channel"
                  :class="[
                    'relative rounded-xl border-2 p-3 text-center transition-all',
                    !bank.active
                      ? 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 opacity-50 cursor-not-allowed'
                      : selectedBank === bank.channel
                        ? 'border-[var(--accent)] bg-cream-100 dark:bg-ash-700 shadow-md'
                        : 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 hover:border-[var(--accent)] hover:shadow-sm'
                  ]"
                >
                  <span class="block text-sm font-bold text-ink-900 dark:text-ink-50">{{ bank.label }}</span>
                  <span v-if="!bank.active" class="block text-[10px] text-ink-400 mt-0.5">Coming Soon</span>
                  <svg v-if="bank.active && selectedBank === bank.channel" class="w-4 h-4 text-[var(--accent)] mx-auto mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Step 3: Payment Display -->
        <div v-show="step === 'payment'">
          <!-- Order Summary -->
          <div class="bg-cream-50 dark:bg-ash-800 rounded-xl border border-cream-200 dark:border-ash-700 p-4">
            <div class="flex justify-between items-center">
              <div>
                <h3 class="font-bold text-ink-900 dark:text-ink-50">{{ selectedPkg?.name }}</h3>
                <p class="text-sm text-ink-500 dark:text-ink-400">{{ selectedPkg?.tokens }} token • {{ selectedPkg?.duration }}</p>
                <BadgeTier v-if="selectedPkg" :badge="selectedPkg.badge" size="sm" class="mt-1" />
                <ul v-if="selectedPkg" class="mt-2 text-left text-xs text-ink-600 dark:text-cream-100 space-y-0.5 border-t border-cream-200 dark:border-ash-700 pt-2">
                  <li v-for="b in BADGE_TIERS[selectedPkg.badge].benefits" :key="b" class="flex items-center gap-1.5">
                    <svg class="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>
                    {{ b }}
                  </li>
                  <!-- Image Generation Benefit -->
                  <li class="flex items-center gap-1.5 pt-1 border-t border-cream-200 dark:border-ash-700 mt-1">
                    <svg class="w-3.5 h-3.5 text-blue-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                    <span class="text-blue-600 dark:text-blue-400">{{ BADGE_TIERS[selectedPkg.badge].imageModels[0] }}</span>
                    <span class="text-ink-400 dark:text-ink-500">({{ BADGE_TIERS[selectedPkg.badge].imageQuality }})</span>
                  </li>
                </ul>
              </div>
              <div class="text-right">
                <div class="text-xl font-bold text-ink-900 dark:text-ink-50">{{ formatIDR(selectedPkg?.price || 0) }}</div>
              </div>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="flex flex-col items-center justify-center py-12">
            <div class="w-12 h-12 border-4 border-cream-300 dark:border-ash-600 border-t-[var(--accent)] rounded-full animate-spin"></div>
            <p class="text-ink-500 dark:text-ink-400 text-sm mt-4">Membuat pembayaran...</p>
          </div>

          <!-- Success -->
          <div v-if="paymentStatus === 'paid'" class="text-center py-6">
            <div class="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center mx-auto mb-4">
              <svg class="w-9 h-9 text-emerald-600 dark:text-emerald-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 class="text-xl font-bold text-ink-900 dark:text-ink-50 mb-2">Pembayaran Berhasil</h3>
            <p class="text-sm text-ink-600 dark:text-ink-300 mb-4">Token sudah ditambahkan ke akun Anda.</p>
            <button @click="close" class="px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold transition">
              Tutup
            </button>
          </div>

          <!-- QRIS Display -->
          <div v-if="paymentData && method === 'qris' && paymentStatus !== 'paid' && paymentStatus !== 'failed'" class="text-center">
            <div class="bg-white rounded-xl p-3 sm:p-4 inline-block mb-4">
              <canvas ref="qrCanvasRef" width="240" height="240" class="w-48 h-48 sm:w-60 sm:h-60 mx-auto block"></canvas>
            </div>
            <div class="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2 mb-3 text-left max-w-sm mx-auto">
              <p class="text-blue-800 dark:text-blue-200 text-xs sm:text-sm font-semibold mb-1">Nominal pembayaran</p>
              <p class="text-blue-700 dark:text-blue-300 text-xs sm:text-sm">
                Masukkan manual sebesar <strong>{{ formatIDR(paymentData.amount || amount) }}</strong> jika aplikasi tidak mengisi otomatis.
              </p>
            </div>
            <div class="bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-2 mb-3 max-w-sm mx-auto inline-flex justify-between items-center w-full">
              <span class="text-amber-700 dark:text-amber-300 text-xs sm:text-sm font-medium">Bayar sebelum:</span>
              <span class="text-amber-700 dark:text-amber-300 font-bold text-base sm:text-lg">{{ countdown }}</span>
            </div>
            <div class="text-xs text-ink-800 dark:text-ink-200 space-y-1 mb-3 max-w-sm mx-auto text-left bg-cream-100 dark:bg-ash-700/50 rounded-lg px-3 py-2">
              <div class="flex justify-between"><span class="text-ink-700">Amount:</span><span class="font-medium text-ink-900 dark:text-ink-50">{{ formatIDR(paymentData.amount || amount) }}</span></div>
              <div v-if="paymentData.transaction_id" class="flex justify-between"><span class="text-ink-700">ID:</span><span class="font-mono text-[10px] sm:text-xs text-ink-800 dark:text-ink-200 break-all">{{ paymentData.transaction_id }}</span></div>
            </div>
            <div class="flex gap-2 max-w-sm mx-auto">
              <button @click="copyTransactionId" class="flex-1 py-2 text-xs sm:text-sm font-medium text-white bg-slate-600 hover:bg-slate-500 active:bg-slate-700 rounded-xl transition-all active:scale-95">
                {{ copied ? '✓ Tersalin!' : 'Salin ID Transaksi' }}
              </button>
            </div>
          </div>

          <!-- VA Display -->
          <div v-if="paymentData && method === 'va' && paymentStatus !== 'paid' && paymentStatus !== 'failed'" class="text-center">
            <div class="mb-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600">
              <div class="w-2 h-2 rounded-full bg-emerald-500"></div>
              <span class="text-xs font-semibold text-slate-700 dark:text-slate-200">Virtual Account {{ paymentData.bank_name || 'BRI' }}</span>
            </div>
            <div class="bg-white dark:bg-ash-700 rounded-xl p-4 sm:p-6 mb-4 max-w-sm mx-auto">
              <p class="text-xs text-ink-500 dark:text-ink-400 mb-1">Nomor Virtual Account</p>
              <p class="text-xl sm:text-2xl font-mono font-bold tracking-wider text-ink-900 dark:text-ink-50 select-all break-all">{{ paymentData.va_number || '000000' }}</p>
              <button @click="copyVANumber" class="mt-2 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:text-emerald-500">
                {{ copied ? '✓ Tersalin!' : 'Salin Nomor VA' }}
              </button>
            </div>
            <div class="bg-cyan-50 dark:bg-cyan-900/20 rounded-lg px-3 py-2 mb-3 max-w-sm mx-auto">
              <div class="flex justify-between items-center">
                <span class="text-cyan-700 dark:text-cyan-300 text-xs sm:text-sm font-medium">Menunggu Pembayaran</span>
                <span class="text-cyan-700 dark:text-cyan-300 font-bold text-sm sm:text-lg">{{ countdown }}</span>
              </div>
            </div>
            <div class="text-xs text-ink-800 dark:text-ink-200 space-y-1 mb-3 max-w-sm mx-auto text-left bg-cream-100 dark:bg-ash-700/50 rounded-lg px-3 py-2">
              <div class="flex justify-between"><span class="text-ink-700">Amount:</span><span class="font-semibold text-ink-900 dark:text-ink-50">{{ formatIDR(paymentData.amount || amount) }}</span></div>
              <div class="flex justify-between"><span class="text-ink-700">Token:</span><span class="font-medium text-ink-900 dark:text-ink-50">{{ paymentData.tokens || tokens }}</span></div>
              <div class="flex justify-between"><span class="text-ink-700">Bank:</span><span class="font-medium text-ink-900 dark:text-ink-50">{{ paymentData.bank_name || 'BRI' }}</span></div>
              <div v-if="paymentData.transaction_id" class="flex justify-between"><span class="text-ink-700">ID:</span><span class="font-mono text-[10px] sm:text-xs text-ink-800 dark:text-ink-200 break-all">{{ paymentData.transaction_id }}</span></div>
            </div>
            <div v-if="paymentData.how_to_pay_page" class="mb-4 max-w-sm mx-auto text-left">
              <button @click="showHowToPay = !showHowToPay" class="text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline mb-2">
                {{ showHowToPay ? '▼' : '▶' }} Cara Pembayaran Virtual Account
              </button>
              <div v-if="showHowToPay" class="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg p-3 text-xs text-ink-700 dark:text-ink-300 space-y-1">
                <p class="font-semibold text-ink-900 dark:text-ink-50">Transfer ke VA {{ paymentData.bank_name || 'BRI' }}:</p>
                <ol class="list-decimal list-inside space-y-0.5">
                  <li>Buka aplikasi mobile banking atau ATM {{ paymentData.bank_name || 'BRI' }}.</li>
                  <li>Pilih <strong>Transfer → Virtual Account</strong>.</li>
                  <li>Masukkan nomor VA <span class="font-mono font-bold">{{ paymentData.va_number }}</span>.</li>
                  <li>Nominal dikunci otomatis. Masukkan manual <strong>{{ formatIDR(paymentData.amount || amount) }}</strong> jika diminta.</li>
                  <li>Konfirmasi dan selesaikan pembayaran.</li>
                </ol>
              </div>
            </div>
            <div class="flex gap-2 max-w-sm mx-auto">
            </div>
          </div>

          <!-- Failed (API error) -->
          <div v-if="paymentStatus === 'failed' && !cancelClicked" class="text-center py-6">
            <div class="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center mx-auto mb-4">
              <svg class="w-9 h-9 text-red-600 dark:text-red-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h3 class="text-xl font-bold text-ink-900 dark:text-ink-50 mb-2">Pembayaran Gagal</h3>
            <p class="text-sm text-ink-700 dark:text-ink-200 mb-1">{{ error || 'Terjadi kesalahan saat memproses pembayaran.' }}</p>
            <button @click="resetPayment" class="px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold transition mt-2">
              Coba Lagi
            </button>
          </div>

          <!-- Cancelled by user -->
          <div v-if="paymentStatus === 'cancelled'" class="text-center py-6">
            <div class="w-16 h-16 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center mx-auto mb-4">
              <svg class="w-9 h-9 text-orange-600 dark:text-orange-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h3 class="text-xl font-bold text-ink-900 dark:text-ink-50 mb-2">Pembayaran Dibatalkan</h3>
            <p class="text-sm text-ink-600 dark:text-ink-300 mb-4">Transaksi telah dibatalkan.</p>
            <button @click="resetPayment" class="px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold transition">
              Coba Lagi
            </button>
          </div>

          <!-- Error -->
          <div v-if="error" class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 mt-4">
            <p class="text-red-800 dark:text-red-200 text-sm">{{ error }}</p>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-5 py-4 border-t border-cream-200 dark:border-ash-700 shrink-0 flex justify-between items-center">
        <!-- Step: package → disabled hint -->
        <button
          v-if="step === 'package'"
          @click="close"
          class="px-4 py-2 text-sm font-medium text-ink-700 dark:text-ink-200 bg-cream-100 dark:bg-ash-700 rounded-lg hover:bg-cream-200 dark:hover:bg-ash-600 transition active:scale-95"
        >
          Batal
        </button>
        <button
          v-if="step === 'package'"
          :disabled="!selectedPackageId"
          @click="step = 'method'"
          class="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition active:scale-95"
        >
          Lanjut → {{ selectedPkg ? formatIDR(selectedPkg.price) : 'pilih paket' }}
        </button>

        <!-- Step: method → back + confirm -->
        <button
          v-if="step === 'method'"
          @click="step = 'package'"
          class="px-4 py-2 text-sm font-medium text-ink-700 dark:text-ink-200 bg-cream-100 dark:bg-ash-700 rounded-lg hover:bg-cream-200 dark:hover:bg-ash-600 transition active:scale-95"
        >
          ← Kembali
        </button>
        <button
          v-if="step === 'method'"
          @click="confirmMethod"
          class="px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 rounded-lg transition active:scale-95"
        >
          Bayar dengan {{ method === 'qris' ? 'QRIS' : 'VA' }} →
        </button>

        <!-- Step: payment → cancel only (payment buttons inline) -->
        <div v-if="step === 'payment'" class="w-full text-center">
          <button
            v-if="paymentStatus === 'pending' || paymentStatus === 'expired'"
            @click="cancelPayment"
            class="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-500 active:bg-red-700 rounded-lg transition active:scale-95"
          >
            Batalkan Pembayaran
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import QRCode from 'qrcode'
import api from '../api/index.ts'
import { BADGE_TIERS, type BadgeKey } from '../config/badgeTiers'
import BadgeTier from './BadgeTier.vue'

interface Package {
  id: string
  name: string
  duration: string
  price: number
  tokens: number
  icon: string
  popular?: boolean
  maintenance?: boolean
  badge: BadgeKey
  fullGenEstimate: number
  slrEstimate: number
}

const props = defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const packages: Package[] = [
  {
    id: 'daily',
    name: 'Harian',
    duration: '24 Jam',
    price: 41000,
    tokens: 300000,
    icon: '⚡',
    popular: false,
    badge: 'starter',
    fullGenEstimate: 2,
    slrEstimate: 1
  },
  {
    id: 'weekly',
    name: 'Mingguan',
    duration: '7 Hari',
    price: 125000,
    tokens: 1200000,
    icon: '📅',
    popular: true,
    badge: 'pro',
    fullGenEstimate: 10,
    slrEstimate: 4
  },
  {
    id: 'monthly',
    name: 'Bulanan',
    duration: '30 Hari',
    price: 315000,
    tokens: 3500000,
    icon: '🗓️',
    badge: 'elite',
    fullGenEstimate: 29,
    slrEstimate: 14
  },
  {
    id: 'test',
    name: 'Test 1k',
    duration: '24 Jam',
    price: 1000,
    tokens: 10,
    icon: '🧪',
    popular: false,
    maintenance: true,
    badge: 'trial',
    fullGenEstimate: 0,
    slrEstimate: 0
  }
]

const step = ref<'package' | 'method' | 'payment'>('package')
const selectedPackageId = ref<string | null>(null)
const selectedPackage = ref<Package | null>(null)
const method = ref<'qris' | 'va'>('va')
const loading = ref(false)
const paymentData = ref<any>(null)
const paymentStatus = ref<'pending' | 'paid' | 'expired' | 'cancelled' | 'failed'>('pending')
const copied = ref(false)
const cancelClicked = ref(false)
const showHowToPay = ref(false)
const countdown = ref('00:00')
const error = ref<string | null>(null)
const qrCanvasRef = ref<HTMLCanvasElement | null>(null)

let countdownInterval: ReturnType<typeof setInterval> | null = null
let statusInterval: ReturnType<typeof setInterval> | null = null
let currentReferenceId: string | null = null
const amount = ref(0)
const tokens = ref(0)

// VA bank selector
const selectedBank = ref('VIRTUAL_ACCOUNT_BRI')
const banks = [
  { channel: 'VIRTUAL_ACCOUNT_BRI', label: 'BRI', active: true },
  { channel: 'VIRTUAL_ACCOUNT_BANK_PERMATA', label: 'Permata', active: true },
  { channel: 'VIRTUAL_ACCOUNT_BNI', label: 'BNI', active: false },
  { channel: 'VIRTUAL_ACCOUNT_MANDIRI', label: 'Mandiri', active: false },
]

const selectedPkg = computed(() => packages.find(p => p.id === selectedPackageId.value) || null)

function selectPackage(pkg: Package) {
  if (pkg.maintenance) return
  selectedPackageId.value = pkg.id
}

function close() {
  cleanup()
  selectedPackageId.value = null
  selectedPackage.value = null
  paymentData.value = null
  step.value = 'package'
  method.value = 'va'
  emit('close')
}

function cleanup() {
  if (countdownInterval) { clearInterval(countdownInterval); countdownInterval = null }
  if (statusInterval) { clearInterval(statusInterval); statusInterval = null }
}

function formatIDR(amountVal: number): string {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(amountVal)
}

function formatTokenShort(tokens: number): string {
  if (tokens >= 1000000) return (tokens / 1000000).toFixed(1).replace('.0', '') + 'M'
  if (tokens >= 1000) return (tokens / 1000).toFixed(1).replace('.0', '') + 'K'
  return tokens.toString()
}

function confirmMethod() {
  cancelClicked.value = false
  selectedPackage.value = packages.find(p => p.id === selectedPackageId.value) || null
  if (!selectedPackage.value) return
  amount.value = selectedPackage.value.price
  tokens.value = selectedPackage.value.tokens
  step.value = 'payment'
  generatePayment()
}

async function generatePayment() {
  if (!selectedPackage.value) return
  loading.value = true
  error.value = null
  paymentData.value = null
  paymentStatus.value = 'pending'

  try {
    const endpoint = method.value === 'va' ? '/api/payment/doku/generate-va' : '/api/payment/doku/generate'
    const payload: any = {
      amount: selectedPackage.value.price,
      tokens: selectedPackage.value.tokens
    }
    if (method.value === 'va') {
      payload.channel = selectedBank.value
    }
    const res = await api.post(endpoint, payload)
    const data = res.data
    paymentData.value = data
    if (data.trial && data.status === 'paid') {
      paymentStatus.value = 'paid'
      window.dispatchEvent(new CustomEvent('quota:refresh'))
      return
    }
    currentReferenceId = data.transaction_id || data.reference_no || null
    startStatusPolling(currentReferenceId)
    if (data.expires_at) {
      startCountdown(new Date(data.expires_at))
    }
    if (method.value === 'qris' && data.qr_string) {
      await nextTick()
      if (qrCanvasRef.value) {
        try {
          await QRCode.toCanvas(qrCanvasRef.value, data.qr_string, { width: 240, margin: 2, color: { dark: '#1a1a1a', light: '#ffffff' } })
        } catch { /* silent */ }
      }
    }
  } catch (e: any) {
    error.value = e.message
    paymentStatus.value = 'failed'
  } finally {
    loading.value = false
  }
}

function startCountdown(expiresAt: Date) {
  if (countdownInterval) clearInterval(countdownInterval)
  const update = () => {
    const diff = Math.max(0, Math.floor((expiresAt.getTime() - Date.now()) / 1000))
    const m = String(Math.floor(diff / 60)).padStart(2, '0')
    const s = String(diff % 60).padStart(2, '0')
    countdown.value = `${m}:${s}`
    if (diff === 0) {
      clearInterval(countdownInterval!)
      countdownInterval = null
      paymentStatus.value = 'expired'
    }
  }
  update()
  countdownInterval = setInterval(update, 1000)
}

function startStatusPolling(refId: string | null) {
  if (statusInterval) clearInterval(statusInterval)
  if (!refId) return
  const check = async () => {
    if (paymentStatus.value === 'paid' || paymentStatus.value === 'failed' || paymentStatus.value === 'cancelled') {
      clearInterval(statusInterval!)
      statusInterval = null
      return
    }
    try {
      const endpoint = method.value === 'va' ? '/api/payment/doku/query-va' : '/api/payment/doku/query'
      const res = await api.post(endpoint, { transaction_id: refId })
      const data = res.data
      if (data.status === 'paid') {
        paymentStatus.value = 'paid'
        window.dispatchEvent(new CustomEvent('quota:refresh'))
        if (statusInterval) { clearInterval(statusInterval); statusInterval = null }
      } else if (data.status === 'failed' || data.doku_status === '68') {
        paymentStatus.value = 'failed'
        if (statusInterval) { clearInterval(statusInterval); statusInterval = null }
      }
    } catch { /* retry next tick */ }
  }
  check()
  statusInterval = setInterval(check, 3000)
}

async function copyTransactionId() {
  if (!paymentData.value?.transaction_id) return
  await navigator.clipboard.writeText(paymentData.value.transaction_id)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

async function copyVANumber() {
  if (!paymentData.value?.va_number) return
  await navigator.clipboard.writeText(paymentData.value.va_number)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

function cancelPayment() {
  cancelClicked.value = true
  paymentStatus.value = 'cancelled'
  cleanup()
  // Call backend to void pending transaction
  voidCancelTransaction()
}

async function voidCancelTransaction() {
  if (currentReferenceId) {
    try {
      const endpoint = method.value === 'va' ? '/api/payment/doku/cancel-va' : '/api/payment/doku/cancel'
      await api.post(endpoint, { transaction_id: currentReferenceId })
    } catch { /* silent */ }
  }
  currentReferenceId = null
}

function resetPayment() {
  cancelClicked.value = false
  paymentData.value = null
  paymentStatus.value = 'pending'
  step.value = 'method'
  method.value = 'va'
  error.value = null
  currentReferenceId = null
}

watch(() => props.isOpen, (val) => {
  if (!val) {
    cleanup()
    selectedPackageId.value = null
    selectedPackage.value = null
    paymentData.value = null
    step.value = 'package'
    method.value = 'va'
    copied.value = false
    showHowToPay.value = false
    error.value = null
  }
})
</script>
