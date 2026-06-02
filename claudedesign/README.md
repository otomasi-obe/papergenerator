# PaperFull — Design System

**PaperFull** (paperfull.app · also served at paper.otomasi.app) is an **AI academic-paper generator**. From a single prompt it drafts a complete, submission-ready paper — 4000+ words across all IMRaD sections (Introduction, Methods, Results, Discussion) — with academic prose, LaTeX formulas, AI-generated figures, formatted tables, 20+ citations, and DOCX export. It targets **IEEE, international (Scopus/WoS), Indonesian SINTA-indexed journals, and conferences**, and is "anti-AI-detection" oriented. It's a private project by **ZOO Company**, with strong roots in the Indonesian academic / engineering-automation community (the `otomasi-obe` / `sistem-otomasi` GitHub orgs).

The product is bilingual in practice: **UI labels are English, but inline microcopy, tooltips, and helper text are frequently Indonesian** (e.g. "Ketik pesan…", "Terima semua", "Sedang generate paper di chat lain"). Treat this EN/ID blend as a brand characteristic, not an inconsistency.

---

## Two surfaces / products

1. **Marketing site** — `LandingPage` + `LoginPage`. A dark, navy-gradient promotional experience: hero with editor screenshot, trust strip, feature grid, publication-type & domain grids, CTA. Emoji are used as feature icons here.
2. **The app** — the authenticated tool:
   - **Dashboard** (`/dashboard`) — "My Papers" grid of paper cards (open / copy / delete).
   - **Paper Editor** (`/editor/:paperId`) — the core workspace: a **split layout** with a tabbed editor pane on the left (Editor · Journal · Literatur · Files · Data · Preview) and an **AI chat panel** on the right. Toolbar with DOCX export, undo/redo, save status, pending-changes badge.
   - **Admin** (`/admin`) — token-usage analytics per user.
   - Supporting: Google + email/password auth (Cloudflare Turnstile on register), light/dark/system theme switcher, token-quota meter, job-completion notification bell.

---

## Sources (the reader may or may not have access — stored for reference)

- **Frontend codebase** (source of truth): mounted at `frontend/` — Vue 3 + Vite + Pinia + Tailwind CSS 3 SPA. Routes in `src/views/`, components in `src/components/`, theme in `tailwind.config.js` + `src/style.css`.
- **Monorepo:** https://github.com/otomasi-obe/papergenerator (branch `v1`) — Flask/SQLAlchemy/SQLite backend (port 8001) + the same Vue frontend (port 8000). Paper templates: ACM, APA, IEEE, Elsevier, MDPI, Springer, Vancouver. *Explore this repo to build more faithfully against the real product.*
- Related orgs worth browsing: `otomasi-obe`, `sistem-otomasi`, `otomasi-iot` (the broader automation/IoT product family this brand sits within).

Production hosts referenced in code: `https://paperfull.app`, `https://paper.otomasi.app`.

---

## CONTENT FUNDAMENTALS

**Voice.** Practical, encouraging, builder-to-researcher. The marketing voice makes confident capability claims ("Generate complete papers with 4000+ words from a single prompt"); the in-app voice is terse, instructional, and reassuring during long operations ("masih bekerja — paper besar bisa sampai 15 menit").

**Person.** Marketing addresses **you** ("Ready to write your paper?", "Join researchers using AI…"). In-app Indonesian copy slips into the informal **kamu** ("Kamu bisa lakukan hal lain dulu…"). First-person plural ("our AI") only in marketing.

**Language mix.** English for nav, page titles, buttons, and structural labels (Papers, New Paper, Export DOCX, Sign In). **Indonesian for conversational/transient microcopy**: placeholders ("Ketik pesan…"), confirmations ("Hapus Section?", "dan semua kontennya akan dihapus permanen"), banners ("Sedang generate paper di chat lain"), suggestion chips ("💡 Saran"). Some tabs are mixed: `📖 Literatur`, `📝 Editor`.

**Casing.** Title Case for nav items and primary buttons (New Paper, Export DOCX). Sentence case for body, helper text, and dialog prose. **UPPERCASE with wide tracking** for eyebrows / trust-strip labels ("TRUSTED ACROSS DISCIPLINES · IEEE · SINTA…") and section labels ("SECTION I", author/keyword field labels).

**Numbers & stats.** Marketing leans on big round proof points: **100+ domain topics, 20+ citation styles, 4000+ words, DOCX**. Token usage is shown compactly with `k`/`M` suffixes in tabular-nums mono (`1.2k/50.0k`). Relative time is humanized ("just now", "3h ago", "2d ago").

**Tone in errors / waits.** Calm and non-blocking. Failures are short and actionable ("Save failed" → click to retry; "Copy failed — try again"). Long AI jobs get patient, explanatory banners rather than spinners-only.

