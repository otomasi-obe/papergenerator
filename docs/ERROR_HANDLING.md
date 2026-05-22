# Error Handling System

## Overview

Unified error handling system across backend (Flask) and frontend (Vue 3) with standardized error codes, categories, user-friendly messages, and automatic retry strategies.

## Architecture

### Error Categories

| Category | Description | HTTP Status | Examples |
|----------|-------------|-------------|----------|
| `VALIDATION` | Input validation failures | 400 | Invalid format, missing fields |
| `AUTH` | Authentication/authorization | 401/403 | Unauthorized, token expired |
| `NOT_FOUND` | Resource not found | 404 | Paper not found, user not found |
| `CONFLICT` | Resource conflicts | 409 | Paper locked, duplicate entry |
| `RATE_LIMIT` | Rate limiting | 429 | Too many requests, quota exceeded |
| `EXTERNAL` | External API failures | 502/503 | AI timeout, upstream error |
| `SERVER` | Internal server errors | 500 | Database error, internal error |

### Error Codes

Standard error codes used across the system:

**Validation Errors (400)**
- `VALIDATION_FAILED` - General validation failure
- `INVALID_INPUT` - Invalid input format
- `MISSING_FIELD` - Required field missing
- `INVALID_FORMAT` - Format validation failed
- `FILE_TOO_LARGE` - File exceeds size limit
- `INVALID_FILE_TYPE` - Unsupported file type

**Auth Errors (401/403)**
- `UNAUTHORIZED` - Not authenticated
- `FORBIDDEN` - No permission
- `TOKEN_EXPIRED` - JWT token expired
- `INVALID_CREDENTIALS` - Wrong email/password

**Not Found Errors (404)**
- `NOT_FOUND` - Generic not found
- `PAPER_NOT_FOUND` - Paper doesn't exist
- `USER_NOT_FOUND` - User doesn't exist
- `FILE_NOT_FOUND` - File doesn't exist
- `CONVERSATION_NOT_FOUND` - Conversation doesn't exist

**Conflict Errors (409)**
- `PAPER_LOCKED` - Paper is being processed
- `RESOURCE_CONFLICT` - Resource conflict
- `DUPLICATE_ENTRY` - Duplicate data

**Rate Limit Errors (429)**
- `RATE_LIMIT_EXCEEDED` - Too many requests
- `QUOTA_EXCEEDED` - Token quota exceeded

**External Errors (502/503)**
- `UPSTREAM_TIMEOUT` - AI service timeout
- `UPSTREAM_ERROR` - AI service error
- `EXTERNAL_API_ERROR` - External API failure

**Server Errors (500)**
- `INTERNAL_ERROR` - Internal server error
- `DATABASE_ERROR` - Database operation failed
- `TOOL_EXECUTION_FAILED` - Tool execution failed

## Backend Usage

### Basic Usage

```python
from errors import ValidationError, NotFoundError, ConflictError, handle_error

@app.route('/api/papers/<paper_id>')
@jwt_required()
def get_paper(paper_id):
    user_id = get_jwt_identity()
    
    # Validate input
    if not paper_id or len(paper_id) > 20:
        raise ValidationError(
            message="Invalid paper ID format",
            code=ErrorCode.INVALID_INPUT,
            details={"field": "paper_id", "max_length": 20}
        )
    
    # Check resource exists
    paper = Paper.query.get(paper_id)
    if not paper:
        raise NotFoundError(
            message=f"Paper {paper_id} not found",
            code=ErrorCode.PAPER_NOT_FOUND,
            resource_type="paper"
        )
    
    # Check authorization
    if paper.user_id != user_id:
        raise AuthError(
            message="Access denied",
            code=ErrorCode.FORBIDDEN,
            status_code=403
        )
    
    return jsonify(paper.to_dict())
```

### Custom Error Classes

```python
from errors import AppError, ErrorCode, ErrorCategory

class PaperLockedError(AppError):
    def __init__(self, paper_id: str, operation: str):
        super().__init__(
            message=f"Paper {paper_id} is locked by {operation}",
            code=ErrorCode.PAPER_LOCKED,
            category=ErrorCategory.CONFLICT,
            status_code=409,
            details={
                "paper_id": paper_id,
                "active_operation": operation
            }
        )

# Usage
if paper.active_operation:
    raise PaperLockedError(paper.id, paper.active_operation)
```

### Register Error Handlers

In `app.py`:

```python
from errors import register_error_handlers

app = Flask(__name__)
# ... other config ...

register_error_handlers(app)
```

### Error Response Format

All errors return JSON in this format:

```json
{
  "error": "Paper tidak ditemukan",
  "code": "PAPER_NOT_FOUND",
  "category": "NOT_FOUND",
  "details": {
    "resource_type": "paper"
  }
}
```

## Frontend Usage

### Basic Usage

```javascript
import { errorHandler } from '@/services/errorHandler'
import { useStore } from '@/stores/ui'

const store = useStore()

async function loadPaper(paperId) {
  try {
    const response = await axios.get(`/api/papers/${paperId}`)
    return response.data
  } catch (error) {
    await errorHandler.handleError(error, {
      showToast: true,
      toastStore: store
    })
  }
}
```

### With Automatic Retry

```javascript
import { errorHandler } from '@/services/errorHandler'

async function generatePaper(paperId) {
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
      toastStore: store
    })
    
    if (result.retry && result.result) {
      return result.result.data
    }
    
    throw error
  }
}
```

