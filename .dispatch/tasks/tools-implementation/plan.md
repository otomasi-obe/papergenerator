# Implement AI Writing Tools Suite (8 tools from claudedesign)

Convert the React JSX `Tools.jsx` from `/home/sirobo/papergenerator/PaperRiset/claudedesign/PaperFull Design System (2)/ui_kits/app/Tools.jsx` into Vue 3 components for the frontend at `/home/sirobo/papergenerator/frontend/`.

The design MUST match exactly: same colors, same layout, same icons, same interactions. Use Tailwind CSS classes mapped to the existing design tokens in `tailwind.config.js`.

## Reference Files (READ ALL before starting)
- `/home/sirobo/papergenerator/PaperRiset/claudedesign/PaperFull Design System (2)/ui_kits/app/Tools.jsx` — source React component
- `/home/sirobo/papergenerator/PaperRiset/claudedesign/PaperFull Design System (2)/ui_kits/app/styles.css` — CSS styles to replicate
- `/home/sirobo/papergenerator/PaperRiset/claudedesign/colors_and_type.css` — design tokens
- `/home/sirobo/papergenerator/frontend/tailwind.config.js` — Tailwind config (use these color names)
- `/home/sirobo/papergenerator/frontend/src/views/PaperEditorPage.vue` — where to add the Tools tab
- `/home/sirobo/papergenerator/frontend/src/stores/paper.ts` — paper store for API calls
- `/home/sirobo/papergenerator/frontend/src/api/index.ts` — API client

## 8 Tools to Implement
1. **Paraphrase** (✍️) — Rewrite passages. Options: Standard/Formal/Fluent/Concise
2. **Translator** (🌐) — Translate between languages. Options: Indonesian/Spanish/German/Chinese/Arabic
3. **Humanizer** (🧬) — Rework AI-sounding prose. Options: Light/Standard/Aggressive
4. **AI Detector** (🔍) — Estimate AI-likelihood. Shows gauge ring with percentage
5. **Plagiarism Check** (📋) — Scan for similarity. Shows gauge ring with percentage
6. **Grammar & Style** (✓) — Fix grammar inline with diff highlighting (add/delete)
7. **Summarize** (📝) — Condense text. Options: TL;DR/Abstract/Bullets
8. **Citation Generator** (📑) — Generate formatted reference from DOI/URL/title

## Implementation Plan

### Step 1: Create Tools store (`src/stores/tools.ts`)
- [ ] Create Pinia store for tools state
- [ ] State: activeTool, inputText, outputText, isProcessing, selectedOption, toolResults
- [ ] Actions: processTool(toolId, input, option), resetTool()
- [ ] API integration: POST to `/api/tools/{toolId}` with SSE streaming for real-time results
- [ ] Handle all 8 tool types with their specific options

### Step 2: Create ToolsTab component (`src/components/ToolsTab.vue`)
- [ ] Grid view showing all 8 tool cards (matching claudedesign exactly)
- [ ] Each card: icon (colored circle), title, description
- [ ] Click card → open ToolWorkspace for that tool
- [ ] Use Tailwind classes: `bg-white dark:bg-ash-800`, `rounded-2xl`, `border-cream-300 dark:border-ash-700`
- [ ] Card hover: `hover:border-navy-500 dark:hover:border-cream-400`
- [ ] Icon circle: 38x38px, rounded-lg, colored background
- [ ] Grid: `grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3`

### Step 3: Create ToolWorkspace component (`src/components/ToolWorkspace.vue`)
- [ ] Two-pane layout: Input (left) + Output (right)
- [ ] Back button "← All tools" at top
- [ ] Tool header with icon + title + description
- [ ] Tool-specific controls (chip toggles, select dropdowns)
- [ ] Run/Scan button (navy-700 bg, cream-50 text)
- [ ] Input textarea with word count
- [ ] Output area with typing animation (3 dots)
- [ ] Gauge component for AI Detector & Plagiarism Check (conic-gradient ring)
- [ ] Diff highlighting for Grammar & Style (green add, red delete with strikethrough)
- [ ] Copy button in output header

