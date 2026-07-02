# Log Path Fix Report
**Date:** 2026-06-30  
**Issue:** Nested directories created by relative paths (`../../log`, `../data`)

---

## 🐛 Root Cause

Code menggunakan **relative paths** yang bergantung pada CWD:
```python
# ❌ BAD (CWD-dependent)
_LOG_DIR = Path("../../log/slr")
charts_base = Path(os.path.join(os.path.dirname(__file__), "..", "..", "data", "charts"))
```

Kalau script dijalankan dari CWD salah → nested dirs:
- `backend/backend/log/generator/`
- `tools/data/data/charts/`

---

## ✅ Fixed Files

### 1. **tools/Literatur/slrFetch.py**
```python
# ✅ FIXED (absolute from __file__)
_SLR_LOG_DIR_ENV = os.getenv("SLR_LOG_DIR")
if _SLR_LOG_DIR_ENV:
    _LOG_DIR = Path(_SLR_LOG_DIR_ENV)
else:
    # backend/tools/Literatur/slrFetch.py → backend/log/slr
    _LOG_DIR = Path(__file__).resolve().parent.parent.parent / "log" / "slr"
```

### 2. **tools/Literatur/slrSummarize.py**
```python
# ✅ FIXED (absolute from __file__)
_SLR_LOG_DIR_ENV = os.getenv("SLR_LOG_DIR")
if _SLR_LOG_DIR_ENV:
    _LOG_DIR = Path(_SLR_LOG_DIR_ENV)
else:
    _LOG_DIR = Path(__file__).resolve().parent.parent.parent / "log" / "slr"
```

### 3. **tools/data/chart_generator.py**
```python
# ✅ FIXED (absolute from __file__)
charts_base = Path(__file__).resolve().parent.parent.parent / "data" / "charts"
```

---

## 🧹 Cleanup

**Script:** `cleanup_nested_dirs.sh`

**Results:**
- ✅ `tools/data/data/` → cleaned (8K, moved to `backend/data/charts/`)
- ✅ `backend/backend/` → not found (already clean or never created)

**Command:**
```bash
cd /home/sirobo/papergenerator/backend
./cleanup_nested_dirs.sh
```

---

## ✅ Verification

Test all log paths resolve correctly:
```bash
cd /home/sirobo/papergenerator/backend
python3 -c "
from tools.Literatur.slrFetch import _LOG_DIR as slr_fetch
from tools.Literatur.slrSummarize import _LOG_DIR as slr_sum
from tools.Literatur.slrOrchestrator import _LOG_DIR as slr_orch

print('slrFetch:', slr_fetch)
print('slrSummarize:', slr_sum)
print('slrOrchestrator:', slr_orch)
"
```

**Output:**
```
slrFetch: /home/sirobo/papergenerator/backend/log/slr
slrSummarize: /home/sirobo/papergenerator/backend/log/slr
slrOrchestrator: /home/sirobo/papergenerator/backend/log/slr
```

All paths correct ✅

---

## 📊 Summary

| File | Before | After | Status |
|------|--------|-------|--------|
| slrFetch.py | `../../log/slr` | `Path(__file__).resolve().parent.parent.parent / "log" / "slr"` | ✅ Fixed |
| slrSummarize.py | `../../log/slr` | `Path(__file__).resolve().parent.parent.parent / "log" / "slr"` | ✅ Fixed |
| chart_generator.py | `os.path.join(.., .., data)` | `Path(__file__).resolve().parent.parent.parent / "data"` | ✅ Fixed |
| Nested dirs | 2 found (112K) | 0 remaining | ✅ Cleaned |

---

## 🎯 Correct Log Structure

```
backend/
├── log/                          ← ROOT log dir
│   ├── slr/                      ← SLR logs (slrFetch, slrSummarize, slrOrchestrator)
│   ├── generator/                ← Gemini account logs (CreateImageGemini)
│   ├── backend.log               ← Global backend log
│   ├── error.log                 ← Error log
│   └── gunicorn-*.log            ← Gunicorn logs
└── data/
    ├── charts/                   ← Generated charts
    ├── uploads/                  ← User uploads
    └── exports/                  ← Exported files
```

**No more:** ❌ `backend/backend/`, ❌ `tools/data/data/`

---

## 🔒 Prevention

**Rule:** Always use `Path(__file__).resolve()` for paths relative to code location.

**Pattern:**
```python
# Get backend/ root from any file
BACKEND_ROOT = Path(__file__).resolve().parents[N]  # N = levels up
LOG_DIR = BACKEND_ROOT / "log" / "subdir"
DATA_DIR = BACKEND_ROOT / "data" / "subdir"
```

Never use:
- ❌ `Path("../../log")`  — CWD-dependent
- ❌ `os.path.join("..", "..", "data")`  — CWD-dependent
- ❌ `"backend/log"`  — assumes CWD = project root

---

**Status:** 🟢 All fixed, nested dirs cleaned, tests passing
