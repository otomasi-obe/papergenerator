# File Upload System - Test Cases
**Date:** 2026-05-22  
**Version:** Post-Security-Fix  
**Test Environment:** Backend (Flask) + Frontend (Vue 3)

---

## 🧪 SECURITY TEST CASES

### Test 1: Magic Bytes Validation - Malicious File Detection
**Priority:** CRITICAL  
**Objective:** Verify that files with mismatched content are rejected

**Steps:**
1. Create a text file with content "This is malware"
2. Rename it from `malware.txt` to `malware.pdf`
3. Attempt to upload via UI

**Expected Result:**
- ❌ Upload rejected
- Warning message: "malware.pdf: konten file tidak sesuai dengan ekstensi (kemungkinan file berbahaya)"
- File NOT saved to disk
- File NOT added to database

**Actual Result:** [TO BE TESTED]

---

### Test 2: Memory Exhaustion Prevention - Large File
**Priority:** CRITICAL  
**Objective:** Verify server doesn't read entire oversized file into memory

**Steps:**
1. Create a 100MB dummy file: `dd if=/dev/zero of=large.pdf bs=1M count=100`
2. Attempt to upload via API or UI
3. Monitor server memory usage during upload

**Expected Result:**
- ❌ Upload rejected after reading ~30MB
- Warning message: "large.pdf: File exceeds 30MB limit"
- Server memory does NOT spike by 100MB
- File NOT saved to disk

**Actual Result:** [TO BE TESTED]

---

### Test 3: Content Validation - PDF with Embedded JavaScript
**Priority:** HIGH  
**Objective:** Verify PDF files are validated (basic check)

**Steps:**
1. Create a valid PDF file
2. Upload via UI

**Expected Result:**
- ✅ Upload succeeds (magic bytes match)
- File saved and extractable

**Note:** Full XSS/malicious content detection requires additional tools (ClamAV, etc.)

**Actual Result:** [TO BE TESTED]

---

### Test 4: Frontend Size Validation
**Priority:** HIGH  
**Objective:** Verify frontend rejects oversized files before upload

**Steps:**
1. Create a 50MB file
2. Select it via file picker
3. Observe behavior before network request

**Expected Result:**
- ❌ Upload blocked at frontend
- Warning message: "File terlalu besar (max 30MB): [filename]"
- NO network request sent to backend
- Bandwidth saved

**Actual Result:** [TO BE TESTED]

---

## 📋 FUNCTIONAL TEST CASES

### Test 5: Valid PDF Upload
**Priority:** HIGH  
**Objective:** Verify normal PDF upload works

**Steps:**
1. Select a valid 5MB PDF file
2. Click "Upload file"
3. Wait for completion

**Expected Result:**
- ✅ Upload succeeds
- Progress shows "1 files - 0%" → "1 files - 100%"
- File appears in left sidebar
- Preview loads in iframe
- No warnings

**Actual Result:** [TO BE TESTED]

---

### Test 6: Multiple File Upload (Mixed Types)
**Priority:** HIGH  
**Objective:** Verify batch upload with different file types

**Steps:**
1. Select 5 files: 2 PDFs, 1 DOCX, 1 TXT, 1 CSV
2. Click "Upload file"
3. Wait for completion

**Expected Result:**
- ✅ All 5 files uploaded
- Progress shows "5 files - 0%" → "5 files - 100%"
- All files appear in sidebar with correct icons:
  - PDF: 📕
  - DOCX: 📘
  - TXT: 📄
  - CSV: 📈
- No warnings

**Actual Result:** [TO BE TESTED]

---

### Test 7: Excel/CSV File Upload (New Feature)
**Priority:** MEDIUM  
**Objective:** Verify Excel and CSV files are now supported

**Steps:**
1. Create a simple Excel file (.xlsx) with data
2. Create a CSV file with comma-separated values
3. Upload both files

