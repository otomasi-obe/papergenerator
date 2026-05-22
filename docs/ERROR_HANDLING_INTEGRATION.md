# Error Handling System - Integration Guide

## Quick Start

### Step 1: Register Backend Error Handlers

Add to `backend/app.py` after app initialization:

```python
from errors import register_error_handlers

# ... existing app setup ...

# Register error handlers (add after all blueprints are registered)
register_error_handlers(app)
```

### Step 2: Setup Frontend Error Handler

Add to `frontend/src/main.js`:

```javascript
import { errorHandler } from '@/services/errorHandler'
import axios from 'axios'

// Setup axios interceptor for automatic error handling
axios.interceptors.response.use(
  response => response,
  async error => {
    const parsed = errorHandler.parseError(error)
    
    // Auto-redirect to login for auth errors
    if (parsed.code === 'UNAUTHORIZED' || parsed.code === 'TOKEN_EXPIRED') {
      setTimeout(() => {
        window.location.href = '/login'
      }, 2000)
    }
    
    // Log errors for debugging
    errorHandler.logError(error, {
      url: error.config?.url,
      method: error.config?.method
    })
    
    return Promise.reject(error)
  }
)

// Set user level based on user preference (optional)
// errorHandler.setUserLevel('intermediate') // 'beginner' | 'intermediate' | 'advanced'
```

### Step 3: Test the Integration

Create a test endpoint in `backend/app.py`:

```python
from errors import NotFoundError, ErrorCode

@app.route('/api/test/error')
def test_error():
    raise NotFoundError(
        message="Test error",
        code=ErrorCode.NOT_FOUND
    )
```

Test in browser console:

```javascript
import { errorHandler } from '@/services/errorHandler'
import { useStore } from '@/stores/ui'

const store = useStore()

try {
  await axios.get('/api/test/error')
} catch (error) {
  await errorHandler.handleError(error, {
    showToast: true,
    toastStore: store
  })
}
```

## Migration Examples

### Example 1: Migrate a Simple Endpoint

**Before (`backend/papers_bp.py`):**
```python
@papers_bp.route('/api/papers/<paper_id>', methods=['GET'])
@jwt_required()
def get_paper(paper_id):
    user_id = get_jwt_identity()
    
    if not paper_id or len(paper_id) > 20:
        return jsonify({"error": "Invalid paper id"}), 400
    
    paper = Paper.query.get(paper_id)
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    
    if paper.user_id != user_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    return jsonify(paper.to_dict())
```

**After:**
```python
from errors import ValidationError, NotFoundError, AuthError, ErrorCode

@papers_bp.route('/api/papers/<paper_id>', methods=['GET'])
@jwt_required()
def get_paper(paper_id):
    user_id = get_jwt_identity()
    
    if not paper_id or len(paper_id) > 20:
        raise ValidationError(
            message="Invalid paper ID format",
            code=ErrorCode.INVALID_FORMAT,
            details={"field": "paper_id", "max_length": 20}
        )
    
    paper = Paper.query.get(paper_id)
    if not paper:
        raise NotFoundError(
            message=f"Paper {paper_id} not found",
            code=ErrorCode.PAPER_NOT_FOUND,
            resource_type="paper"
        )
    
    if paper.user_id != user_id:
        raise AuthError(
            message="Access denied to this paper",
            code=ErrorCode.FORBIDDEN,
            status_code=403
        )
    
    return jsonify(paper.to_dict())
```

### Example 2: Migrate a Frontend Component

**Before (`frontend/src/stores/paper.js`):**
```javascript
async loadPaper(paperId) {
  try {
    const response = await axios.get(`/api/papers/${paperId}`)
    this.currentPaper = response.data
    return response.data
  } catch (error) {
    const msg = error?.response?.data?.error || error?.message || 'Failed to load paper'
    this.showToast(msg, 'error')
    throw error
  }
}
```

**After:**
```javascript
import { errorHandler } from '@/services/errorHandler'

async loadPaper(paperId) {
  try {
    const response = await axios.get(`/api/papers/${paperId}`)
    this.currentPaper = response.data
    return response.data
  } catch (error) {
    await errorHandler.handleError(error, {
      showToast: true,
      toastStore: this
    })
    throw error
  }
}
```

