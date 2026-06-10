"""
Integration tests for Image API endpoints.

Tests cover:
- Image generation job lifecycle (POST/GET/Cancel)
- Image upload/download (POST/GET/DELETE)
- Image authorization and security
- Signed token generation and validation
- Edge cases and error handling

Cycle 34 - Image API Integration Tests
"""

import io

import pytest

from database.models import ImageGenJob, PaperImage, db


@pytest.fixture
def test_image_bytes():
    """Create minimal valid 1x1 transparent PNG (67 bytes)."""
    return (
        b'\x89PNG\r\n\x1a\n'
        b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
        b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
        b'\r\n-\xb4'
        b'\x00\x00\x00\x00IEND\xaeB`\x82'
    )


@pytest.fixture
def other_user_token(app, other_user):
    """Generate JWT access token for other_user."""
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(identity=str(other_user.id))
        return token


@pytest.fixture
def other_user_headers(other_user_token):
    """Generate authorization headers for other_user."""
    return {'Authorization': f'Bearer {other_user_token}'}


@pytest.fixture
def test_image_job(app, test_user, test_paper):
    """Create a test image generation job."""
    with app.app_context():
        job = ImageGenJob(
            id='test-job-001',
            user_id=test_user.id,
            paper_id=test_paper.id,
            prompt='A test image prompt',
            status='queued'
        )
        db.session.add(job)
        db.session.commit()

        yield job

        db.session.delete(job)
        db.session.commit()


@pytest.fixture
def test_paper_image(app, test_user, test_paper, test_image_bytes):
    """Create a test paper image record and file."""
    with app.app_context():
        from tools.editor.utils import safe_paper_dir

        paper_dir = safe_paper_dir(test_paper.id)
        paper_dir.mkdir(parents=True, exist_ok=True)

        filename = 'test-image-001.png'
        filepath = paper_dir / filename
        filepath.write_bytes(test_image_bytes)

        img = PaperImage(
            paper_id=test_paper.id,
            user_id=test_user.id,
            filename=filename,
            original_name='test.png',
            file_path=f'{test_paper.id}/{filename}'
        )
        db.session.add(img)
        db.session.commit()

        yield img

        if filepath.exists():
            filepath.unlink()
        db.session.delete(img)
        db.session.commit()


