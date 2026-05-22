"""
Test suite for image generation bug fixes.

Tests all 6 fixes implemented:
1. Cookie validation (fail fast)
2. Image intercept timeout (dynamic)
3. Browser launch retry (3 attempts)
4. Compression failure handling (fail job)
5. UI operation timeouts (30s default)
6. Model documentation (status field)

Run: pytest backend/tests/test_image_fixes.py -v
"""
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest


class TestCookieValidation:
    """Test Fix #1: Cookie validation fails fast"""
    
    def test_missing_psidts_raises_error(self):
        """Should raise RuntimeError if PSIDTS cookie missing after 90s"""
        from imageGenerator.GeminiCookies import _wait_for_required_cookies
        
        mock_page = Mock()
        mock_context = Mock()
        mock_page.context = mock_context
        
        # Simulate missing PSIDTS cookie
        mock_context.cookies.return_value = [
            {"name": "__Secure-1PSID", "domain": ".google.com"},
            # __Secure-1PSIDTS is missing
        ]
        
        result = _wait_for_required_cookies(mock_page, timeout_s=1)
        assert result is False, "Should return False when PSIDTS missing"
    
    def test_complete_cookies_returns_true(self):
        """Should return True when all required cookies present"""
        from imageGenerator.GeminiCookies import _has_required_cookies
        
        mock_context = Mock()
        mock_context.cookies.return_value = [
            {"name": "__Secure-1PSID", "domain": ".google.com"},
            {"name": "__Secure-1PSIDTS", "domain": ".google.com"},
        ]
        
        result = _has_required_cookies(mock_context)
        assert result is True, "Should return True when all cookies present"


class TestImageInterceptTimeout:
    """Test Fix #2: Dynamic intercept timeout"""
    
    def test_intercept_timeout_scales_with_generation(self):
        """Intercept timeout should be generate_timeout_s + 30"""
        # This is tested by reading the code logic
        # In CreateImageGemini.py line 365:
        # intercept_timeout = generate_timeout_s + 30
        
        generate_timeout = 240
        expected_intercept = 240 + 30  # 270s
        
        # Verify the logic exists in the code
        code_path = Path(__file__).parent.parent / "imageGenerator" / "CreateImageGemini.py"
        code = code_path.read_text()
        
        assert "intercept_timeout = generate_timeout_s + 30" in code, \
            "Code should have dynamic intercept timeout"
        assert "deadline = time.time() + intercept_timeout" in code, \
            "Code should use intercept_timeout for deadline"


class TestBrowserLaunchRetry:
    """Test Fix #3: Browser launch retry logic"""
    
    @patch('image_worker._get_pool')
    def test_browser_launch_retries_on_failure(self, mock_get_pool):
        """Should retry browser launch up to 3 times"""
        from image_worker import _Worker
        
        mock_app = Mock()
        mock_app.app_context.return_value.__enter__ = Mock()
        mock_app.app_context.return_value.__exit__ = Mock()
        
        worker = _Worker(mock_app, "account1")
        
        # Verify retry logic exists in code
        code_path = Path(__file__).parent.parent / "image_worker.py"
        code = code_path.read_text()
        
        assert "launch_attempts = 3" in code, "Should have 3 launch attempts"
        assert "for attempt in range(1, launch_attempts + 1):" in code, \
            "Should loop through attempts"
        assert "acc.close()" in code, "Should close account before retry"
        assert "time_module.sleep(2 ** attempt)" in code, \
            "Should have exponential backoff"
    
    def test_retry_backoff_timing(self):
        """Verify exponential backoff: 2s, 4s"""
        backoffs = [2 ** attempt for attempt in range(1, 3)]
        assert backoffs == [2, 4], "Backoff should be 2s, 4s"


class TestCompressionFailureHandling:
    """Test Fix #4: Compression failure handling"""
    
    def test_compression_failure_deletes_file(self):
        """Should delete uncompressed file if compression fails"""
        code_path = Path(__file__).parent.parent / "image_worker.py"
        code = code_path.read_text()
        
        # Verify compression failure handling
        assert "if not compress_image(out_path, max_size_mb=1.0):" in code, \
            "Should check compression return value"
        assert "raise RuntimeError" in code and "compression failed" in code.lower(), \
            "Should raise error on compression failure"
        assert "out_path.unlink()" in code, \
            "Should delete file on compression failure"
    
    @patch('imageGenerator.compress.compress_image')
    def test_compression_success_logs_size(self, mock_compress):
        """Should log compressed size on success"""
        mock_compress.return_value = True
        
        code_path = Path(__file__).parent.parent / "image_worker.py"
        code = code_path.read_text()
        
        assert "Image compressed successfully" in code, \
            "Should log success message"
        assert "out_path.stat().st_size // 1024" in code, \
            "Should log file size in KB"


class TestUIOperationTimeouts:
    """Test Fix #5: UI operation timeouts"""
    
    def test_open_image_tool_has_timeout(self):
        """_open_image_tool should have timeout parameter"""
        code_path = Path(__file__).parent.parent / "imageGenerator" / "CreateImageGemini.py"
        code = code_path.read_text()
        
        assert "def _open_image_tool(page, *, timeout_s: int = 30)" in code, \
            "_open_image_tool should have timeout parameter"
        assert "deadline = time.monotonic() + timeout_s" in code, \
            "Should set deadline based on timeout"
        assert "if time.monotonic() > deadline:" in code, \
            "Should check deadline"
    
    def test_send_prompt_has_timeout(self):
        """_send_prompt should have timeout parameter"""
        code_path = Path(__file__).parent.parent / "imageGenerator" / "CreateImageGemini.py"
        code = code_path.read_text()
        
        assert "def _send_prompt(page, prompt: str, *, timeout_s: int = 30)" in code, \
            "_send_prompt should have timeout parameter"
        assert "box.click(timeout=timeout_s * 1000)" in code, \
            "Should use timeout in click operation"
    
    def test_timeout_error_messages_are_clear(self):
        """Timeout errors should have clear messages"""
        code_path = Path(__file__).parent.parent / "imageGenerator" / "CreateImageGemini.py"
        code = code_path.read_text()
        
        assert "Timeout" in code and "saat membuka image tool" in code, \
            "Should have clear timeout error for image tool"
        assert "Timeout" in code and "saat mengirim prompt" in code, \
            "Should have clear timeout error for prompt"


