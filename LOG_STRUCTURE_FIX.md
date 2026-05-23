# Log Structure Fix - Generation Logs

**Date:** 2026-05-23  
**Issue:** Paper generation logs were still using old nested directory structure  
**Status:** ✅ FIXED

---

## Problem

Paper generation logs were being created in the old structure:
```
backend/data/logs/1/3917135ccb95/a82ec1d95c57/
├── 00_request.json
├── 01_raw_response_meta.json
└── 01_raw_response.txt
```

Where:
- `1` = user_id
- `3917135ccb95` = paper_id  
- `a82ec1d95c57` = job_id (generation job)

This was inconsistent with the new storage structure used for chat logs.

---

## Root Cause

The file `generate_paper_single.py` had its own logging system that was not updated when the storage structure was reorganized:

**Old code (lines 55-100):**
```python
_LOG_ROOT = Path(__file__).parent / "data" / "logs"

def _user_slug_for_log(user_id) -> str:
    # Created slugs like "1__username" or just "1"
    ...

def _gen_log_dir(user_id, paper_id, job_id) -> Path | None:
    d = (
        _LOG_ROOT
        / _user_slug_for_log(user_id)
        / _safe_seg(paper_id, "_no-paper")
        / _safe_seg(job_id, "_no-job")
    )
    d.mkdir(parents=True, exist_ok=True)
    return d
```

---

## Solution

### 1. Added new function to `storage_helper.py`

```python
def get_generation_log_path(username: str, paper_id: str, job_id: str) -> Path:
    """
    Get path for paper generation logs.
    
    Returns:
        Path: backend/data/<username>/<paper_id>/generation/<job_id>/
    """
    base_path = get_user_paper_path(username, paper_id)
    gen_dir = base_path / "generation" / _safe_path_seg(job_id, "no_job")
    gen_dir.mkdir(parents=True, exist_ok=True)
    return gen_dir
```

### 2. Updated `generate_paper_single.py`

**New imports:**
```python
from storage_helper import get_generation_log_path, _get_username_from_user_id
```

**Simplified `_gen_log_dir()` function:**
```python
def _gen_log_dir(user_id, paper_id, job_id) -> Path | None:
    """Build (and create) the per-job log directory.

    Layout: backend/data/<username>/<paper_id>/generation/<job_id>/
    Uses the new storage structure from storage_helper.py.
    """
    try:
        username = _get_username_from_user_id(user_id)
        d = get_generation_log_path(username, paper_id, job_id)
        return d
    except Exception as e:
        log.warning("[generator-log] mkdir failed: %s", e)
        return None
```

**Removed:**
- `_LOG_ROOT` constant
- `_SAFE_NAME_RE_GEN` regex
- `_safe_seg()` function
- `_user_slug_for_log()` function

---

## New Directory Structure

### Before (Old Structure)
```
backend/data/
├── logs/
│   └── 1/                          # user_id
│       └── 3917135ccb95/           # paper_id
│           └── a82ec1d95c57/       # job_id
│               ├── 00_request.json
│               ├── 01_raw_response_meta.json
│               └── 01_raw_response.txt
└── uploads/
    └── <paper_id>/
```

### After (New Structure)
```
backend/data/
├── <username>/                     # e.g., "sirobo" or "user_1"
│   └── <paper_id>/                 # e.g., "3917135ccb95"
│       ├── chat/                   # Chat logs
│       │   ├── 250523-134530-send.json
│       │   └── 250523-134532-recv.json
│       ├── generation/             # Generation logs (NEW!)
│       │   └── <job_id>/           # e.g., "a82ec1d95c57"
│       │       ├── 00_request.json
│       │       ├── 01_raw_response_meta.json
│       │       └── 01_raw_response.txt
│       ├── image/                  # Generated images
│       │   └── *.png
│       ├── files/                  # Uploaded files
│       │   └── *.pdf
│       ├── <paper_title>.json      # Editor JSON
│       ├── <paper_title>-SLR.json  # SLR results
│       └── <paper_title>.docx      # DOCX export
└── uploads/                        # Legacy (for backward compat)
```

---

## Benefits

1. **Consistency**: All logs now use the same directory structure
2. **Organization**: All paper-related files are in one place per user
3. **Clarity**: Username-based folders are more readable than user_id
4. **Maintainability**: Single source of truth for path generation (storage_helper.py)
5. **Scalability**: Easier to backup/migrate user data (one folder per user)

---

## Files Modified

1. **`backend/storage_helper.py`**
   - Added `get_generation_log_path()` function

2. **`backend/generate_paper_single.py`**
   - Updated imports to use storage_helper
   - Simplified `_gen_log_dir()` function
   - Removed redundant helper functions
   - Reduced from ~100 lines to ~15 lines for logging setup

---

## Testing

### Verify New Structure
```bash
# After next paper generation, check that logs go to new location:
ls -la backend/data/<username>/<paper_id>/generation/<job_id>/

# Should see:
# 00_request.json
# 01_raw_response_meta.json
# 01_raw_response.txt
```

### Old Logs
Old logs in `backend/data/logs/` are preserved for reference but will not be used for new generations.

---

## Migration (Optional)

To migrate old logs to the new structure, you can run:

```python
# migration_script.py
from pathlib import Path
from storage_helper import get_generation_log_path, _get_username_from_user_id
import shutil

old_logs = Path("backend/data/logs")
for user_dir in old_logs.iterdir():
    if not user_dir.is_dir():
        continue
    
    user_id = user_dir.name.split("__")[0] if "__" in user_dir.name else user_dir.name
    username = _get_username_from_user_id(user_id)
    
    for paper_dir in user_dir.iterdir():
        if not paper_dir.is_dir():
            continue
        
        paper_id = paper_dir.name
        
        for job_dir in paper_dir.iterdir():
            if not job_dir.is_dir():
                continue
            
            job_id = job_dir.name
            new_path = get_generation_log_path(username, paper_id, job_id)
            
            # Copy files
            for file in job_dir.glob("*"):
                if file.is_file():
                    shutil.copy2(file, new_path / file.name)
            
            print(f"Migrated: {job_dir} -> {new_path}")
```

---

## Related Changes

This fix is part of the larger storage reorganization that includes:

1. ✅ Chat logs: `backend/data/<username>/<paper_id>/chat/` (already done)
2. ✅ Generation logs: `backend/data/<username>/<paper_id>/generation/` (this fix)
3. ✅ Images: `backend/data/<username>/<paper_id>/image/` (already done)
4. ✅ Files: `backend/data/<username>/<paper_id>/files/` (already done)
5. ✅ Exports: `backend/data/<username>/<paper_id>/<title>.{json,docx}` (already done)

---

## Conclusion

The generation log structure has been successfully updated to match the new storage organization. All new paper generation jobs will now create logs in the clean, user-organized structure:

```
backend/data/<username>/<paper_id>/generation/<job_id>/
```

Old logs in `backend/data/logs/` are preserved but will not receive new entries.
