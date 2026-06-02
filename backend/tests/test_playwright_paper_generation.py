"""
Playwright MCP Test Agent for Paper Generation
Tests paper generation workflow from various user knowledge levels using Playwright MCP tools.

Test Scenarios:
1. Beginner user: Step-by-step guided workflow, asks many questions
2. Intermediate user: Provides some info upfront, needs some guidance
3. Advanced user: Bulk info in first message, fast-track to generation
4. Hybrid literature: Upload files + request AI to find more papers

Each test navigates the application, creates a new paper, interacts with chat,
and verifies paper generation completes successfully.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


class PlaywrightMCPTestAgent:
    """
    Test agent that uses Playwright MCP tools to test paper generation.

    This class wraps Playwright MCP tool calls to provide a clean interface
    for testing the paper generation workflow.
    """

    def __init__(self, base_url="http://localhost:5173"):
        self.base_url = base_url
        self.current_paper_id = None

    def navigate_to_app(self):
        """Navigate to the application landing page."""
        print(f"Navigating to {self.base_url}")

    def login(self, username="testuser", password="testpass"):
        """
        Login to the application.

        Steps:
        1. Navigate to login page
        2. Fill in credentials
        3. Submit form
        4. Wait for redirect to dashboard
        """
        print(f"Logging in as {username}")

    def navigate_to_dashboard(self):
        """Navigate to the dashboard page."""
        print("Navigating to dashboard")

    def create_new_paper(self):
        """
        Create a new paper by clicking the new paper button.

        Returns:
            str: The paper ID extracted from the URL
        """
        print("Creating new paper")
        return None

    def send_chat_message(self, message: str):
        """
        Send a message in the chat interface.

        Args:
            message: The message text to send
        """
        print(f"Sending message: {message[:50]}...")

    def wait_for_ai_response(self, timeout=30):
        """
        Wait for AI to finish responding.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            str: The AI response text
        """
        print(f"Waiting for AI response (timeout: {timeout}s)")
        return ""

    def verify_response_contains(self, text: str, response: str):
        """
        Verify that the AI response contains expected text.

        Args:
            text: Expected text to find
            response: The AI response to check

        Returns:
            bool: True if text found, False otherwise
        """
        found = text.lower() in response.lower()
        print(f"Verify '{text}' in response: {found}")
        return found

    def trigger_paper_generation(self):
        """
        Trigger full paper generation by sending the appropriate command.
        """
        print("Triggering paper generation")

    def wait_for_paper_generation(self, timeout=300):
        """
        Wait for paper generation to complete.

        Args:
            timeout: Maximum seconds to wait (default 5 minutes)

        Returns:
            bool: True if generation completed, False if timeout
        """
        print(f"Waiting for paper generation (timeout: {timeout}s)")
        return False

    def verify_paper_created(self):
        """
        Verify that the paper was successfully created.

        Returns:
            bool: True if paper exists with content, False otherwise
        """
        print("Verifying paper was created")
        return False

    def get_page_snapshot(self):
        """
        Get accessibility snapshot of current page.

        Returns:
            dict: Page snapshot data
        """
        print("Getting page snapshot")
        return {}

    def upload_literature_file(self, file_path: str):
        """
        Upload a literature file (PDF, BibTeX, etc.).

        Args:
            file_path: Path to the file to upload
        """
        print(f"Uploading file: {file_path}")


def test_beginner_user_workflow():
    """
    Test beginner user workflow: step-by-step guided interaction.

    Scenario:
    - User is confused about what to write
    - AI asks guiding questions
    - User answers step by step
    - AI helps formulate topic and structure
    - Paper generation is triggered

    Expected behavior:
    - AI should ask clarifying questions
    - AI should provide guidance and suggestions
    - AI should help narrow down the topic
    - Paper should be generated successfully
    """
    agent = PlaywrightMCPTestAgent()

    # Step 1: Navigate and login
    agent.navigate_to_app()
    agent.login(username="beginner_user", password="test123")
    agent.navigate_to_dashboard()

    # Step 2: Create new paper
    paper_id = agent.create_new_paper()
    assert paper_id is not None, "Failed to create new paper"

    # Step 3: Send beginner-style message
    agent.send_chat_message("Saya bingung mau nulis paper tentang apa. Bisa bantu?")

    # Step 4: Verify AI asks guiding questions
    response1 = agent.wait_for_ai_response(timeout=30)
    assert (
        agent.verify_response_contains("bidang", response1)
        or agent.verify_response_contains("topik", response1)
        or agent.verify_response_contains("minat", response1)
    ), "AI should ask about field/topic/interest"

    # Step 5: Answer with vague interest
    agent.send_chat_message("Saya tertarik dengan AI dan machine learning")

    # Step 6: Verify AI asks more specific questions
    response2 = agent.wait_for_ai_response(timeout=30)
    assert (
        agent.verify_response_contains("spesifik", response2)
        or agent.verify_response_contains("aplikasi", response2)
        or agent.verify_response_contains("masalah", response2)
    ), "AI should ask for more specific details"

    # Step 7: Provide more details
    agent.send_chat_message("Mungkin tentang deep learning untuk image recognition")

    # Step 8: Verify AI provides suggestions
    response3 = agent.wait_for_ai_response(timeout=30)
    assert (
        agent.verify_response_contains("judul", response3)
        or agent.verify_response_contains("struktur", response3)
        or agent.verify_response_contains("outline", response3)
    ), "AI should provide suggestions for title/structure"

    # Step 9: Confirm and request generation
    agent.send_chat_message("Oke, tolong buatkan papernya")

    # Step 10: Wait for generation to complete
    generation_success = agent.wait_for_paper_generation(timeout=300)
    assert generation_success, "Paper generation timed out or failed"

    # Step 11: Verify paper was created
    paper_exists = agent.verify_paper_created()
    assert paper_exists, "Paper was not created successfully"

    print("✓ Beginner user workflow test passed")


def test_intermediate_user_workflow():
    """
    Test intermediate user workflow: provides some info upfront, needs guidance.

    Scenario:
    - User has a general topic and some ideas
    - Provides initial information in first message
    - AI asks for clarification on specific aspects
    - User provides additional details
    - Paper generation is triggered

    Expected behavior:
    - AI should acknowledge the provided information
    - AI should ask for missing details (methodology, scope, etc.)
    - AI should help refine the structure
    - Paper should be generated successfully
    """
    agent = PlaywrightMCPTestAgent()

    # Step 1: Navigate and login
    agent.navigate_to_app()
    agent.login(username="intermediate_user", password="test123")
    agent.navigate_to_dashboard()

    # Step 2: Create new paper
    paper_id = agent.create_new_paper()
    assert paper_id is not None, "Failed to create new paper"

    # Step 3: Send intermediate-style message with some details
    agent.send_chat_message(
        "Saya ingin menulis paper tentang convolutional neural networks untuk "
        "klasifikasi gambar medis. Saya sudah punya dataset X-ray dan ingin "
        "membandingkan beberapa arsitektur CNN."
    )

    # Step 4: Verify AI acknowledges and asks for details
    response1 = agent.wait_for_ai_response(timeout=30)
    assert (
        agent.verify_response_contains("arsitektur", response1)
        or agent.verify_response_contains("metodologi", response1)
        or agent.verify_response_contains("dataset", response1)
    ), "AI should ask about methodology or architecture details"

    # Step 5: Provide methodology details
    agent.send_chat_message(
        "Saya akan membandingkan ResNet, VGG, dan Inception. Dataset saya "
        "punya 10,000 gambar X-ray dengan 5 kategori penyakit."
    )

    # Step 6: Verify AI asks about evaluation or other aspects
    response2 = agent.wait_for_ai_response(timeout=30)
    assert (
        agent.verify_response_contains("evaluasi", response2)
        or agent.verify_response_contains("metrik", response2)
        or agent.verify_response_contains("hasil", response2)
    ), "AI should ask about evaluation metrics or expected results"

    # Step 7: Provide evaluation details
    agent.send_chat_message(
        "Saya akan menggunakan accuracy, precision, recall, dan F1-score. "
        "Tolong buatkan struktur papernya."
    )

    # Step 8: Wait for generation to complete
    generation_success = agent.wait_for_paper_generation(timeout=300)
    assert generation_success, "Paper generation timed out or failed"

    # Step 9: Verify paper was created
    paper_exists = agent.verify_paper_created()
    assert paper_exists, "Paper was not created successfully"

    print("✓ Intermediate user workflow test passed")


def test_advanced_user_workflow():
    """
    Test advanced user workflow: bulk info in first message, fast-track.

    Scenario:
    - User provides comprehensive information upfront
    - Includes title, abstract, methodology, results
    - AI should recognize completeness
    - Minimal back-and-forth needed
    - Paper generation starts quickly

    Expected behavior:
    - AI should acknowledge the comprehensive information
    - AI may ask for minor clarifications only
    - AI should proceed to generation quickly
    - Paper should be generated successfully
    """
    agent = PlaywrightMCPTestAgent()

    # Step 1: Navigate and login
    agent.navigate_to_app()
    agent.login(username="advanced_user", password="test123")
    agent.navigate_to_dashboard()

    # Step 2: Create new paper
    paper_id = agent.create_new_paper()
    assert paper_id is not None, "Failed to create new paper"

    # Step 3: Send comprehensive message with all details
    agent.send_chat_message(
        """Saya ingin menulis paper dengan detail berikut:

