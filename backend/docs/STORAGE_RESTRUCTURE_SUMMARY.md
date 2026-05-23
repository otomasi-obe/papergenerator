# Backend Storage Restructure - Summary

## Date: 2026-05-23

## Overview
Restructured the backend file storage system to organize files by user and paper ID, while maintaining backward compatibility with the existing SQL database schema.

## New Directory Structure

```
backend/data/
  <username>/
    <paper_id>/
      chat/
        DDMMYY-HHMM-send.json    # e.g., 260523-1135-send.json
        DDMMYY-HHMM-recv.json    # e.g., 260523-1135-recv.json
      image/
        <generated images and uploaded images>
      files/
        <uploaded files - maintained for compatibility>
      <paper_title>.json         # Editor JSON
      <paper_title>-SLR.json     # SLR JSON (when available)
      <paper_title>.docx         # DOCX output
```

## Files Created

### 1. `backend/storage_helper.py` (NEW)
**Purpose:** Central module for managing the new storage structure

**Key Functions:**
- `get_user_paper_path(username, paper_id)` - Returns base path for user's paper
- `save_chat_log(username, paper_id, direction, data)` - Saves chat logs with timestamp format
- `get_image_path(username, paper_id, filename)` - Returns image storage path
- `get_paper_json_path(username, paper_id, title)` - Returns editor JSON path
- `get_slr_json_path(username, paper_id, title)` - Returns SLR JSON path
- `get_docx_path(username, paper_id, title, journal)` - Returns DOCX output path
- `get_legacy_paper_dir(paper_id)` - Returns legacy path for backward compatibility
- `migrate_to_new_structure(user_id, paper_id)` - Optional migration helper

**Features:**
- Automatic directory creation
- Safe filename sanitization
- Username resolution from user_id
- Backward compatibility helpers

## Files Modified

### 2. `backend/chat.py`
**Changes:**
- Added import: `from storage_helper import save_chat_log, _get_username_from_user_id`
- Updated chat logging to use new timestamp format (DDMMYY-HHMM instead of turn_id)
- Saves chat logs to new structure: `data/<username>/<paper_id>/chat/`
- Maintains legacy logging for backward compatibility
- Logs both send and recv messages with proper error handling

**Lines Modified:**
- Line 23: Added storage_helper imports
- Lines 578-595: Updated user message logging
- Lines 908-929: Updated assistant message logging
- Lines 947-961: Updated error logging

### 3. `backend/image_worker.py`
**Changes:**
- Added import: `from storage_helper import get_image_path, _get_username_from_user_id`
- Updated image generation to save to new structure
- Maintains copy in legacy location for backward compatibility
- Cleans up both locations on error

**Lines Modified:**
- Line 99: Added User model import and storage_helper imports
- Line 119: Added username resolution
- Lines 141-147: Updated image path generation
- Lines 180-202: Updated compression and dual-location saving
- Lines 237-245: Updated cleanup to handle both locations

### 4. `backend/images_bp.py`
**Changes:**
- Added import: `from storage_helper import get_image_path, _get_username_from_user_id`
- Updated both upload endpoints (upload_paper_image and upload_user_image)
- Saves images to new structure with legacy fallback
- Cleans up both locations on DB failure

**Lines Modified:**
- Line 33: Added storage_helper imports
- Lines 80-87: Updated upload_paper_image path handling
- Lines 90-107: Updated cleanup logic
- Lines 159-170: Updated upload_user_image path handling
- Lines 172-196: Updated cleanup logic