class TestImageJobs:
    """Test Image Generation Jobs API."""

    def test_create_image_job_success(self, client, auth_headers, test_paper):
        """Create valid image generation job."""
        response = client.post(
            '/api/image-jobs',
            headers=auth_headers,
            json={
                'paper_id': test_paper.id,
                'prompt': 'A beautiful sunset over mountains'
            }
        )

        assert response.status_code == 200
        data = response.get_json()
        assert 'id' in data
        assert data['status'] == 'queued'

    def test_create_image_job_invalid_paper(self, client, auth_headers):
        """Attempt to create job with invalid paper_id."""
        response = client.post(
            '/api/image-jobs',
            headers=auth_headers,
            json={
                'paper_id': 'invalid-paper-id',
                'prompt': 'Test prompt'
            }
        )

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_create_image_job_empty_prompt(self, client, auth_headers, test_paper):
        """Attempt to create job with empty prompt."""
        response = client.post(
            '/api/image-jobs',
            headers=auth_headers,
            json={
                'paper_id': test_paper.id,
                'prompt': ''
            }
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_create_image_job_prompt_too_long(self, client, auth_headers, test_paper):
        """Attempt to create job with prompt > 2000 chars."""
        long_prompt = 'A' * 2001
        response = client.post(
            '/api/image-jobs',
            headers=auth_headers,
            json={
                'paper_id': test_paper.id,
                'prompt': long_prompt
            }
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert '2000' in data['error']

    def test_create_image_job_rate_limit(self, client, auth_headers, test_paper, app):
        """Test rate limit enforcement (max 12 inflight jobs)."""
        with app.app_context():
            for i in range(12):
                job = ImageGenJob(
                    id=f'rate-limit-job-{i}',
                    user_id=test_paper.user_id,
                    paper_id=test_paper.id,
                    prompt=f'Prompt {i}',
                    status='queued'
                )
                db.session.add(job)
            db.session.commit()

        response = client.post(
            '/api/image-jobs',
            headers=auth_headers,
            json={
                'paper_id': test_paper.id,
                'prompt': 'This should be rate limited'
            }
        )

        assert response.status_code == 429
        data = response.get_json()
        assert 'error' in data

        with app.app_context():
            ImageGenJob.query.filter(
                ImageGenJob.id.like('rate-limit-job-%')
            ).delete()
            db.session.commit()

    def test_list_image_jobs(self, client, auth_headers, test_image_job):
        """List user's image generation jobs."""
        response = client.get('/api/image-jobs', headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert 'jobs' in data
        assert len(data['jobs']) >= 1
        assert any(j['id'] == test_image_job.id for j in data['jobs'])

    def test_get_single_image_job(self, client, auth_headers, test_image_job):
        """Get single image generation job by ID."""
        response = client.get(
            f'/api/image-jobs/{test_image_job.id}',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == test_image_job.id
        assert data['prompt'] == test_image_job.prompt
        assert data['status'] == 'queued'

    def test_cancel_image_job(self, client, auth_headers, test_image_job):
        """Cancel an image generation job."""
        response = client.post(
            f'/api/image-jobs/{test_image_job.id}/cancel',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == test_image_job.id
        assert data['status'] == 'cancelled'


class TestImageUploadCRUD:
    """Test Image Upload and CRUD operations."""

    def test_upload_image_success(self, client, auth_headers, test_paper, test_image_bytes):
        """Upload valid PNG image."""
        response = client.post(
            f'/api/papers/{test_paper.id}/images',
            headers=auth_headers,
            data={
                'file': (io.BytesIO(test_image_bytes), 'test.png')
            },
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'image' in data
        assert data['image']['original_name'] == 'test.png'
        assert data['image']['paper_id'] == test_paper.id

    def test_upload_image_invalid_format(self, client, auth_headers, test_paper):
        """Attempt to upload non-image file."""
        txt_content = b'This is a text file, not an image'
        response = client.post(
            f'/api/papers/{test_paper.id}/images',
            headers=auth_headers,
            data={
                'file': (io.BytesIO(txt_content), 'test.txt')
            },
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_upload_image_too_large(self, client, auth_headers, test_paper):
        """Attempt to upload file > 10MB."""
        large_file = b'\x89PNG\r\n\x1a\n' + (b'X' * (10 * 1024 * 1024 + 1))
        response = client.post(
            f'/api/papers/{test_paper.id}/images',
            headers=auth_headers,
            data={
                'file': (io.BytesIO(large_file), 'large.png')
            },
            content_type='multipart/form-data'
        )

        assert response.status_code == 413
        data = response.get_json()
        assert 'error' in data

    def test_upload_image_invalid_bytes(self, client, auth_headers, test_paper):
        """Upload file with .png extension but invalid image bytes."""
        fake_png = b'This is not a real PNG file'
        response = client.post(
            f'/api/papers/{test_paper.id}/images',
            headers=auth_headers,
            data={
                'file': (io.BytesIO(fake_png), 'fake.png')
            },
            content_type='multipart/form-data'
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_upload_user_image_variant(self, client, auth_headers, test_paper, test_image_bytes):
        """Upload via /upload endpoint (user-uploaded variant)."""
        response = client.post(
            f'/api/papers/{test_paper.id}/images/upload',
            headers=auth_headers,
            data={
                'file': (io.BytesIO(test_image_bytes), 'user-upload.png')
            },
            content_type='multipart/form-data'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['kind'] == 'uploaded'
        assert data['original_name'] == 'user-upload.png'
        assert data['paper_id'] == test_paper.id

    def test_list_paper_images(self, client, auth_headers, test_paper, test_paper_image):
        """List all images for a paper."""
        response = client.get(
            f'/api/papers/{test_paper.id}/images',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert 'images' in data
        assert len(data['images']) >= 1
        assert any(img['id'] == test_paper_image.id for img in data['images'])

    def test_delete_image_success(self, client, auth_headers, test_paper, test_paper_image):
        """Delete an image successfully."""
        response = client.delete(
            f'/api/papers/{test_paper.id}/images/{test_paper_image.id}',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_delete_image_unauthorized(self, client, other_user_headers, test_paper, test_paper_image):
        """Attempt to delete another user's image."""
        response = client.delete(
            f'/api/papers/{test_paper.id}/images/{test_paper_image.id}',
            headers=other_user_headers
        )

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_serve_image_with_jwt(self, client, auth_headers, test_paper, test_paper_image):
        """Serve image with JWT authentication."""
        response = client.get(
            f'/api/images/{test_paper.id}/{test_paper_image.filename}',
            headers=auth_headers
        )

        assert response.status_code == 200
        assert response.content_type.startswith('image/')
        assert len(response.data) > 0

    def test_sign_resource_token(self, client, auth_headers, test_paper, test_paper_image):
        """Generate signed token for image access."""
        response = client.post(
            f'/api/papers/{test_paper.id}/sign',
            headers=auth_headers,
            json={
                'scope': 'image',
                'resource_id': test_paper_image.filename,
                'ttl_seconds': 600
            }
        )

        assert response.status_code == 200
        data = response.get_json()
        assert 'url' in data
        assert 'expires_in' in data
        assert data['expires_in'] == 600
        assert test_paper_image.filename in data['url']

    def test_serve_image_with_signed_token(self, client, auth_headers, test_paper, test_paper_image):
        """Serve image using signed token."""
        sign_response = client.post(
            f'/api/papers/{test_paper.id}/sign',
            headers=auth_headers,
            json={
                'scope': 'image',
                'resource_id': test_paper_image.filename,
                'ttl_seconds': 600
            }
        )

        assert sign_response.status_code == 200
        sign_data = sign_response.get_json()
        signed_url = sign_data['url']

        response = client.get(signed_url)

        assert response.status_code == 200
        assert response.content_type.startswith('image/')
        assert len(response.data) > 0