**Emoji.** Used deliberately, not decoratively-everywhere:
- Marketing feature cards each lead with one emoji (⚡ 🌍 🧮 🖼️ 📊 🎯 🏆 🎤 🗂️ 📐 🔒 📈).
- App tabs & menu items use a small consistent set (📝 Editor, 📚 Journal, 📖 Literatur, 📂 Files, 📊 Data, 👁 Preview, 💬 AI Chat, 📄 DOCX, 💡 Saran, 📤 📋 📁 in the attach menu, ☀️ 🌙 🖥️ in the theme switcher, 🚪 Sign Out).
- Status/inline: ⚠️ ⏳ ✓ ✕ ↻ ⠿ (drag handle). Keep emoji `aria-hidden` as the code does.

**Vibe.** "Scholarly but modern" — a warm, paper-and-ink study (think a desk with a laptop, leather notebook, and stacked hardback journals) crossed with a clean SaaS tool.

---

## VISUAL FOUNDATIONS

**Core metaphor: paper & ink.** Warm parchment/ivory surfaces, deep-navy ink, gold for "premium/accepted". The logo is a navy paper-sheet glyph (a stylized sheet with a stem-and-dot forming a lowercase "p"/person) on ivory.

**Color.**
- **Primary:** deep **navy** `#0b4088` (CTA buttons, active headings, brand). A brighter **vivid sea-blue** `#1265c8` is the interactive/link blue. *Note: in code the `brown-*` scale is remapped to navy, so `brown-700` renders navy.*
- **Surfaces:** **cream** `#fffdf8` app background, **white** cards, **ivory** `#fbf8f1`/`#f4edde` for sunken/AI-message wells. Everything reads like aged paper.
- **Text:** cool blue-gray **ink** — `#0c1c3c` headings, `#214070` body, `#3e70a8` muted.
- **Accent:** **gold** `#d9a718`/`#c28d0d` — sparingly, for premium/accepted badges, stars, decorative rules. A secondary **editorial teal** `#238f7f` drives focus rings, the back-to-top FAB, and editable-content focus.
- **Semantics:** emerald `#2f9d6e` success/saved, amber/gold `#d9a718` warning/pending/under-review, red `#c43655` danger/delete/references.
- **Dark mode** is **"ash" — nautical blue-dark**, not neutral gray: shell `#0b1f3e`, header/sidebar `#102c55`, card `#163d71`. In dark mode the **primary button inverts to cream** (`#f1e8d8`) with dark text. Some editor cards use warm **anthracite** darks.

**Backgrounds.** Light mode body carries two faint radial gradients (a soft teal glow top-left, a warm border-tint bottom-right) — subtle texture, never loud. Marketing uses full **navy gradients** (`from-navy-900 via-navy-800 to-stone-900`) and **photographic** section backgrounds (warm, shallow-DOF study/desk imagery) dimmed under dark overlays. No repeating patterns or noise textures; imagery is warm and naturalistic with selective teal-cyan UI glows composited in.

**Type.** Intended stack is **DM Sans** (UI), **Fraunces** (warm old-style serif headings), **JetBrains Mono** (numerics/code). ⚠️ **In the live build these Google fonts are configured but never imported**, so production currently falls back to `system-ui` for UI and a Georgia-class serif for `h1/h2`. The **paper preview is always Times New Roman** (a deliberate, theme-independent choice — the export must look like the export). This design system loads the intended fonts so specimens are accurate; see the font caveat below.

**Spacing.** 4 / 8 / 12 / 16 / 24 / 40 / 64 px scale. Generous page padding (`px-4 lg:px-8`, `py-6/8`). Cards use 20px (`p-5`) interior padding.

**Radii.** Soft and friendly: inputs/small buttons `rounded-xl` (12px), cards `rounded-2xl` (16px), CTA panels `rounded-3xl` (24px), pills/chips fully rounded. Drag handles and tiny controls `rounded` (6px).

**Cards.** White (light) / ash-800 (dark), `rounded-2xl`, hairline cream-300 border, very soft shadow (`0 1px 0 …, 0 1px 3px …`); hover lifts shadow and warms the border toward navy. Editor sub-cards use a **colored left-accent border** (`border-l-4`) to type content blocks — navy-l for metadata, cream for sections, red for references. (This is intentional product UI, not generic AI-card styling.)

**Borders & dividers.** Hairline `cream-300` (`#dfcfb5`) light / `ash-700` dark. Inputs get a 1px cream-300 border that deepens to navy on focus, plus a soft ring. The chat composer uses a heavier `border-2` that turns navy + 4px ring on focus-within.

**Shadows / elevation.** Restrained. Cards: barely-there. Menus/dropdowns/toasts: `shadow-lg`. Hero image gets a dramatic `0 30px 60px -15px rgba(0,0,0,.6)`. No neumorphism, no glow except the marketing UI accents.

**Transparency & blur.** Sticky header/toolbar use `bg-…/95` + `backdrop-blur`. Login card and marketing surfaces use translucent `white/5` over the navy gradient. Blur is reserved for sticky chrome and glass-on-photo marketing panels.

