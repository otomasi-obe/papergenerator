"""Integration test for PDF preview endpoint."""
import sys, json
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from papergenerator.backend.main import app, db, Paper
from papergenerator.backend.utils.database.models import User
from flask_jwt_extended import create_access_token
import tempfile

TEST_EMAIL = "test-pdf-preview@example.com"
TEST_PAPER_ID = "test-paper-pdf-123"
TEST_USER_ID = 9999

def create_test_user():
    with app.app_context():
        user = User.query.filter_by(email=TEST_EMAIL).first()
        if not user:
            user = User(email=TEST_EMAIL, password="test123")
            db.session.add(user)
            db.session.commit()
        return user.id

def create_test_paper(user_id: int):
    paper_data = {
        "title": "Test PDF Preview Paper",
        "journal": "IEEE",
        "authors": [{"name": "Test Author", "affiliation": "Test Uni", "location": "City", "email": "a@t.com"}],
        "abstract": "This is a test abstract.",
        "keywords": ["test", "pdf", "preview"],
        "sections": [
            {"title": "Introduction", "content": [{"id": "text", "text": "Test introduction."}]},
            {"title": "Methods", "content": [{"id": "text", "text": "Test methods."}]},
            {"title": "Results", "content": [{"id": "text", "text": "Test results."}]},
            {"title": "Conclusion", "content": [{"id": "text", "text": "Test conclusion."}]},
        ],
        "references": [{"text": "[1] J. Doe, 'Test', 2024."}],
        "language": "en",
    }
    paper = Paper.query.filter_by(id=TEST_PAPER_ID).first()
        # TODO: add user_id filter — test utility, not production
    if paper:
        paper.data = paper_data
    else:
        paper = Paper(id=TEST_PAPER_ID, user_id=user_id, data=paper_data)
        db.session.add(paper)
    db.session.commit()
    return paper

def test_pdf_preview():
    with app.app_context():
        user_id = create_test_user()
        paper = create_test_paper(user_id)
        token = create_access_token(identity=user_id)
        
    with app.test_client() as client:
        # Test PDF preview endpoint
        resp = client.post(
            f'/api/papers/{TEST_PAPER_ID}/pdf-preview',
            json={"paper_id": TEST_PAPER_ID, "journal": "IEEE"},
            headers={"Authorization": f"Bearer {token}"},
        )
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.get_json()}")
        
        if resp.status_code != 200:
            print("FAIL: PDF preview request failed")
            return False
        
        # Check if preview.pdf is accessible
        resp2 = client.get(
            f'/api/papers/{TEST_PAPER_ID}/preview.pdf',
            headers={"Authorization": f"Bearer {token}"},
        )
        print(f"PDF download status: {resp2.status_code}")
        print(f"Content-Type: {resp2.content_type}")
        
        if resp2.status_code != 200:
            print("FAIL: PDF download failed")
            return False
        
        # Check file was created at user/<user_id>/papers/<paper_id>/paper.pdf
        expected_path = Path(f"user/{user_id}/papers/{TEST_PAPER_ID}/paper.pdf")
        if expected_path.exists():
            size = expected_path.stat().st_size
            print(f"✅ PDF saved: {expected_path} ({size} bytes)")
            return True
        else:
            print(f"FAIL: PDF not at expected path: {expected_path}")
            return False

if __name__ == "__main__":
    success = test_pdf_preview()
    sys.exit(0 if success else 1)
