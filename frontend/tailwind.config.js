/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      // Font stacks — editorial & scholarly feel
      // DM Sans: clean UI copy | Fraunces: warm old-style serif for headings
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        serif: ['"Fraunces"', '"Playfair Display"', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      colors: {
        // ─────────────────────────────────────────────────────────────────
        // PRIMARY: Navy — Biru Laut
        // Digunakan sebagai warna brand utama, tombol primer, headings aktif,
        // sidebar background (dark mode), dan border aktif.
        //   navy-50  → surface / hover background ringan
        //   navy-400 → interactive element (link, icon button)
        //   navy-600 → CTA button background (light mode)
        //   navy-800 → text heading dark, sidebar bg dark mode
        //   navy-950 → app shell bg dark mode
        // ─────────────────────────────────────────────────────────────────
        navy: {
          50: '#ebf3ff',
          100: '#d0e4fb',
          200: '#a1c9f6',
          300: '#64a6ed',
          400: '#2e82e0',
          500: '#1265c8',  // vivid sea blue
          600: '#0e51a6',
          700: '#0b4088',  // deep navy — text heading, icon
          800: '#082f6a',
          900: '#051d49',
          950: '#020d2a',  // midnight ocean — dark mode base
        },

        // ─────────────────────────────────────────────────────────────────
        // ACCENT: Gold — Emas Antik
        // Digunakan sebagai highlight, badge "published/accepted", rating bintang,
        // garis dekoratif, dan pembatas section premium.
        //   gold-100 → background badge ringan
        //   gold-400 → icon highlight, star rating, border dekorasi
        //   gold-500 → teks label premium
        //   gold-700 → teks/icon pada surface terang
        // ─────────────────────────────────────────────────────────────────
        gold: {
          50: '#fefaec',
          100: '#faf0c6',
          200: '#f5de87',
          300: '#ecc440',
          400: '#d9a718',  // bright antique gold — icon, star, border
          500: '#c28d0d',  // classic gold — label premium
          600: '#a37210',  // deeper gold
          700: '#845b0d',  // amber-gold — text on light bg
          800: '#654208',
          900: '#452c04',
          950: '#2a1902',
        },

        // ─────────────────────────────────────────────────────────────────
        // SURFACE: Ivory — Kertas Tua
        // Background utama light mode. Evokes "physical paper" feel.
        //   ivory-50/100 → page background, card background
        //   ivory-200/300 → border halus, divider
        //   ivory-400/500 → caption text, placeholder
        // ─────────────────────────────────────────────────────────────────
        ivory: {
          50: '#f8f5ef',
          100: '#f2ece1',
          200: '#e8e0d0',
          300: '#c4a87a',
          400: '#a68a5c',
          500: '#a38560',
          600: '#806548',
          700: '#5e4a35',
          800: '#3b2e22',
          900: '#201811',
        },

        // ─────────────────────────────────────────────────────────────────
        // TEXT: Anthracite — Tinta Pekat
        // Body text, label, metadata. Lebih hangat dari pure black.
        //   anthracite-700/800/900 → body text, headings
        //   anthracite-400/500 → secondary text, metadata
        //   anthracite-100/200 → text on dark (dark mode)
        // ─────────────────────────────────────────────────────────────────
        anthracite: {
          50: '#f5f3ee',
          100: '#d7d0c4',
          200: '#b5ab9c',
          300: '#8d8273',
          400: '#675e55',
          500: '#474139',
          600: '#31343a',
          700: '#24282e',
          800: '#181d22',
          900: '#101419',
        },

        // ─────────────────────────────────────────────────────────────────
        // SEMANTIC ACCENT — Updated untuk skema Navy + Gold
        // ─────────────────────────────────────────────────────────────────
        accent: {
          primary: '#1265c8',  // navy-500 — CTA, link, pill aktif
          secondary: '#c28d0d',  // gold-500 — highlight, badge premium
          success: '#2f9d6e',  // teal — paper accepted / doi verified
          warning: '#d9a718',  // gold-400 — under review / preprint
          danger: '#c43655',  // merah — retracted / error
        },

        // ─────────────────────────────────────────────────────────────────
        // ACADEMIC CONTEXT COLORS
        // Petakan status/tipe dokumen ke warna semantik
        // ─────────────────────────────────────────────────────────────────
        academic: {
          journal: '#0b4088',  // navy-700 — jurnal resmi, peer-reviewed
          conference: '#1265c8',  // navy-500 — paper konferensi, aktif
          thesis: '#c28d0d',  // gold-500 — disertasi / tesis (distingsi)
          preprint: '#2e82e0',  // navy-400 — preprint, in-review
          book: '#084263',  // navy tua kebiruan — monografi
        },

        // ─────────────────────────────────────────────────────────────────
        // UI CHROME: Ink — Cool Blue-Gray
        // Border, divider, skeleton loader, icon muted.
        //   ink-100/200 → border halus, surface tersier
        //   ink-400/500 → icon muted, label sekunder
        //   ink-800/900 → dark mode chrome
        // ─────────────────────────────────────────────────────────────────
        ink: {
          50: '#f0ebe2',
          100: '#d5ccb8',
          200: '#b5a78e',
          300: '#8d7e65',
          400: '#6b5e48',
          500: '#4a4035',
          600: '#382f24',
          700: '#1a1610',
          800: '#0f0d09',
          900: '#0c0a07',
        },

        // ─────────────────────────────────────────────────────────────────
        // SECONDARY SURFACE: Cream — Kertas Sekunder
        // Digunakan untuk sidebar, panel, card sekunder di light mode.
        // ─────────────────────────────────────────────────────────────────
        cream: {
          50: '#f8f5ef',
          100: '#f2ece1',
          200: '#e8e0d0',
          300: '#c4a87a',
          400: '#a68a5c',
          500: '#9f7d54',
          600: '#806044',
          700: '#624933',
          800: '#463323',
          900: '#281c13',
        },

        // ─────────────────────────────────────────────────────────────────
        // DARK MODE SURFACES: Ash — Nautical Blue-Dark
        // Dark mode base. Bernuansa biru laut gelap, bukan abu netral.
        //   ash-900/950 → app shell bg dark mode
        //   ash-800/850 → sidebar bg dark mode
        //   ash-700 → card bg dark mode
        //   ash-500/600 → border dark mode
        // ─────────────────────────────────────────────────────────────────
        ash: {
          50: '#ecf3f9',
          100: '#d4e4f4',
          200: '#a8c9e8',
          300: '#74a8d8',
          400: '#4787c4',
          500: '#2969ac',
          600: '#1e518e',
          700: '#163d71',
          800: '#102c55',
          850: '#0b1f3e',
          900: '#07122a',
        },

        // ─────────────────────────────────────────────────────────────────
        // BACKWARD COMPAT: 'brown' diremap ke navy
        // Jika ada komponen lama yang menggunakan 'brown-*', tetap berfungsi.
        // ─────────────────────────────────────────────────────────────────
        brown: {
          50: '#ebf3ff',
          100: '#d0e4fb',
          200: '#a1c9f6',
          300: '#64a6ed',
          400: '#2e82e0',
          500: '#1265c8',
          600: '#0e51a6',
          700: '#0b4088',
          800: '#082f6a',
          900: '#051d49',
        },
      },
    },
  },
  plugins: [],
}