### Example 3: Migrate with Retry Logic

**Before (`frontend/src/stores/paper.js`):**
```javascript
async generatePaper(paperId) {
  try {
    const response = await axios.post(`/api/papers/${paperId}/generate`)
    return response.data
  } catch (error) {
    const msg = error?.response?.data?.error || 'Generation failed'
    this.showToast(msg, 'error')
    throw error
  }
}
```

**After:**
```javascript
import { errorHandler } from '@/services/errorHandler'

async generatePaper(paperId) {
  const operationId = `generate-${paperId}`
  
  try {
    const response = await axios.post(`/api/papers/${paperId}/generate`)
    errorHandler.resetRetryAttempts(operationId)
    return response.data
  } catch (error) {
    const result = await errorHandler.handleError(error, {
      operationId,
      onRetry: () => axios.post(`/api/papers/${paperId}/generate`),
      showToast: true,
      toastStore: this
    })
    
    if (result.retry && result.result) {
      return result.result.data
    }
    
    throw error
  }
}
```

## Common Patterns

### Pattern 1: Validation Errors

```python
from errors import ValidationError, ErrorCode

# Missing field
if not data.get('title'):
    raise ValidationError(
        message="Title is required",
        code=ErrorCode.MISSING_FIELD,
        details={"field": "title"}
    )

# Invalid format
if not re.match(r'^[a-zA-Z0-9_-]+$', paper_id):
    raise ValidationError(
        message="Invalid paper ID format",
        code=ErrorCode.INVALID_FORMAT,
        details={"field": "paper_id", "pattern": "^[a-zA-Z0-9_-]+$"}
    )

# File too large
if file.content_length > MAX_SIZE:
    raise ValidationError(
        message=f"File too large (max {MAX_SIZE} bytes)",
        code=ErrorCode.FILE_TOO_LARGE,
        details={"max_size": MAX_SIZE, "actual_size": file.content_length}
    )
```

### Pattern 2: Resource Not Found

```python
from errors import NotFoundError, ErrorCode

paper = Paper.query.get(paper_id)
if not paper:
    raise NotFoundError(
        message=f"Paper {paper_id} not found",
        code=ErrorCode.PAPER_NOT_FOUND,
        resource_type="paper"
    )

user = User.query.get(user_id)
if not user:
    raise NotFoundError(
        message=f"User {user_id} not found",
        code=ErrorCode.USER_NOT_FOUND,
        resource_type="user"
    )
```

### Pattern 3: Authorization Errors

```python
from errors import AuthError, ErrorCode

# Unauthorized (not logged in)
if not user_id:
    raise AuthError(
        message="Authentication required",
        code=ErrorCode.UNAUTHORIZED,
        status_code=401
    )

# Forbidden (logged in but no access)
if paper.user_id != user_id:
    raise AuthError(
        message="Access denied to this paper",
        code=ErrorCode.FORBIDDEN,
        status_code=403
    )
```

### Pattern 4: Conflict Errors

```python
from errors import ConflictError, ErrorCode

# Paper locked
if paper.active_operation:
    raise ConflictError(
        message=f"Paper is locked by {paper.active_operation}",
        code=ErrorCode.PAPER_LOCKED,
        details={
            "paper_id": paper.id,
            "active_operation": paper.active_operation
        }
    )

# Duplicate entry
existing = Paper.query.filter_by(title=title, user_id=user_id).first()
if existing:
    raise ConflictError(
        message="Paper with this title already exists",
        code=ErrorCode.DUPLICATE_ENTRY,
        details={"title": title}
    )
```

### Pattern 5: External API Errors

```python
from errors import ExternalError, ErrorCode
import requests

try:
    response = requests.post(API_URL, json=payload, timeout=180)
    response.raise_for_status()
    return response.json()

except requests.Timeout:
    raise ExternalError(
        message="AI service timeout",
        code=ErrorCode.UPSTREAM_TIMEOUT,
        status_code=503,
        service="AI API"
    )

except requests.RequestException as e:
    raise ExternalError(
        message=f"AI service error: {str(e)}",
        code=ErrorCode.UPSTREAM_ERROR,
        status_code=502,
        service="AI API"
    )
```

### Pattern 6: Database Errors