### Step 4: Create Gauge component (`src/components/ToolGauge.vue`)
- [ ] Conic-gradient ring showing percentage
- [ ] Inner circle with percentage text
- [ ] Title and description below
- [ ] Colors: green for low risk, gold for medium, red for high

### Step 5: Integrate Tools tab into PaperEditorPage
- [ ] Add 'tools' to the `leftTabs` array: `{ id: 'tools', label: '🛠 Tools' }`
- [ ] Add Tools tab panel in the template
- [ ] Add keyboard shortcut Ctrl+6 for Tools tab
- [ ] Ensure Tools tab appears between Editor and Journal tabs

### Step 6: Add API endpoints to backend (if not exists)
- [ ] Check if `/api/tools/{toolId}` endpoints exist
- [ ] If not, create them in the backend
- [ ] Each tool should accept: { text, option } and return streaming response

### Step 7: Style matching — pixel-perfect to claudedesign
- [ ] Use exact same spacing, colors, typography
- [ ] Light mode: cream-50 bg, white cards, navy-700 primary
- [ ] Dark mode: ash-850 bg, ash-800 cards, cream-200 primary
- [ ] Font: DM Sans for UI, Fraunces for headings
- [ ] Border radius: 12px (lg) for cards, 6px (sm) for inputs
- [ ] Shadows: shadow-[0_1px_0_rgba(15,14,11,0.04),0_1px_3px_rgba(15,14,11,0.06)]

### Step 8: Test all 8 tools
- [ ] Verify each tool opens correctly
- [ ] Verify options/chips work
- [ ] Verify Run/Scan button triggers processing
- [ ] Verify output displays correctly
- [ ] Verify gauge renders for Detector/Plagiarism
- [ ] Verify diff highlighting for Grammar
- [ ] Verify Copy button works
- [ ] Verify back navigation works

## Critical Design Details (MUST MATCH)
- Tool card icon circle: `w-[38px] h-[38px] rounded-lg flex items-center justify-center text-lg mb-3`
- Tool card: `bg-white dark:bg-ash-800 rounded-2xl border border-cream-300 dark:border-ash-700 p-4 cursor-pointer hover:border-navy-500 dark:hover:border-cream-400 transition-all`
- Tool card hover scale: `active:scale-[0.98]`
- Input/Output panes: `bg-white dark:bg-ash-800 rounded-xl border border-cream-300 dark:border-ash-700`
- IO header: `flex justify-between px-3.5 py-2.5 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-700 text-xs font-semibold`
- Textarea: `w-full border-0 outline-0 resize-none bg-transparent px-3.5 py-3 text-sm leading-relaxed min-h-[220px]`
- Chip toggle: `inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5`
- Chip button: `text-xs px-3 py-1.5 rounded text-ink-500 dark:text-ink-300 font-medium`
- Chip active: `bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-700`
- Gauge ring: conic-gradient, 64x64px, inner 46x46px circle
- Gauge colors: green (#2f9d6e) for low, gold (#d9a718) for medium, red (#c43655) for high
- Diff add: `bg-emerald-200/30 dark:bg-emerald-800/30 rounded px-0.5`
- Diff delete: `bg-red-200/30 dark:bg-red-800/30 line-through rounded px-0.5`

## Files to Create/Modify
- CREATE: `src/stores/tools.ts`
- CREATE: `src/components/ToolsTab.vue`
- CREATE: `src/components/ToolWorkspace.vue`
- CREATE: `src/components/ToolGauge.vue`
- MODIFY: `src/views/PaperEditorPage.vue` (add Tools tab)
- MODIFY: `src/router/index.ts` (if needed for tools route)

## Output
Write a summary of all changes made to `.dispatch/tasks/tools-implementation/output.md`
