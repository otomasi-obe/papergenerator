# UI Color Fix Plan

## Issues Identified

### 1. PreviewTab.vue - Potential text visibility issue
**Line 36:** `class="paper-preview border rounded-lg bg-white p-8 max-w-4xl mx-auto shadow-sm"`

**Problem:** 
- Uses `bg-white` inline class
- Relies on `.paper-preview` CSS class for text color
- In dark mode, if parent has light text, this could cause visibility issues

**Fix:** Add explicit text color to ensure visibility
```vue
class="paper-preview border rounded-lg bg-white text-gray-900 p-8 max-w-4xl mx-auto shadow-sm"
```

### 2. FilesTab.vue - PDF iframe
**Line 110:** `class="w-full h-full min-h-[60vh] border-0 bg-white"`

**Status:** Intentional - PDFs are always rendered on white background
**Action:** No fix needed (by design)

### 3. Missing explicit text colors
Several components use background colors without explicit text colors, relying on inheritance. This can cause issues if parent text color doesn't match.

## Fixes to Apply

### Fix 1: PreviewTab.vue - Add explicit text color
Ensure paper preview always has dark text on white background.

### Fix 2: Verify CSS variables are properly defined
Check that all CSS variables used in components are defined in both light and dark modes.

### Fix 3: Add defensive text colors
Add explicit text colors to components that set backgrounds but don't set text colors.