### 5. `backend/app.py`
**Changes:**
- Updated export_docx() function to save DOCX to new structure
- Falls back to legacy location if username/paper_id unavailable
- Preserves DOCX files in new structure (doesn't delete on cleanup)

**Lines Modified:**
- Lines 1126-1173: Updated export_docx function with new storage logic

### 6. `backend/papers_bp.py`
**Changes:**
- Added paper JSON disk persistence to all save/update endpoints
- Saves paper JSON to: `data/<username>/<paper_id>/<title>.json`
- Non-blocking: failures are logged but don't break the API response

**Functions Updated:**
- `save_paper()` - Lines 70-99: Added JSON disk save
- `update_paper()` - Lines 120-142: Added JSON disk save
- `patch_paper()` - Lines 222-272: Added JSON disk save

## Backward Compatibility

### Maintained Features:
1. **SQL Database Schema:** NO changes to database structure
2. **Legacy Paths:** All files are ALSO saved to legacy locations:
   - Images: `backend/data/uploads/<paper_id>/`
   - Files: `backend/data/uploads/<paper_id>/files/`
   - Chat logs: `backend/data/logs/<user_slug>/<paper_id>/<chat_id>/`
   - DOCX: `backend/data/exports/` (when user/paper info unavailable)

3. **Dual Writing:** New code writes to BOTH new and legacy locations
4. **Graceful Degradation:** If new structure fails, operations continue with legacy paths

## Testing Results

✅ All Python files compile without syntax errors
✅ storage_helper functions work correctly
✅ New directory structure creates properly
✅ Chat logs use correct timestamp format (DDMMYY-HHMM)
✅ Path sanitization works correctly
✅ Username resolution from user_id works

## Migration Strategy

### Automatic (Implemented):
- New files automatically go to new structure
- Legacy locations maintained for compatibility
- No user action required

### Optional (Available):
- `migrate_to_new_structure(user_id, paper_id)` function available
- Can be called on-demand to copy existing files to new structure
- Non-destructive: copies files, doesn't move them

## Potential Issues & Considerations

### 1. Disk Space
- **Issue:** Files are now stored in two locations (new + legacy)
- **Impact:** ~2x disk usage for images and files
- **Mitigation:** Can remove legacy locations after migration period

### 2. Username Changes
- **Issue:** If user email changes, username path changes
- **Impact:** Files would be in old username directory
- **Mitigation:** Username is resolved at runtime from user_id

### 3. Title Changes
- **Issue:** Paper JSON filename based on title
- **Impact:** Old JSON files remain when title changes
- **Mitigation:** Latest file always has current title; old files can be cleaned up

### 4. Performance
- **Issue:** Dual writes add slight overhead
- **Impact:** Minimal - file I/O is fast for small files
- **Mitigation:** Can disable legacy writes after migration

### 5. SLR JSON
- **Issue:** SLR JSON path defined but not yet integrated
- **Impact:** SLR results still need to be updated to use new paths
- **Mitigation:** Path helper is ready; just needs integration in slr_bp.py

## Next Steps (Optional)

1. **Remove Legacy Writes:** After confirming new structure works, remove dual-write logic
2. **Migrate Existing Files:** Run migration for existing papers
3. **Update SLR Integration:** Update slr_bp.py to use `get_slr_json_path()`
4. **Add Cleanup Job:** Periodic cleanup of old JSON files when titles change
5. **Add Migration Endpoint:** Admin endpoint to trigger bulk migration

## Files NOT Modified

These files were analyzed but not modified (no storage operations):
- `backend/models.py` - Database schema unchanged
- `backend/paper_utils.py` - Legacy helpers maintained
- `backend/files_bp.py` - Uses existing paper_dir structure (compatible)
- `backend/slr_bp.py` - SLR JSON path helper ready but not integrated yet

## Rollback Plan

If issues arise:
1. New structure is additive - can be disabled without breaking existing functionality
2. Remove storage_helper imports from modified files
3. Revert to git commit before changes
4. Legacy paths continue to work independently

## Verification Commands

```bash
# Check new structure
ls -la backend/data/<username>/<paper_id>/

# Check chat logs format
ls -la backend/data/<username>/<paper_id>/chat/

# Check images
ls -la backend/data/<username>/<paper_id>/image/

# Test storage helper
cd backend && python3 -c "from storage_helper import *; print('OK')"
```

## Summary

✅ **Completed:** All required functionality implemented
✅ **Tested:** Basic functionality verified
✅ **Backward Compatible:** Legacy paths maintained
✅ **Database:** No schema changes required
✅ **Safe:** Non-destructive, can be rolled back

The restructure is complete and ready for testing in development environment.