**Buttons & states.**
- Primary: navy-700 bg, white text, `rounded-xl`, soft shadow → hover navy-800; **press = `active:scale-95`** (a consistent, signature press shrink across the app); focus = 2px teal outline + offset. Dark mode primary flips to cream bg / dark text.
- Secondary: cream-200 → cream-300 hover (ash in dark). Ghost: transparent → cream-100 hover. Danger: red-600 → red-700. Outline: 2px navy border, fills navy on hover.
- Links/nav: hover warms to navy / lightens to cream; active nav pill gets a cream-300/ash-600 filled background.

**Hover / press conventions.** Hover = subtle **background fill** (cream-100/200) or border-warming, not color inversion. Press = **scale-95 shrink** nearly everywhere. Transitions are short (`150–250ms ease`), color/transform only — no bounces, no springy easing. `prefers-reduced-motion` is fully honored (animations clamped to ~0).

**Animation.** Minimal and functional: fade/slide-up toasts (`translateY(20px)→0`, 0.3s), spinners for loading, a pulsing dot on "live"/editing labels, smooth scroll. No decorative looping motion.

**Layout rules.** Sticky top header (`z-40`) + sticky editor toolbar (`z-30`) that wrap gracefully on small widths. Editor is a 50/50 split (tab pane ‖ chat) that collapses to full-width chat when no tab is active. Content max-widths: marketing `max-w-6xl`, paper preview `max-w-4xl` centered. Hit targets are explicitly `min-h-[44px]` for accessibility.

---

## ICONOGRAPHY

PaperFull has **no installed icon font and no SVG icon set in the repo**. Its icon language is two-track:

1. **Emoji** carry most "iconographic" meaning — in marketing feature cards and across app tabs, menus, and status microcopy (see the Emoji list under Content Fundamentals). They are always wrapped `aria-hidden="true"` with a real text label beside them. This is core to the brand's approachable, low-chrome feel.
2. **Inline hand-written SVGs**, drawn in the **Heroicons "outline" idiom** — 24×24 viewBox, `fill="none"`, `stroke="currentColor"`, `stroke-width="2"`, round caps/joins. Used for the few truly functional glyphs: notification **bell**, **send** paper-airplane, **export/download**, **stop** (rounded square), the multicolor **Google "G"** on the login button. They inherit text color via `currentColor`.
3. **Unicode glyphs as UI icons:** `⠿` braille drag-handle (reorder), `↑ ↓ ↶ ↷ ↻` (move/undo/redo/retry), `← →` (back/nav), `▾ ▸ �."` (disclosure), `＋ ✕ ✓` (add/close/confirm), `∞` (unlimited quota), `↑` (back-to-top).

**Guidance for new work:** match this exactly. Prefer the existing emoji for tab/menu/status affordances; for new functional glyphs use **Heroicons (outline, 2px stroke)** from CDN — it is the closest match to the in-repo SVGs. Do **not** introduce a heavy filled icon set, and do not hand-draw bespoke SVG illustrations. This design system links Heroicons-style markup in the UI kits and documents the substitution.

> Iconography substitution flagged: there is no first-party icon set to copy, so new functional icons should use **Heroicons outline** (CDN), which matches the codebase's inline SVG style. Brand logos and photographic assets *were* copied from the codebase into `assets/`.

---

## Font caveat (action requested)

The brand's intended fonts — **DM Sans, Fraunces, JetBrains Mono** — are declared in `tailwind.config.js` but **not imported by the live app**, which therefore falls back to system fonts. This design system loads the intended trio from **Google Fonts** so specimens render correctly. If the team has licensed/self-hosted versions (or wants the design system to mirror the current system-font reality instead), send them and I'll swap `fonts/` accordingly.

---

## Index / manifest

Root files:
- **`README.md`** — this document.
- **`colors_and_type.css`** — all color + type tokens (raw scales, semantic light/dark tokens, type classes). Import this into any artifact.
- **`SKILL.md`** — Agent-Skill front-matter wrapper so this folder works as a downloadable Claude skill.
- **`assets/`** — brand logos & photographic imagery copied from the codebase (`logo.png`, `logo-with-text.png`, `landing-page.jpg`, `feature-illustration.jpg`, `trust-strip-bg.jpg`, `og-image.jpg`, `favicon-32x32.png`).
- **`preview/`** — Design-System-tab cards (colors, type, spacing/radii/shadow, components, brand). One concept per card.

UI kits (high-fidelity, interactive recreations):
- **`ui_kits/marketing/`** — the public landing + login experience.
- **`ui_kits/app/`** — the authenticated tool: dashboard, paper editor (tabbed pane + AI chat), header chrome.

Each UI kit has its own `README.md`, an `index.html` demo, and small reusable `.jsx` components.

> No slide template was provided in the source, so `slides/` is intentionally omitted.