**Expected Result:**
- ✅ Both files accepted
- XLSX shows 📊 icon
- CSV shows 📈 icon
- Preview shows extracted text/data
- No warnings

**Actual Result:** [TO BE TESTED]

---

### Test 8: Upload Cancellation
**Priority:** MEDIUM  
**Objective:** Verify user can cancel in-progress upload

**Steps:**
1. Select a large file (20MB PDF)
2. Click "Upload file"
3. Immediately click "✕ Cancel" button while uploading

**Expected Result:**
- ❌ Upload cancelled
- Warning message: "Upload dibatalkan"
- File NOT saved to disk
- File NOT added to database
- UI returns to normal state

**Actual Result:** [TO BE TESTED]

---

### Test 9: File Download
**Priority:** MEDIUM  
**Objective:** Verify new download button works

**Steps:**
1. Upload a PDF file
2. Select it in sidebar
3. Click "Download ↓" button

**Expected Result:**
- ✅ File downloads to user's Downloads folder
- Original filename preserved
- File content intact

**Actual Result:** [TO BE TESTED]

---

### Test 10: File Deletion
**Priority:** MEDIUM  
**Objective:** Verify file deletion works

**Steps:**
1. Upload a file
2. Hover over file in sidebar
3. Click 🗑 button
4. Confirm deletion in dialog

**Expected Result:**
- ✅ File removed from sidebar
- File deleted from disk
- File removed from database
- If it was selected, preview clears

**Actual Result:** [TO BE TESTED]

---

### Test 11: Mixed Valid/Invalid Upload
**Priority:** MEDIUM  
**Objective:** Verify partial success handling

**Steps:**
1. Select 4 files:
   - valid.pdf (5MB, valid)
   - fake.pdf (renamed .txt, invalid content)
   - huge.docx (50MB, too large)
   - good.txt (1MB, valid)
2. Upload all

**Expected Result:**
- ✅ 2 files succeed (valid.pdf, good.txt)
- ❌ 2 files rejected
- Warning message shows both rejections:
  - "fake.pdf: konten file tidak sesuai dengan ekstensi"
  - "huge.docx: File exceeds 30MB limit"
- Only valid files appear in sidebar

**Actual Result:** [TO BE TESTED]

---

### Test 12: Preview Different File Types
**Priority:** MEDIUM  
**Objective:** Verify preview works for all supported types

**Test Cases:**
| File Type | Expected Preview |
|-----------|------------------|
| PDF | Inline iframe with PDF viewer |
| DOCX | Extracted text with paragraphs and tables |
| TXT | Plain text in monospace font |
| MD | Markdown source (not rendered) |
| CSV | Comma-separated values in monospace |
| XLSX | Extracted sheet data with tabs |

**Steps:**
1. Upload one file of each type
2. Click each file in sidebar
3. Verify preview renders correctly

**Expected Result:**
- ✅ All previews load without errors
- Text is readable and properly formatted
- No "(tidak bisa di-preview di browser)" errors

**Actual Result:** [TO BE TESTED]

---

## ⚡ PERFORMANCE TEST CASES

### Test 13: Extraction Timeout
**Priority:** MEDIUM  
**Objective:** Verify extraction doesn't hang indefinitely

**Steps:**
1. Upload a very complex PDF (100+ pages with images)
2. Monitor extraction time

**Expected Result:**
- ⏱️ Extraction completes within 30 seconds OR times out
- If timeout: file still saved, but extracted_text is empty
- No server hang
- Other uploads can proceed

**Actual Result:** [TO BE TESTED]

---

### Test 14: Concurrent Uploads (20 Worker Pool)
**Priority:** LOW  
**Objective:** Verify extraction pool handles concurrent uploads

**Steps:**
1. Open 3 browser tabs
2. Upload 10 files in each tab simultaneously (30 total)
3. Monitor server behavior

**Expected Result:**
- ✅ All 30 files eventually complete
- Max 20 extractions run concurrently
- Remaining 10 queue and wait
- No crashes or deadlocks

