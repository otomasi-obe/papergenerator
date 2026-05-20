/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      // Font stacks tuned to feel like claude.ai's typography:
      // - sans: system-ui first so it picks San Francisco / Segoe UI cleanly
      // - serif: warm "old style" for headings (replacement for Tiempos Headline)
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        serif: ['"Iowan Old Style"', '"Palatino Linotype"', '"Book Antiqua"', 'Palatino', 'Georgia', 'serif'],
      },
      colors: {
        // Neutral ivory/anthracite tokens (workspace surface — replaces cream-brown).
        // Calibrated to claude.ai's measured tokens:
        //   light body  rgb(248,248,246) = #f8f8f6, text rgb(18,18,18) = #121212
        //   dark  body  rgb(31,31,30)    = #1f1f1e, text rgb(248,248,246) = #f8f8f6
        ivory: {
          50:  '#ffffff',  /* card surface (light) */
          100: '#f8f8f6',  /* body bg (light) */
          200: '#f3f2ee',  /* hover */
          300: '#cfcec5',  /* border soft — tighter contrast for crisp boxes */
          400: '#9e9d92',  /* border strong */
          500: '#6b6a62',  /* muted text */
          600: '#4a4945',
          700: '#2d2c29',
          800: '#1f1f1e',
          900: '#121212',
        },
        anthracite: {
          50:  '#f8f8f6',  /* dark text primary */
          100: '#c3c2b7',  /* dark text secondary */
          200: '#97958c',  /* dark text muted */
          300: '#75726a',
          400: '#4c4a44',
          500: '#3a3935',  /* hover */
          600: '#383836',  /* elevated2 */
          700: '#2c2c2a',  /* surface (claude.ai exact) */
          800: '#1f1f1e',  /* body (claude.ai exact) */
          900: '#121211',
        },
        // Legacy aliases re-mapped to the new ivory/anthracite ramp so older
        // class names still produce the new look without a global rename.
        // (cream-* used for light surfaces / brown-* used for text and accents
        // / ash-* used for dark surfaces.)
        cream: {
          50: '#ffffff', 100: '#f8f8f6', 200: '#f3f2ee', 300: '#cfcec5',
          400: '#9e9d92', 500: '#6b6a62', 600: '#4a4945', 700: '#2d2c29',
          800: '#1f1f1e', 900: '#121212',
        },
        brown: {
          50: '#f3f2ee', 100: '#cfcec5', 200: '#9e9d92', 300: '#6b6a62',
          400: '#4a4945', 500: '#2d2c29', 600: '#1f1f1e', 700: '#1f1f1e',
          800: '#121212', 900: '#0a0a0a',
        },
        ash: {
          50: '#f8f8f6', 100: '#c3c2b7', 200: '#97958c', 300: '#75726a',
          400: '#4c4a44', 500: '#3a3935', 600: '#383836', 700: '#2c2c2a',
          800: '#1f1f1e', 850: '#1a1a19', 900: '#121211',
        },
        ink: {
          50: '#f8f8f6', 100: '#e2e1da', 200: '#c3c2b7', 300: '#97958c',
          400: '#56544c', 500: '#36352f', 600: '#2a2826', 700: '#1c1b18',
          800: '#121212', 900: '#0a0a0a',
        },
      },
    },
  },
  plugins: [],
}
