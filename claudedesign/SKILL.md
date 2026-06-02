---
name: paperfull-design
description: Use this skill to generate well-branded interfaces and assets for PaperFull (paperfull.app), an AI academic-paper generator, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the `README.md` file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## What's here
- `README.md` — product context, content fundamentals, visual foundations, iconography, and a file index. **Start here.**
- `colors_and_type.css` — all color + type tokens. Import it; don't reinvent the palette.
- `assets/` — brand logos and photographic imagery.
- `preview/` — small design-system cards (colors, type, spacing, components, brand).
- `ui_kits/marketing/` — landing + login recreation.
- `ui_kits/app/` — dashboard + paper editor + AI chat recreation (light & dark).

## Quick rules of thumb
- **Palette:** deep navy `#0b4088` primary, cream/ivory paper surfaces, cool blue-gray "ink" text, gold `#d9a718` sparingly, "ash" nautical-blue dark mode. Semantics: emerald success, amber/gold warning, red danger.
- **Type:** DM Sans (UI), Fraunces (serif headings), JetBrains Mono (numerics); Times New Roman for the rendered paper itself.
- **Shape language:** rounded-xl/2xl cards, hairline cream borders, soft warm shadows, `active:scale-95` press.
- **Icons:** emoji for tab/menu/status affordances; Heroicons-outline (2px) for functional SVG glyphs. No bespoke hand-drawn SVG.
- **Voice:** practical and encouraging; English structure with Indonesian microcopy is on-brand.