### User Level Adaptation

```javascript
import { errorHandler } from '@/services/errorHandler'

// Set user level based on user preference
errorHandler.setUserLevel('beginner')  // 'beginner' | 'intermediate' | 'advanced'

// Beginner: "Paper sedang diproses. Tunggu sebentar ya 😊"
// Intermediate: "Paper locked: generation in progress. Wait or cancel."
// Advanced: "Paper locked by active operation. Cancel or wait for completion."
```

### Manual Error Parsing

```javascript
import { errorHandler } from '@/services/errorHandler'

const parsed = errorHandler.parseError(error)
console.log(parsed)
// {
//   message: "Paper tidak ditemukan",
//   code: "PAPER_NOT_FOUND",
//   category: "NOT_FOUND",
//   details: { resource_type: "paper" },
//   statusCode: 404,
//   originalError: {...}
// }

const friendly = errorHandler.getUserFriendlyMessage(parsed)
console.log(friendly)
// {
//   message: "Paper tidak ditemukan. Mungkin sudah dihapus.",
//   action: "Back",
//   showDetails: false
// }
```

## Error Recovery Strategies

The frontend automatically handles retry logic for transient errors:

| Error Code | Retryable | Retry Delay | Max Retries | Special Action |
|------------|-----------|-------------|-------------|----------------|
| `UPSTREAM_TIMEOUT` | ✅ | 30s | 3 | - |
| `TOOL_EXECUTION_FAILED` | ✅ | 5s | 2 | - |
| `PAPER_LOCKED` | ✅ | 10s | 5 | - |
| `NETWORK_ERROR` | ✅ | 5s | 3 | - |
| `RATE_LIMIT_EXCEEDED` | ✅ | 60s | 1 | - |
| `QUOTA_EXCEEDED` | ❌ | - | - | Show quota info |
| `UNAUTHORIZED` | ❌ | - | - | Redirect to login |
| `TOKEN_EXPIRED` | ❌ | - | - | Redirect to login |

## Migration Guide

### Backend Migration

**Before:**
```python
@app.route('/api/papers/<paper_id>')
def get_paper(paper_id):
    paper = Paper.query.get(paper_id)
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    return jsonify(paper.to_dict())
```

**After:**
```python
from errors import NotFoundError, ErrorCode

@app.route('/api/papers/<paper_id>')
def get_paper(paper_id):
    paper = Paper.query.get(paper_id)
    if not paper:
        raise NotFoundError(
            message=f"Paper {paper_id} not found",
            code=ErrorCode.PAPER_NOT_FOUND
        )
    return jsonify(paper.to_dict())
```

### Frontend Migration

**Before:**
```javascript
try {
  const response = await axios.get(`/api/papers/${paperId}`)
  return response.data
} catch (error) {
  const msg = error?.response?.data?.error || error?.message || 'Error'
  store.showToast(msg, 'error')
}
```

**After:**
```javascript
import { errorHandler } from '@/services/errorHandler'

try {
  const response = await axios.get(`/api/papers/${paperId}`)
  return response.data
} catch (error) {
  await errorHandler.handleError(error, {
    showToast: true,
    toastStore: store
  })
}
```

## Best Practices

### Backend

1. **Use specific error classes** - Don't use generic `AppError` when specific classes exist
2. **Include details** - Add context in the `details` field for debugging
3. **Don't expose internals** - Never include SQL queries, stack traces, or internal paths in user messages
4. **Log before raising** - Use `log.warning()` or `log.error()` before raising errors
5. **Sanitize messages** - Use `sanitize_error_message()` for external error messages

### Frontend

1. **Always use errorHandler** - Don't manually parse errors
2. **Set operation IDs** - Use unique operation IDs for retry logic
3. **Provide retry callbacks** - Implement `onRetry` for retryable operations
4. **Log advanced errors** - The handler automatically logs for advanced users
5. **Reset retry attempts** - Call `resetRetryAttempts()` on success

## Testing

### Backend Tests

```python
from errors import ValidationError, ErrorCode

def test_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        raise ValidationError(
            message="Invalid input",
            code=ErrorCode.INVALID_INPUT
        )
    
    error = exc_info.value
    assert error.code == ErrorCode.INVALID_INPUT
    assert error.status_code == 400
    assert error.category == ErrorCategory.VALIDATION
```

### Frontend Tests

```javascript
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
    expect(parsed.statusCode).toBe(404)
  })
})
```

## Monitoring

### Backend Logging

All errors are automatically logged with context:

```python
log.warning(f"AppError: {error.code} - {error.message}", extra={"details": error.details})
```

### Frontend Logging

Advanced users see detailed error logs in console:

```javascript
console.error('[ErrorHandler]', {
  message: "Paper tidak ditemukan",
  code: "PAPER_NOT_FOUND",
  category: "NOT_FOUND",
  context: { paperId: "abc123" },
  timestamp: "2026-05-22T16:00:00.000Z"
})
```

## Future Enhancements

- [ ] Error tracking integration (Sentry/GlitchTip)
- [ ] Error analytics dashboard
- [ ] Automatic error reporting
- [ ] Error rate limiting
- [ ] Circuit breaker pattern for external APIs
- [ ] Error recovery suggestions
- [ ] Multi-language support (i18n)