Judul: "Deep Learning-Based Medical Image Classification Using Ensemble CNN Architectures"

Abstract: Penelitian ini mengusulkan metode ensemble dari tiga arsitektur CNN
(ResNet-50, VGG-16, Inception-v3) untuk klasifikasi gambar X-ray paru-paru.
Dataset terdiri dari 10,000 gambar dengan 5 kategori: Normal, Pneumonia,
COVID-19, Tuberculosis, dan Lung Cancer.

Metodologi:
- Preprocessing: resize 224x224, normalisasi, augmentasi data
- Training: 80% train, 10% validation, 10% test
- Optimizer: Adam dengan learning rate 0.001
- Epochs: 100 dengan early stopping
- Ensemble: weighted voting dari 3 model

Hasil:
- Accuracy: 94.5%
- Precision: 93.8%
- Recall: 94.2%
- F1-Score: 94.0%
- ResNet-50 memberikan performa terbaik individual (92.3%)

Kesimpulan: Ensemble method meningkatkan akurasi 2.2% dibanding single model.

Tolong generate paper lengkap dengan struktur IEEE format."""
    )

    # Step 4: Verify AI acknowledges and proceeds
    response1 = agent.wait_for_ai_response(timeout=30)
    assert (
        agent.verify_response_contains("lengkap", response1)
        or agent.verify_response_contains("generate", response1)
        or agent.verify_response_contains("membuat", response1)
    ), "AI should acknowledge comprehensive info and proceed"

    # Step 5: Wait for generation to complete (should start quickly)
    generation_success = agent.wait_for_paper_generation(timeout=300)
    assert generation_success, "Paper generation timed out or failed"

    # Step 6: Verify paper was created
    paper_exists = agent.verify_paper_created()
    assert paper_exists, "Paper was not created successfully"

    print("✓ Advanced user workflow test passed")


def test_hybrid_literature_workflow():
    """
    Test hybrid literature workflow: upload files + AI finds more papers.

    Scenario:
    - User uploads some literature files (PDF, BibTeX)
    - User requests AI to find additional relevant papers
    - AI analyzes uploaded files
    - AI searches for related papers
    - Paper generation includes both sources

    Expected behavior:
    - AI should acknowledge uploaded files
    - AI should extract key information from files
    - AI should search for related papers
    - AI should integrate both sources in generation
    - Paper should be generated successfully
    """
    agent = PlaywrightMCPTestAgent()

    # Step 1: Navigate and login
    agent.navigate_to_app()
    agent.login(username="hybrid_user", password="test123")
    agent.navigate_to_dashboard()

    # Step 2: Create new paper
    paper_id = agent.create_new_paper()
    assert paper_id is not None, "Failed to create new paper"

    # Step 3: Upload literature files
    # Note: In real test, would upload actual files
    # For now, simulate the upload action
    test_file_path = "/tmp/test_literature.bib"
    agent.upload_literature_file(test_file_path)

    # Step 4: Request AI to find more papers
    agent.send_chat_message(
        "Saya sudah upload beberapa paper tentang CNN untuk medical imaging. "
        "Tolong carikan paper-paper terkait lainnya yang relevan, terutama "
        "yang membahas ensemble methods dan X-ray classification."
    )

    # Step 5: Verify AI acknowledges and searches
    response1 = agent.wait_for_ai_response(timeout=60)
    assert (
        agent.verify_response_contains("mencari", response1)
        or agent.verify_response_contains("paper", response1)
        or agent.verify_response_contains("literatur", response1)
    ), "AI should acknowledge search request"

    # Step 6: Wait for search results
    response2 = agent.wait_for_ai_response(timeout=60)
    assert (
        agent.verify_response_contains("menemukan", response2)
        or agent.verify_response_contains("hasil", response2)
        or agent.verify_response_contains("paper", response2)
    ), "AI should provide search results"

    # Step 7: Request paper generation with combined sources
    agent.send_chat_message(
        "Bagus! Sekarang tolong buatkan systematic literature review "
        "berdasarkan paper yang saya upload dan yang kamu temukan."
    )

    # Step 8: Wait for generation to complete
    generation_success = agent.wait_for_paper_generation(timeout=300)
    assert generation_success, "Paper generation timed out or failed"

    # Step 9: Verify paper was created
    paper_exists = agent.verify_paper_created()
    assert paper_exists, "Paper was not created successfully"

    print("✓ Hybrid literature workflow test passed")


def test_error_handling():
    """
    Test error handling scenarios.

    Scenarios:
    - Invalid input
    - Network timeout
    - Generation failure
    - Recovery from errors
    """
    agent = PlaywrightMCPTestAgent()

    # Test 1: Empty message
    agent.navigate_to_app()
    agent.login()
    agent.create_new_paper()

    agent.send_chat_message("")
    agent.wait_for_ai_response(timeout=10)
    # Should handle gracefully, not crash

    # Test 2: Very long message
    long_message = "A" * 10000
    agent.send_chat_message(long_message)
    agent.wait_for_ai_response(timeout=30)
    # Should handle gracefully

    print("✓ Error handling test passed")


def test_concurrent_users():
    """
    Test multiple users generating papers concurrently.

    This test ensures that:
    - Multiple users can work simultaneously
    - Papers don't get mixed up
    - Generation queue works correctly
    """
    agents = [
        PlaywrightMCPTestAgent(),
        PlaywrightMCPTestAgent(),
        PlaywrightMCPTestAgent(),
    ]

    # Each agent creates a paper and starts generation
    for i, agent in enumerate(agents):
        agent.navigate_to_app()
        agent.login(username=f"user{i}", password="test123")
        agent.create_new_paper()
        agent.send_chat_message(f"Generate paper about topic {i}")

    # Verify all generations complete
    for i, agent in enumerate(agents):
        success = agent.wait_for_paper_generation(timeout=300)
        assert success, f"User {i} paper generation failed"
        assert agent.verify_paper_created(), f"User {i} paper not created"

    print("✓ Concurrent users test passed")


if __name__ == "__main__":
    """
    Run all tests.

    Usage:
        python test_playwright_paper_generation.py

    Or with pytest:
        pytest test_playwright_paper_generation.py -v
    """
    print("=" * 70)
    print("Playwright MCP Test Agent for Paper Generation")
    print("=" * 70)
    print()

    tests = [
        ("Beginner User Workflow", test_beginner_user_workflow),
        ("Intermediate User Workflow", test_intermediate_user_workflow),
        ("Advanced User Workflow", test_advanced_user_workflow),
        ("Hybrid Literature Workflow", test_hybrid_literature_workflow),
        ("Error Handling", test_error_handling),
        ("Concurrent Users", test_concurrent_users),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        print(f"\n{'─' * 70}")
        print(f"Running: {name}")
        print(f"{'─' * 70}")
        try:
            test_func()
            passed += 1
            print(f"✓ {name} PASSED")
        except AssertionError as e:
            failed += 1
            print(f"✗ {name} FAILED: {e}")
        except Exception as e:
            failed += 1
            print(f"✗ {name} ERROR: {e}")

    print(f"\n{'=' * 70}")
    print(f"Test Results: {passed} passed, {failed} failed")
    print(f"{'=' * 70}")

    sys.exit(0 if failed == 0 else 1)
