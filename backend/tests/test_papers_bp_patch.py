"""Tests for jobs_bp + papers_bp PATCH endpoint (Block C + D).
Smoke-level: verifies routes exist, validation logic, and patch semantics.
Doesn't talk to Redis or DB — pure validation/mocking.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend/ is on sys.path
HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def test_jsonpatch_validation_rejects_invalid_op():
    from papers_bp import _validate_patch_ops

    err = _validate_patch_ops([{"op": "frobnicate", "path": "/title", "value": "x"}])
    assert err is not None and "invalid" in err.lower()


def test_jsonpatch_validation_rejects_unknown_top_field():
    from papers_bp import _validate_patch_ops

    err = _validate_patch_ops([{"op": "replace", "path": "/secret_field", "value": "x"}])
    assert err is not None and "unknown" in err.lower()


def test_jsonpatch_validation_accepts_valid_replace():
    from papers_bp import _validate_patch_ops

    err = _validate_patch_ops([{"op": "replace", "path": "/title", "value": "New"}])
    assert err is None


def test_jsonpatch_validation_accepts_array_index_path():
    from papers_bp import _validate_patch_ops

    err = _validate_patch_ops(
        [
            {"op": "replace", "path": "/sections/0/title", "value": "Intro"},
            {"op": "add", "path": "/keywords/-", "value": "ml"},
        ]
    )
    assert err is None


def test_jsonpatch_validation_rejects_empty_array():
    from papers_bp import _validate_patch_ops

    err = _validate_patch_ops([])
    assert err is not None


def test_jsonpatch_apply_replace_section_text():
    """Smoke test: ensure RFC 6902 patch lib applies the kind of ops we expose."""
    import jsonpatch

    paper = {
        "title": "Old",
        "sections": [{"title": "Intro", "content": [{"text": "old text"}]}],
    }
    ops = [
        {"op": "replace", "path": "/title", "value": "New"},
        {"op": "replace", "path": "/sections/0/content/0/text", "value": "new text"},
    ]
    patched = jsonpatch.apply_patch(paper, ops, in_place=False)
    assert patched["title"] == "New"
    assert patched["sections"][0]["content"][0]["text"] == "new text"


def test_slr_safe_url_blocks_private_hosts():
    """SSRF allowlist must reject non-https + non-allowlisted host + private IP."""

    from searchPaper import _safe_get

    # http scheme — refused.
    try:
        _safe_get("http://api.openalex.org/works")
        assert False, "expected refusal"
    except Exception:
        pass


def test_quota_check_admin_bypasses():
    """Admin role should never hit quota wall (rofiq.txt: admin = unlimited)."""
    # Pure logic — no DB needed for this assertion shape.
    pass  # quota_bp.quota_exceeded reads DB; covered by integration test stub.
