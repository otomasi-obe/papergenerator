"""
Integration Tests: File Upload Operations
==========================================
Test complete file upload flows including upload, list, preview, serve, and delete.
Covers all file types, security validation, and edge cases.
"""
import io
from pathlib import Path

import pytest

from database.models import PaperFile, db
from tools.editor.utils import upload_folder

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_pdf_bytes():
    """Generate minimal valid PDF file."""
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000214 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
308
%%EOF
"""


@pytest.fixture
def sample_docx_bytes():
    """Generate minimal valid DOCX file (ZIP format)."""
    import io as io_module
    import zipfile

    buffer = io_module.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>''')

        zf.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''')

        zf.writestr('word/document.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:t>Test DOCX content with tables</w:t></w:r></w:p>
<w:tbl>
<w:tr><w:tc><w:p><w:r><w:t>Cell 1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Cell 2</w:t></w:r></w:p></w:tc></w:tr>
</w:tbl>
</w:body>
</w:document>''')

    return buffer.getvalue()


@pytest.fixture
def sample_txt_bytes():
    """Generate text file."""
    return b"This is a test text file.\nLine 2 of content.\nLine 3 of content."


@pytest.fixture
def sample_md_bytes():
    """Generate markdown file."""
    return b"# Test Markdown\n\nThis is **bold** and this is *italic*.\n\n## Section 2\n\nSome content."


@pytest.fixture
def sample_csv_bytes():
    """Generate CSV file."""
    return b"Name,Age,City\nJohn,30,NYC\nJane,25,LA\nBob,35,Chicago"


@pytest.fixture
def fake_pdf_bytes():
    """Generate fake PDF (text file with .pdf extension) for magic bytes test."""
    return b"This is not a real PDF file, just plain text."


@pytest.fixture
def large_file_bytes():
    """Generate file larger than 30MB limit."""
    return b"X" * (31 * 1024 * 1024)


# ── Test Classes ─────────────────────────────────────────────────────────────


class TestUploadFlow:
    """Test file upload flows with various file types."""

    def test_upload_single_pdf_success(self, client, test_user, test_paper, sample_pdf_bytes, auth_headers):
        """Test uploading single PDF file successfully."""
        data = {
            'files': (io.BytesIO(sample_pdf_bytes), 'test.pdf')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert len(json_data['files']) == 1
        assert json_data['files'][0]['ext'] == '.pdf'
        assert json_data['files'][0]['original_name'] == 'test.pdf'

        file_entry = PaperFile.query.filter_by(paper_id=test_paper.id).first()
        assert file_entry is not None
        assert file_entry.ext == '.pdf'
        assert file_entry.size_bytes == len(sample_pdf_bytes)

        filepath = Path(upload_folder()) / file_entry.file_path
        assert filepath.exists()
        assert filepath.read_bytes() == sample_pdf_bytes

    def test_upload_multiple_files_mixed_types(self, client, test_user, test_paper,
                                                sample_pdf_bytes, sample_docx_bytes, sample_txt_bytes, auth_headers):
        """Test uploading multiple files of different types."""
        data = {
            'files': [
                (io.BytesIO(sample_pdf_bytes), 'doc1.pdf'),
                (io.BytesIO(sample_docx_bytes), 'doc2.docx'),
                (io.BytesIO(sample_txt_bytes), 'notes.txt')
            ]
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert len(json_data['files']) == 3

        extensions = {f['ext'] for f in json_data['files']}
        assert extensions == {'.pdf', '.docx', '.txt'}

        file_count = PaperFile.query.filter_by(paper_id=test_paper.id).count()
        assert file_count == 3

    def test_upload_docx_with_tables(self, client, test_user, test_paper, sample_docx_bytes, auth_headers):
        """Test DOCX upload with table content extraction."""
        data = {
            'files': (io.BytesIO(sample_docx_bytes), 'table_doc.docx')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True

        file_entry = PaperFile.query.filter_by(paper_id=test_paper.id).first()
        assert file_entry is not None
        assert 'Test DOCX content' in file_entry.extracted_text or 'Cell' in file_entry.extracted_text

    def test_upload_csv_file(self, client, test_user, test_paper, sample_csv_bytes, auth_headers):
        """Test CSV file upload and extraction."""
        data = {
            'files': (io.BytesIO(sample_csv_bytes), 'data.csv')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True

        file_entry = PaperFile.query.filter_by(paper_id=test_paper.id).first()
        assert file_entry is not None
        assert 'Name,Age,City' in file_entry.extracted_text

    def test_upload_markdown_file(self, client, test_user, test_paper, sample_md_bytes, auth_headers):
        """Test markdown file upload."""
        data = {
            'files': (io.BytesIO(sample_md_bytes), 'readme.md')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True

        file_entry = PaperFile.query.filter_by(paper_id=test_paper.id).first()
        assert file_entry is not None
        assert 'Test Markdown' in file_entry.extracted_text

    def test_upload_file_size_limit(self, client, test_user, test_paper, large_file_bytes, auth_headers):
        """Test file size limit enforcement (>30MB rejected)."""
        data = {
            'files': (io.BytesIO(large_file_bytes), 'huge.pdf')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert len(json_data['files']) == 0
        assert len(json_data['warnings']) > 0
        assert any('30MB' in w or 'limit' in w for w in json_data['warnings'])

    def test_upload_invalid_extension(self, client, test_user, test_paper, auth_headers):
        """Test uploading file with invalid extension (.exe)."""
        data = {
            'files': (io.BytesIO(b'fake executable'), 'virus.exe')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert len(json_data['files']) == 0
        assert len(json_data['warnings']) > 0
        assert any('tidak didukung' in w or 'format' in w for w in json_data['warnings'])

    def test_upload_text_file(self, client, test_user, test_paper, sample_txt_bytes, auth_headers):
        """Test plain text file upload."""
        data = {
            'files': (io.BytesIO(sample_txt_bytes), 'notes.txt')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert len(json_data['files']) == 1

        file_entry = PaperFile.query.filter_by(paper_id=test_paper.id).first()
        assert 'test text file' in file_entry.extracted_text


class TestSecurityValidation:
    """Test security and validation features."""

    def test_upload_magic_bytes_mismatch(self, client, test_user, test_paper, fake_pdf_bytes, auth_headers):
        """Test magic bytes validation - text file renamed to .pdf should be rejected."""
        data = {
            'files': (io.BytesIO(fake_pdf_bytes), 'fake.pdf')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert len(json_data['files']) == 0
        assert len(json_data['warnings']) > 0
        assert any('konten' in w or 'berbahaya' in w for w in json_data['warnings'])

    def test_upload_empty_file(self, client, test_user, test_paper, auth_headers):
        """Test uploading empty file (0 bytes)."""
        data = {
            'files': (io.BytesIO(b''), 'empty.txt')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert len(json_data['files']) == 0
        assert len(json_data['warnings']) > 0
        assert any('kosong' in w for w in json_data['warnings'])

    def test_upload_without_auth(self, client, test_paper, sample_pdf_bytes):
        """Test uploading without authentication returns 401."""
        data = {
            'files': (io.BytesIO(sample_pdf_bytes), 'test.pdf')
        }

        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data=data,
            content_type='multipart/form-data'
        )

        assert response.status_code == 401

    def test_upload_to_other_user_paper(self, client, test_user, other_user, sample_pdf_bytes, auth_headers):
        """Test user cannot upload to another user's paper."""
        from database.models import Paper

        with client.application.app_context():
            other_paper = Paper(
                id='other-paper-1',
                user_id=other_user.id,
                title='Other User Paper',
                data={'title': 'Other'}
            )
            db.session.add(other_paper)
            db.session.commit()

        data = {
            'files': (io.BytesIO(sample_pdf_bytes), 'test.pdf')
        }

        response = client.post(
            '/api/papers/other-paper-1/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 404

    def test_upload_invalid_paper_id(self, client, test_user, sample_pdf_bytes, auth_headers):
        """Test uploading to non-existent paper returns 404."""
        data = {
            'files': (io.BytesIO(sample_pdf_bytes), 'test.pdf')
        }

        response = client.post(
            '/api/papers/nonexistent-paper/files',
            data=data,
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 404


class TestListRetrieve:
    """Test file listing and retrieval operations."""

    def test_list_files_after_upload(self, client, test_user, test_paper,
                                     sample_pdf_bytes, sample_txt_bytes, sample_md_bytes, auth_headers):
        """Test listing files returns all uploaded files in correct order."""
        for filename, content in [('doc1.pdf', sample_pdf_bytes),
                                   ('doc2.txt', sample_txt_bytes),
                                   ('doc3.md', sample_md_bytes)]:
            client.post(
                f'/api/papers/{test_paper.id}/files',
                data={'files': (io.BytesIO(content), filename)},
                headers=auth_headers,
                content_type='multipart/form-data'
            )

        response = client.get(f'/api/papers/{test_paper.id}/files', headers=auth_headers)

        assert response.status_code == 200
        json_data = response.get_json()
        assert len(json_data['files']) == 3

        original_names = [f['original_name'] for f in json_data['files']]
        assert 'doc1.pdf' in original_names
        assert 'doc2.txt' in original_names
        assert 'doc3.md' in original_names

    def test_list_files_empty_paper(self, client, test_user, test_paper, auth_headers):
        """Test listing files for paper with no uploads returns empty array."""
        response = client.get(f'/api/papers/{test_paper.id}/files', headers=auth_headers)

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['files'] == []

    def test_preview_file_with_extracted_text(self, client, test_user, test_paper, sample_pdf_bytes, auth_headers):
        """Test preview endpoint returns extracted text."""
        upload_response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data={'files': (io.BytesIO(sample_pdf_bytes), 'test.pdf')},
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        file_id = upload_response.get_json()['files'][0]['id']

        response = client.get(f'/api/papers/{test_paper.id}/files/{file_id}/preview', headers=auth_headers)

        assert response.status_code == 200
        json_data = response.get_json()
        assert 'text' in json_data
        assert json_data['ext'] == '.pdf'
        assert json_data['original_name'] == 'test.pdf'

    def test_serve_raw_file_with_bearer_auth(self, client, test_user, test_paper, sample_pdf_bytes, auth_headers):
        """Test serving raw file with Bearer token authentication."""
        upload_response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data={'files': (io.BytesIO(sample_pdf_bytes), 'test.pdf')},
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        file_id = upload_response.get_json()['files'][0]['id']

        response = client.get(f'/api/papers/{test_paper.id}/files/{file_id}/raw', headers=auth_headers)

        assert response.status_code == 200
        assert response.data == sample_pdf_bytes
        assert response.content_type == 'application/pdf'


class TestDeleteFlow:
    """Test file deletion operations."""

    def test_delete_file_success(self, client, test_user, test_paper, sample_pdf_bytes, auth_headers):
        """Test deleting file removes from DB and disk."""
        upload_response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data={'files': (io.BytesIO(sample_pdf_bytes), 'test.pdf')},
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        file_id = upload_response.get_json()['files'][0]['id']

        file_entry = db.session.get(PaperFile, file_id)
        filepath = Path(upload_folder()) / file_entry.file_path
        assert filepath.exists()

        response = client.delete(f'/api/papers/{test_paper.id}/files/{file_id}', headers=auth_headers)

        assert response.status_code == 200
        assert response.get_json()['success'] is True

        assert db.session.get(PaperFile, file_id) is None
        assert not filepath.exists()

    def test_delete_file_not_found(self, client, test_user, test_paper, auth_headers):
        """Test deleting non-existent file returns 404."""
        response = client.delete(f'/api/papers/{test_paper.id}/files/99999', headers=auth_headers)

        assert response.status_code == 404

    def test_delete_file_other_user(self, client, test_user, other_user, sample_pdf_bytes, auth_headers):
        """Test user cannot delete another user's file."""
        from database.models import Paper

        with client.application.app_context():
            other_paper = Paper(
                id='other-paper-2',
                user_id=other_user.id,
                title='Other User Paper',
                data={'title': 'Other'}
            )
            db.session.add(other_paper)
            db.session.commit()

            other_file = PaperFile(
                paper_id='other-paper-2',
                user_id=other_user.id,
                filename='test.pdf',
                original_name='test.pdf',
                ext='.pdf',
                size_bytes=100,
                file_path='other-paper-2/files/test.pdf',
                extracted_text=''
            )
            db.session.add(other_file)
            db.session.commit()
            other_file_id = other_file.id

        response = client.delete(f'/api/papers/other-paper-2/files/{other_file_id}', headers=auth_headers)

        assert response.status_code == 404


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_list_files_unauthorized(self, client, test_paper):
        """Test listing files without auth returns 401."""
        response = client.get(f'/api/papers/{test_paper.id}/files')

        assert response.status_code == 401

    def test_preview_file_unauthorized(self, client, test_paper):
        """Test preview without auth returns 401."""
        response = client.get(f'/api/papers/{test_paper.id}/files/1/preview')

        assert response.status_code == 401

    def test_delete_file_unauthorized(self, client, test_paper):
        """Test delete without auth returns 401."""
        response = client.delete(f'/api/papers/{test_paper.id}/files/1')

        assert response.status_code == 401

    def test_upload_no_files_provided(self, client, test_user, test_paper, auth_headers):
        """Test upload with no files returns 400."""
        response = client.post(
            f'/api/papers/{test_paper.id}/files',
            data={},
            headers=auth_headers,
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
