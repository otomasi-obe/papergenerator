# File Upload System - Bug Report & Security Audit
**Date:** 2026-05-22  
**Audited Files:** `backend/files_bp.py`, `backend/extract_pdfs.py`, `frontend/src/components/FilesTab.vue`

---

## 🔴 CRITICAL SECURITY ISSUES

### 1. No Content-Type Validation (HIGH SEVERITY)
**Location:** `backend/files_bp.py:204-207`  
**Issue:** Only validates file extension, not actual file content. Attacker can rename `malware.exe` → `malware.pdf`

```python
ext = Path(f.filename or "").suffix.lower()
if ext not in ALLOWED_FILE_EXTS:
    warnings.append(f"{f.filename}: format tidak didukung")
```

**Risk:** Malicious executables, scripts, or exploits can be uploaded  
**Fix:** Validate magic bytes/MIME type using `python-magic` or `filetype` library

---

### 2. DoS via Memory Exhaustion (HIGH SEVERITY)
**Location:** `backend/files_bp.py:209-214`  
**Issue:** Reads entire file into memory BEFORE checking size

```python
data = f.stream.read()  # ← Reads entire file first
if len(data) > MAX_FILE_BYTES:  # ← Then checks size
    warnings.append(...)
```

**Risk:** Attacker uploads 500MB file → server reads all into RAM → then rejects  
**Fix:** Check `Content-Length` header or stream with size limit

---

### 3. No Malicious Content Detection (MEDIUM SEVERITY)
**Location:** `backend/files_bp.py` (missing entirely)  
**Issue:** No scanning for:
- Embedded JavaScript in PDFs
- Macro-enabled Office documents
- Polyglot files (valid PDF + executable)
- Zip bombs in DOCX/XLSX

**Risk:** XSS, code execution, resource exhaustion  
**Fix:** Integrate ClamAV or implement content sanitization

---

## 🟡 FUNCTIONAL BUGS

### 4. Frontend/Backend File Size Mismatch (HIGH PRIORITY)
**Locations:**
- Frontend: `FilesTab.vue:6` → "max 10MB per file"
- Backend: `files_bp.py:38` → `MAX_FILE_BYTES = 30 * 1024 * 1024`

**Impact:** User confusion, wasted uploads  
**Fix:** Update frontend to show 30MB or backend to enforce 10MB

---

### 5. Frontend/Backend File Type Mismatch (HIGH PRIORITY)
**Locations:**
- Frontend: `FilesTab.vue:12` → `.pdf,.docx,.doc,.txt,.md`
- Backend: `files_bp.py:33` → Also accepts `.xlsx,.xls,.csv`

**Impact:** Users can't upload Excel/CSV files through UI (but API accepts them)  
**Fix:** Add Excel/CSV to frontend accept attribute

---

### 6. No Frontend File Size Validation (MEDIUM PRIORITY)
**Location:** `FilesTab.vue:178-211`  
**Issue:** Files uploaded without client-side size check

**Impact:** Wastes bandwidth uploading 50MB file that backend will reject  
**Fix:** Add validation before FormData submission

---

### 7. No Upload Cancellation (MEDIUM PRIORITY)
**Location:** `FilesTab.vue:192-200`  
**Issue:** No AbortController for axios request

**Impact:** User can't cancel long upload, must wait or refresh page  
**Fix:** Implement AbortController with cancel button

---

### 8. Upload Progress Inconsistency (LOW PRIORITY)
**Location:** `FilesTab.vue:188-197`  
**Issue:** Comment says `0/${list.length}` but code shows percentage

```javascript
uploadProgress.value = `0/${list.length}`  // Line 188
// ...
uploadProgress.value = `${pct}%`  // Line 197 - different format!
```

**Impact:** Confusing progress display  
**Fix:** Use consistent format (e.g., "3/5 files - 67%")

---

### 9. Partial Upload Failure Unclear (MEDIUM PRIORITY)
**Location:** `files_bp.py:202-228`, `FilesTab.vue:204`  
**Issue:** If 5 files uploaded, 2 fail → warnings show "file.pdf: format tidak didukung" but unclear which succeeded

**Impact:** User doesn't know which files are actually uploaded  
**Fix:** Return structured success/failure list per file

---

### 10. No Explicit Download Button (LOW PRIORITY)
**Location:** `FilesTab.vue:77-82`  
**Issue:** Only "Buka di tab baru" (open in new tab), no download option

**Impact:** Users must right-click → save as  
**Fix:** Add download button with `download` attribute

---

## 🟢 PERFORMANCE ISSUES

### 11. Long Extraction Timeout (MEDIUM PRIORITY)
**Location:** `files_bp.py:241`  
**Issue:** 120 second timeout per file

```python
extracted = fut.result(timeout=120)
```

**Impact:** 10 large PDFs = 20 minutes of worker time  
**Fix:** Reduce to 30s, add timeout warning to user

---

### 12. No Rate Limiting (MEDIUM PRIORITY)
**Location:** `files_bp.py:179-268`  
**Issue:** No throttling on upload endpoint

**Impact:** User can spam 1000 upload requests  
**Fix:** Add Flask-Limiter (e.g., 20 uploads/minute)

---

## 📋 TEST SCENARIOS

### ✅ Should Pass
- [x] Upload valid 5MB PDF
- [x] Upload multiple files (3 PDFs + 2 DOCX)
- [x] Delete uploaded file
- [x] Preview TXT/MD files
- [x] Preview DOCX with tables

### ❌ Should Fail (Currently Passes - BUG!)
- [ ] Upload .exe renamed to .pdf → **ACCEPTED** (Bug #1)
- [ ] Upload 100MB file → **READS ALL INTO MEMORY** (Bug #2)
- [ ] Upload PDF with embedded JavaScript → **NO DETECTION** (Bug #3)
- [ ] Upload .xlsx via UI → **BLOCKED BY FRONTEND** (Bug #5)

### 🔧 Missing Features
- [ ] Cancel upload mid-progress
- [ ] Download file (not just open)
- [ ] Batch delete multiple files
- [ ] File rename after upload
- [ ] Duplicate file detection

---

## 🛠️ RECOMMENDED FIXES (Priority Order)

1. **CRITICAL:** Add magic bytes validation (Bug #1)
2. **CRITICAL:** Fix memory exhaustion (Bug #2)
3. **HIGH:** Sync frontend/backend file size limit (Bug #4)
4. **HIGH:** Sync frontend/backend file types (Bug #5)
5. **MEDIUM:** Add frontend size validation (Bug #6)
6. **MEDIUM:** Add upload cancellation (Bug #7)
7. **MEDIUM:** Add rate limiting (Bug #12)
8. **MEDIUM:** Implement malicious content detection (Bug #3)
9. **LOW:** Fix progress display (Bug #8)
10. **LOW:** Add download button (Bug #10)

---

## 📊 SECURITY SCORE: 4/10
- ✅ JWT authentication required
- ✅ User isolation (can only access own files)
- ✅ Path traversal protection (line 327-329)
- ✅ UUID filenames prevent collisions
- ❌ No content validation
- ❌ No malware scanning
- ❌ No rate limiting
- ❌ Memory exhaustion vulnerability