**Actual Result:** [TO BE TESTED]

---

## 🔒 EDGE CASES

### Test 15: Empty File
**Priority:** LOW  
**Steps:** Upload a 0-byte file

**Expected Result:**
- ❌ Rejected with "file kosong" warning

---

### Test 16: File with Special Characters in Name
**Priority:** LOW  
**Steps:** Upload `test file (2024) [final] #1.pdf`

**Expected Result:**
- ✅ Uploads successfully
- Original name preserved in database
- Stored with UUID filename on disk

---

### Test 17: Duplicate File Upload
**Priority:** LOW  
**Steps:** Upload same file twice

**Expected Result:**
- ✅ Both uploads succeed
- Two separate entries in database
- Two separate UUID filenames on disk
- No collision

---

### Test 18: Upload Without Paper Selected
**Priority:** LOW  
**Steps:** Try to upload when no paper is active

**Expected Result:**
- ❌ Upload button disabled
- No upload possible

---

## 📊 TEST SUMMARY TEMPLATE

```
Date: ___________
Tester: ___________

| Test # | Test Name | Status | Notes |
|--------|-----------|--------|-------|
| 1 | Magic Bytes Validation | ⬜ Pass / ⬜ Fail | |
| 2 | Memory Exhaustion Prevention | ⬜ Pass / ⬜ Fail | |
| 3 | Content Validation | ⬜ Pass / ⬜ Fail | |
| 4 | Frontend Size Validation | ⬜ Pass / ⬜ Fail | |
| 5 | Valid PDF Upload | ⬜ Pass / ⬜ Fail | |
| 6 | Multiple File Upload | ⬜ Pass / ⬜ Fail | |
| 7 | Excel/CSV Upload | ⬜ Pass / ⬜ Fail | |
| 8 | Upload Cancellation | ⬜ Pass / ⬜ Fail | |
| 9 | File Download | ⬜ Pass / ⬜ Fail | |
| 10 | File Deletion | ⬜ Pass / ⬜ Fail | |
| 11 | Mixed Valid/Invalid | ⬜ Pass / ⬜ Fail | |
| 12 | Preview All Types | ⬜ Pass / ⬜ Fail | |
| 13 | Extraction Timeout | ⬜ Pass / ⬜ Fail | |
| 14 | Concurrent Uploads | ⬜ Pass / ⬜ Fail | |
| 15 | Empty File | ⬜ Pass / ⬜ Fail | |
| 16 | Special Characters | ⬜ Pass / ⬜ Fail | |
| 17 | Duplicate Upload | ⬜ Pass / ⬜ Fail | |
| 18 | No Paper Selected | ⬜ Pass / ⬜ Fail | |

Overall Pass Rate: _____ / 18 (____%)
```

---

## 🚀 AUTOMATED TEST SCRIPT (Optional)

```python
# backend/tests/test_file_upload.py
import pytest
from io import BytesIO

def test_magic_bytes_validation():
    """Test that fake PDFs are rejected"""
    fake_pdf = BytesIO(b"This is not a PDF")
    # ... test upload endpoint
    assert response.status_code == 200
    assert "konten file tidak sesuai" in response.json['warnings'][0]

def test_size_limit():
    """Test that oversized files are rejected"""
    large_file = BytesIO(b"x" * (31 * 1024 * 1024))  # 31MB
    # ... test upload endpoint
    assert "exceeds 30MB" in response.json['warnings'][0]

# Add more automated tests...
```

---

## 📝 REGRESSION TEST CHECKLIST

After any future changes to file upload system, re-run:
- [ ] Test 1 (Security: Magic bytes)
- [ ] Test 2 (Security: Memory exhaustion)
- [ ] Test 5 (Basic upload)
- [ ] Test 6 (Multiple files)
- [ ] Test 8 (Cancellation)
- [ ] Test 11 (Partial success)
