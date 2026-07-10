import re

_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(previous|prior|above)\s+instructions?', re.I),
    re.compile(r'you\s+are\s+(now|a)\s+', re.I),
    re.compile(r'system\s*:', re.I),
    re.compile(r'\[.*?system.*?\]', re.I),
]

def sanitize_prompt(text: str) -> str:
    """Sanitize user-supplied custom_prompt to prevent prompt injection.
    
    Redacts common injection patterns like 'ignore previous instructions',
    'you are now a', 'system:', and '[system]' markers.
    """
    if not text or not isinstance(text, str):
        return text or ""
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text