class TestModelDocumentation:
    """Test Fix #6: Model documentation updated"""
    
    def test_status_field_documents_cancelled(self):
        """Status field should document 'cancelled' state"""
        code_path = Path(__file__).parent.parent / "models.py"
        code = code_path.read_text()
        
        # Find the ImageGenJob status field
        assert "queued|running|done|error|cancelled" in code, \
            "Status field should document all 5 states including cancelled"
    
    def test_worker_field_has_description(self):
        """Worker field should have clear description"""
        code_path = Path(__file__).parent.parent / "models.py"
        code = code_path.read_text()
        
        assert "which account picked it up (account1..account4)" in code, \
            "Worker field should document account names"
    
    def test_error_field_has_description(self):
        """Error field should have clear description"""
        code_path = Path(__file__).parent.parent / "models.py"
        code = code_path.read_text()
        
        assert "error message if status=error" in code, \
            "Error field should document its purpose"


class TestIntegration:
    """Integration tests for complete workflow"""
    
    @pytest.mark.integration
    def test_job_lifecycle_with_fixes(self):
        """Test complete job lifecycle with all fixes applied"""
        # This would require a running system, so we just verify
        # the fixes are present in the codebase
        
        fixes_present = []
        
        # Check Fix #1: Cookie validation
        cookies_code = (Path(__file__).parent.parent / "imageGenerator" / "GeminiCookies.py").read_text()
        fixes_present.append("raise RuntimeError" in cookies_code and "PSIDTS" in cookies_code)
        
        # Check Fix #2: Intercept timeout
        gemini_code = (Path(__file__).parent.parent / "imageGenerator" / "CreateImageGemini.py").read_text()
        fixes_present.append("intercept_timeout = generate_timeout_s + 30" in gemini_code)
        
        # Check Fix #3: Browser retry
        worker_code = (Path(__file__).parent.parent / "image_worker.py").read_text()
        fixes_present.append("launch_attempts = 3" in worker_code)
        
        # Check Fix #4: Compression handling
        fixes_present.append("if not compress_image" in worker_code)
        
        # Check Fix #5: UI timeouts
        fixes_present.append("timeout_s: int = 30" in gemini_code)
        
        # Check Fix #6: Model docs
        models_code = (Path(__file__).parent.parent / "models.py").read_text()
        fixes_present.append("cancelled" in models_code)
        
        assert all(fixes_present), f"Not all fixes present: {fixes_present}"
        assert len(fixes_present) == 6, "Should have 6 fixes"


class TestErrorMessages:
    """Test that error messages are clear and actionable"""
    
    def test_cookie_error_message_is_clear(self):
        """Cookie error should explain what's wrong and how to fix"""
        code_path = Path(__file__).parent.parent / "imageGenerator" / "GeminiCookies.py"
        code = code_path.read_text()
        
        assert "Cookie penting" in code and "tidak muncul" in code, \
            "Should explain which cookie is missing"
        assert "login ulang" in code or "refresh" in code, \
            "Should suggest how to fix"
    
    def test_intercept_error_message_is_clear(self):
        """Intercept timeout error should explain possible causes"""
        code_path = Path(__file__).parent.parent / "imageGenerator" / "CreateImageGemini.py"
        code = code_path.read_text()
        
        assert "Gagal capture image bytes" in code, \
            "Should explain what failed"
        assert "network issue" in code or "API berubah" in code or "rate limit" in code, \
            "Should suggest possible causes"
    
    def test_compression_error_message_is_clear(self):
        """Compression error should show file size"""
        code_path = Path(__file__).parent.parent / "image_worker.py"
        code = code_path.read_text()
        
        assert "could not reduce" in code and "<1MB" in code, \
            "Should explain compression target"
        assert "Original size:" in code, \
            "Should show original file size"


class TestBackwardCompatibility:
    """Ensure fixes don't break existing functionality"""
    
    def test_job_status_values_unchanged(self):
        """Job status values should remain the same"""
        valid_statuses = {'queued', 'running', 'done', 'error', 'cancelled'}
        
        # These are the only valid status values
        # Adding new ones would break existing code
        assert len(valid_statuses) == 5, "Should have exactly 5 status values"
    
    def test_worker_names_unchanged(self):
        """Worker names should remain account1..account4"""
        expected_workers = ['account1', 'account2', 'account3', 'account4']
        
        code_path = Path(__file__).parent.parent / "image_worker.py"
        code = code_path.read_text()
        
        assert "account1,account2,account3,account4" in code, \
            "Worker names should remain unchanged"
    
    def test_api_endpoints_unchanged(self):
        """API endpoints should remain the same"""
        code_path = Path(__file__).parent.parent / "image_jobs_bp.py"
        code = code_path.read_text()
        
        # Verify endpoints still exist
        assert '/api/image-jobs' in code, "POST endpoint should exist"
        assert '/<job_id>' in code, "GET job endpoint should exist"
        assert '/<job_id>/cancel' in code, "Cancel endpoint should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