```python
from errors import AppError, ErrorCode, ErrorCategory
import logging

log = logging.getLogger(__name__)

try:
    db.session.add(paper)
    db.session.commit()
except Exception as e:
    db.session.rollback()
    log.exception("Database commit failed")
    raise AppError(
        message="Database operation failed",
        code=ErrorCode.DATABASE_ERROR,
        category=ErrorCategory.SERVER,
        status_code=500,
        details={"operation": "create_paper"}
    )
```

## Testing

### Backend Unit Tests

```python
import pytest
from errors import ValidationError, NotFoundError, ErrorCode

def test_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        raise ValidationError(
            message="Invalid input",
            code=ErrorCode.INVALID_INPUT
        )
    
    error = exc_info.value
    assert error.code == ErrorCode.INVALID_INPUT
    assert error.status_code == 400
    assert error.category == "VALIDATION"

def test_error_response_format(client):
    response = client.get('/api/papers/invalid-id')
    assert response.status_code == 404
    
    data = response.get_json()
    assert 'error' in data
    assert 'code' in data
    assert 'category' in data
    assert data['code'] == 'PAPER_NOT_FOUND'
```

### Frontend Unit Tests

```javascript
import { describe, it, expect } from 'vitest'
import { errorHandler } from '@/services/errorHandler'

describe('ErrorHandler', () => {
  it('should parse backend error', () => {
    const error = {
      response: {
        status: 404,
        data: {
          error: 'Paper tidak ditemukan',
          code: 'PAPER_NOT_FOUND',
          category: 'NOT_FOUND'
        }
      }
    }
    
    const parsed = errorHandler.parseError(error)
    expect(parsed.code).toBe('PAPER_NOT_FOUND')
    expect(parsed.category).toBe('NOT_FOUND')
    expect(parsed.statusCode).toBe(404)
  })
  
  it('should adapt error message by user level', () => {
    errorHandler.setUserLevel('beginner')
    
    const error = { code: 'PAPER_NOT_FOUND', message: 'Not found' }
    const friendly = errorHandler.getUserFriendlyMessage(error)
    
    expect(friendly.message).toContain('tidak ditemukan')
    expect(friendly.showDetails).toBe(false)
  })
})
```

## Troubleshooting

### Issue 1: Error handler not catching errors

**Problem:** Errors are not being caught by the error handler.

**Solution:** Make sure `register_error_handlers(app)` is called AFTER all blueprints are registered in `app.py`.

### Issue 2: Frontend not showing user-friendly messages

**Problem:** Frontend shows raw error messages instead of user-friendly ones.

**Solution:** Make sure you're using `errorHandler.handleError()` instead of manually parsing errors.

### Issue 3: Retry logic not working

**Problem:** Errors are not being retried automatically.

**Solution:** Make sure you provide both `operationId` and `onRetry` callback to `handleError()`.

### Issue 4: Error details not showing

**Problem:** Error details are not visible in the UI.

**Solution:** Set user level to 'advanced' or 'intermediate' to see details:
```javascript
errorHandler.setUserLevel('advanced')
```

## Rollback Plan

If issues arise, you can temporarily disable the new error handling:

### Backend Rollback

Comment out in `app.py`:
```python
# from errors import register_error_handlers
# register_error_handlers(app)
```

Old error format will still work:
```python
return jsonify({"error": "Error message"}), 400
```

### Frontend Rollback

Remove from `main.js`:
```javascript
// Remove axios interceptor setup
```

Old error handling will still work:
```javascript
const msg = error?.response?.data?.error || 'Error'
store.showToast(msg, 'error')
```

## Next Steps

1. ✅ Integrate error handlers into app.py and main.js
2. ⏳ Test with existing endpoints
3. ⏳ Migrate high-priority endpoints (auth, papers, chat)
4. ⏳ Migrate high-priority components (ChatTab, LiteratureTab)
5. ⏳ Add comprehensive tests
6. ⏳ Monitor error rates in production
7. ⏳ Gather user feedback on error messages
8. ⏳ Iterate and improve

## Support

- Documentation: `docs/ERROR_HANDLING.md`
- Examples: `backend/examples_error_handling.py`, `frontend/src/examples/errorHandlingExamples.js`
- Implementation Plan: `docs/ERROR_HANDLING_IMPLEMENTATION_PLAN.md`
