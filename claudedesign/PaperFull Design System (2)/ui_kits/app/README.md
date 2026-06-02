# PaperFull — App UI Kit

High-fidelity recreation of the **authenticated product**: the paper dashboard and the split-pane paper editor with AI chat. Recreated from `frontend/src/views/DashboardPage.vue`, `PaperEditorPage.vue`, `AppHeader.vue`, and `components/chat/*`.

## Run it
Open `index.html`. Interactive flow:
- **Dashboard** — "My Papers" grid. **Copy** / **Delete** show toasts; **Open** or **＋ New Paper** enters the editor.
- **Editor** — sticky toolbar (DOCX · Undo · Redo · tabs · AI Chat) over a 50/50 split: the **Editor** pane (Title, Authors with drag handles, Abstract, Keywords, Sections, References — each an accent-bordered card) on the left and the **AI Chat** panel on the right. Type a message (or tap a suggestion chip like "Buat outline") → a fake streaming reply with a tool-call line.
- **Preview** tab — the IEEE-style paper rendered in **Times New Roman**, two-column, exactly as the product exports.
- **Theme** — open the user menu (top-right) → Light / Dark / System. Dark mode is the "ash" nautical-blue surface.

## Components (exported to `window`)
- `Header.jsx` — `AppHeader` + the shared `Icon` set (bell/send/export/stop as Heroicons-outline SVG). Token-quota meter, notification bell with badge, user menu + theme segmented control.
- `Dashboard.jsx` — `Dashboard` paper grid + empty state.
- `Chat.jsx` — `Chat` panel: message bubbles (user/ai + tool line), typing indicator, suggestion chips, composer.
- `Tabs.jsx` — `window.PFTabs`: the **Journal** (searchable template selector + template grid), **Literatur** (SLR runner + reference table with relevance stars), **Files** (Dokumen/Figures sub-tabs, file list + extracted-text preview), and **Data** (source → table → bar chart) tabs.
- `Tools.jsx` — `window.PFTools`: the **Tools** suite (see below).
- `Editor.jsx` — `Editor` shell: toolbar, tabs, `EditorPane`, `PreviewPane`.
- `styles.css` — full light + dark theme via tokens from `../../colors_and_type.css`.

## 🛠 Tools suite (designed extension)
Added at the user's request to round out a complete paper-generator workflow (the product already advertises "anti-AI detection"). Eight tools, each opening a two-pane input→output workspace with in-brand controls:
- **Paraphrase** (tone: Standard/Formal/Fluent/Concise) · **Translator** (EN→ID +20 languages) · **Humanizer** (Light/Standard/Aggressive) · **Summarize** (TL;DR/Abstract/Bullets)
- **AI Detector** & **Plagiarism Check** — conic-gradient score gauges
- **Grammar & Style** — inline add/delete diff highlighting
- **Citation Generator** — DOI/URL/title → formatted reference

These are *new designs in the PaperFull style*, not recreations of existing screens — flagged as such so they're easy to review.

## Notes on fidelity
- Copy is the real EN/ID blend: English structure ("My Papers", tabs) with Indonesian microcopy ("Ketik pesan…", "Jalankan SLR", suggestion chips, AI replies).
- The Journal / Literatur / Files / Data tabs are now full recreations from their Vue sources.
- Interactions are cosmetic mocks (no backend, no real DOCX export, no auto-save persistence).
- `toRoman` is defined globally in `index.html` so all Babel scopes share it.
