# PaperFull — Marketing UI Kit

High-fidelity recreation of the **public marketing surface**: the landing page and the login / register screen. Recreated from `frontend/src/views/LandingPage.vue` and `LoginPage.vue`.

## Run it
Open `index.html`. It's an interactive click-through:
- **Landing** → hero, trust strip, feature grid, supported publication types, CTA, footer.
- Click **Sign In** / **Get Started** → the **Login** screen (toggle to Register, Google button).
- "Sign in" / "Continue with Google" → a success toast linking to the **app kit**.

## Components
- `Landing.jsx` — full marketing page. Internal data arrays (`FEATURES`, `PUB_TYPES`) drive the emoji feature/venue cards exactly as in the Vue source.
- `Login.jsx` — auth card with email/password form, Google OAuth button (`GoogleG` inline SVG), and a register/login toggle.
- `styles.css` — the navy-gradient promo surface, cream CTA buttons, glass login card.

## Notes on fidelity
- The shell is the real `from-navy-900 via-navy-800 to-stone-900` gradient with cream text.
- Marketing uses **emoji as feature icons** (⚡ 🌍 🧮 🖼️ 📊 🎯 · 📚 🌐 🏆 🎤) — faithful to production.
- The hero headline highlights "Journal" in cream. ⚠️ The original used a `background-clip:text` gradient here; that rule miscomputes line-box height in Blink and collapses the headline, so this kit uses a solid cream highlight instead (same visual intent, no overlap bug).
- Images are the real exported assets in `../../assets/` (logo, hero, feature illustration, trust strip).
- Tokens come from `../../colors_and_type.css`.
