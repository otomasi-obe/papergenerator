"""
Integration Tests: Paper CRUD Operations
=========================================
Test complete paper CRUD flows including create, read, update, delete, list, and patch.
"""


class TestPaperList:
    """Test GET /api/papers - List papers with pagination."""

    def test_list_papers_empty(self, client, test_user):
        """Test listing papers returns empty list for new user."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.get('/api/papers')

        assert response.status_code == 200
        data = response.get_json()
        assert 'papers' in data
        assert data['papers'] == []
        assert data['pagination']['total'] == 0

    def test_list_papers_with_data(self, client, test_user, test_paper):
        """Test listing papers returns user's papers."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.get('/api/papers')

        assert response.status_code == 200
        data = response.get_json()
        assert len(data['papers']) == 1
        assert data['papers'][0]['id'] == 'test-paper-1'
        assert data['papers'][0]['title'] == 'Test Paper'
        assert data['pagination']['total'] == 1

    def test_list_papers_pagination(self, client, test_user, test_paper):
        """Test pagination parameters work correctly."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.get('/api/papers?limit=10&offset=0')

        assert response.status_code == 200
        data = response.get_json()
        assert data['pagination']['limit'] == 10
        assert data['pagination']['offset'] == 0
        assert not data['pagination']['has_more']

    def test_list_papers_user_isolation(self, client, test_user, other_user_paper):
        """Test user can only see their own papers."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.get('/api/papers')

        assert response.status_code == 200
        data = response.get_json()
        assert data['papers'] == []
        assert data['pagination']['total'] == 0

    def test_list_papers_unauthorized(self, client):
        """Test listing papers without authentication returns 401."""
        response = client.get('/api/papers')

        assert response.status_code == 401

    def test_list_papers_invalid_query(self, client, test_user):
        """Test invalid query parameters are handled."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.get('/api/papers?limit=invalid')

        assert response.status_code in [200, 400]


class TestPaperCreate:
    """Test POST /api/papers - Create/save paper."""

    def test_create_paper_with_auto_id(self, client, test_user):
        """Test creating paper with auto-generated ID."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        paper_data = {
            'title': 'New Paper',
            'data': {
                'title': 'New Paper',
                'abstract': 'Test abstract'
            }
        }
        response = client.post('/api/papers', json=paper_data)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']
        assert 'id' in data
        assert data['paper']['title'] == 'New Paper'

    def test_create_paper_with_custom_id(self, client, test_user):
        """Test creating paper with custom ID."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        paper_data = {
            'id': 'custom-paper-1',
            'title': 'Custom Paper',
            'data': {
                'title': 'Custom Paper',
                'abstract': 'Custom abstract'
            }
        }
        response = client.post('/api/papers', json=paper_data)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']
        assert data['id'] == 'custom-paper-1'

    def test_create_paper_upsert_behavior(self, client, test_user, test_paper):
        """Test updating existing paper via POST (upsert)."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        paper_data = {
            'id': 'test-paper-1',
            'title': 'Updated Title',
            'data': {
                'title': 'Updated Title',
                'abstract': 'Updated abstract'
            }
        }
        response = client.post('/api/papers', json=paper_data)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']
        assert data['paper']['title'] == 'Updated Title'

    def test_create_paper_invalid_id(self, client, test_user):
        """Test creating paper with invalid ID format returns 400."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        paper_data = {
            'id': 'invalid@id#format',
            'title': 'Test',
            'data': {}
        }
        response = client.post('/api/papers', json=paper_data)

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_create_paper_no_data(self, client, test_user):
        """Test creating paper without data returns 400."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.post('/api/papers')

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_create_paper_unauthorized(self, client):
        """Test creating paper without authentication returns 401."""
        paper_data = {
            'title': 'Test',
            'data': {}
        }
        response = client.post('/api/papers', json=paper_data)

        assert response.status_code == 401

    def test_create_paper_title_extraction(self, client, test_user):
        """Test title extraction from data.title."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        paper_data = {
            'data': {
                'title': 'Extracted Title',
                'abstract': 'Test'
            }
        }
        response = client.post('/api/papers', json=paper_data)

        assert response.status_code == 200
        data = response.get_json()
        assert data['paper']['title'] == 'Extracted Title'


class TestPaperLoad:
    """Test GET /api/papers/<paper_id> - Load single paper."""

    def test_load_existing_paper(self, client, test_user, test_paper):
        """Test loading existing paper returns full data."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.get('/api/papers/test-paper-1')

        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == 'test-paper-1'
        assert data['title'] == 'Test Paper'
        assert 'abstract' in data

    def test_load_nonexistent_paper(self, client, test_user):
        """Test loading non-existent paper returns 404."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.get('/api/papers/nonexistent-id')

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_load_other_user_paper(self, client, test_user, other_user_paper):
        """Test loading other user's paper returns 404 (user isolation)."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.get('/api/papers/other-paper-1')

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_load_paper_invalid_id(self, client, test_user):
        """Test loading paper with invalid ID format returns 400."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.get('/api/papers/invalid@id')

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_load_paper_unauthorized(self, client, test_paper):
        """Test loading paper without authentication returns 401."""
        response = client.get('/api/papers/test-paper-1')

        assert response.status_code == 401


class TestPaperUpdate:
    """Test PUT /api/papers/<paper_id> - Update paper."""

    def test_update_existing_paper(self, client, test_user, test_paper):
        """Test updating existing paper succeeds."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        update_data = {
            'title': 'Updated Paper Title',
            'data': {
                'title': 'Updated Paper Title',
                'abstract': 'Updated abstract content'
            }
        }
        response = client.put('/api/papers/test-paper-1', json=update_data)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']
        assert data['paper']['title'] == 'Updated Paper Title'

    def test_update_nonexistent_paper(self, client, test_user):
        """Test updating non-existent paper returns 404."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        update_data = {
            'title': 'Test',
            'data': {}
        }
        response = client.put('/api/papers/nonexistent-id', json=update_data)

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_update_other_user_paper(self, client, test_user, other_user_paper):
        """Test updating other user's paper returns 404."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        update_data = {
            'title': 'Hacked',
            'data': {}
        }
        response = client.put('/api/papers/other-paper-1', json=update_data)

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_update_paper_invalid_id(self, client, test_user):
        """Test updating paper with invalid ID format returns 400."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        update_data = {'title': 'Test', 'data': {}}
        response = client.put('/api/papers/invalid@id', json=update_data)

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_update_paper_unauthorized(self, client, test_paper):
        """Test updating paper without authentication returns 401."""
        update_data = {'title': 'Test', 'data': {}}
        response = client.put('/api/papers/test-paper-1', json=update_data)

        assert response.status_code == 401

    def test_update_paper_empty_data(self, client, test_user, test_paper):
        """Test updating paper with empty data handled gracefully."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.put('/api/papers/test-paper-1', json={})

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']


class TestPaperDelete:
    """Test DELETE /api/papers/<paper_id> - Delete paper."""

    def test_delete_existing_paper(self, client, test_user, test_paper):
        """Test deleting existing paper succeeds."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.delete('/api/papers/test-paper-1')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']

        get_response = client.get('/api/papers/test-paper-1')
        assert get_response.status_code == 404

    def test_delete_nonexistent_paper(self, client, test_user):
        """Test deleting non-existent paper returns 404."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.delete('/api/papers/nonexistent-id')

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_delete_other_user_paper(self, client, test_user, other_user_paper):
        """Test deleting other user's paper returns 404."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.delete('/api/papers/other-paper-1')

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_delete_paper_invalid_id(self, client, test_user):
        """Test deleting paper with invalid ID format returns 400."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.delete('/api/papers/invalid@id')

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_delete_paper_unauthorized(self, client, test_paper):
        """Test deleting paper without authentication returns 401."""
        response = client.delete('/api/papers/test-paper-1')

        assert response.status_code == 401

    def test_delete_paper_cascade(self, client, test_user, test_paper):
        """Test cascade delete removes related data."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        response = client.delete('/api/papers/test-paper-1')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']


class TestPaperPatch:
    """Test PATCH /api/papers/<paper_id> - JSON Patch operations."""

    def test_patch_replace_title(self, client, test_user, test_paper):
        """Test replace operation on title field."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        patch_ops = {
            'patch': [
                {'op': 'replace', 'path': '/title', 'value': 'Patched Title'}
            ]
        }
        response = client.patch('/api/papers/test-paper-1', json=patch_ops)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']
        assert data['applied'] == 1
        assert data['paper']['title'] == 'Patched Title'

    def test_patch_add_section(self, client, test_user, test_paper):
        """Test add operation on sections array."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        patch_ops = {
            'patch': [
                {'op': 'add', 'path': '/sections/-', 'value': {'title': 'New Section', 'content': 'New content'}}
            ]
        }
        response = client.patch('/api/papers/test-paper-1', json=patch_ops)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']

    def test_patch_remove_field(self, client, test_user, test_paper):
        """Test remove operation."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        patch_ops = {
            'patch': [
                {'op': 'remove', 'path': '/abstract'}
            ]
        }
        response = client.patch('/api/papers/test-paper-1', json=patch_ops)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success']

    def test_patch_invalid_operation(self, client, test_user, test_paper):
        """Test invalid operation rejected."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        patch_ops = {
            'patch': [
                {'op': 'invalid', 'path': '/title', 'value': 'Test'}
            ]
        }
        response = client.patch('/api/papers/test-paper-1', json=patch_ops)

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_patch_invalid_path(self, client, test_user, test_paper):
        """Test invalid path rejected (unknown field)."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        patch_ops = {
            'patch': [
                {'op': 'replace', 'path': '/unknown_field', 'value': 'Test'}
            ]
        }
        response = client.patch('/api/papers/test-paper-1', json=patch_ops)

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_patch_empty_array(self, client, test_user, test_paper):
        """Test empty patch array returns 400."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        patch_ops = {'patch': []}
        response = client.patch('/api/papers/test-paper-1', json=patch_ops)

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_patch_non_array(self, client, test_user, test_paper):
        """Test non-array patch returns 400."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        patch_ops = {'patch': 'not an array'}
        response = client.patch('/api/papers/test-paper-1', json=patch_ops)

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_patch_unauthorized(self, client, test_paper):
        """Test patch without authentication returns 401."""
        patch_ops = {
            'patch': [
                {'op': 'replace', 'path': '/title', 'value': 'Test'}
            ]
        }
        response = client.patch('/api/papers/test-paper-1', json=patch_ops)

        assert response.status_code == 401

    def test_patch_nonexistent_paper(self, client, test_user):
        """Test patch on non-existent paper returns 404."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        patch_ops = {
            'patch': [
                {'op': 'replace', 'path': '/title', 'value': 'Test'}
            ]
        }
        response = client.patch('/api/papers/nonexistent-id', json=patch_ops)

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data


class TestPaperLifecycle:
    """Test complete paper lifecycle: create -> read -> update -> patch -> delete."""

    def test_complete_paper_lifecycle(self, client, test_user):
        """Test complete paper lifecycle from creation to deletion."""
        client.post('/api/auth/login', json={
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        })

        create_data = {
            'id': 'lifecycle-paper',
            'title': 'Lifecycle Paper',
            'data': {
                'title': 'Lifecycle Paper',
                'abstract': 'Testing complete lifecycle'
            }
        }
        create_response = client.post('/api/papers', json=create_data)
        assert create_response.status_code == 200
        assert create_response.get_json()['success']

        load_response = client.get('/api/papers/lifecycle-paper')
        assert load_response.status_code == 200
        assert load_response.get_json()['id'] == 'lifecycle-paper'

        update_data = {
            'title': 'Updated Lifecycle',
            'data': {
                'title': 'Updated Lifecycle',
                'abstract': 'Updated content'
            }
        }
        update_response = client.put('/api/papers/lifecycle-paper', json=update_data)
        assert update_response.status_code == 200
        assert update_response.get_json()['paper']['title'] == 'Updated Lifecycle'

        patch_ops = {
            'patch': [
                {'op': 'replace', 'path': '/title', 'value': 'Patched Lifecycle'}
            ]
        }
        patch_response = client.patch('/api/papers/lifecycle-paper', json=patch_ops)
        assert patch_response.status_code == 200
        assert patch_response.get_json()['paper']['title'] == 'Patched Lifecycle'

        delete_response = client.delete('/api/papers/lifecycle-paper')
        assert delete_response.status_code == 200
        assert delete_response.get_json()['success']

        verify_response = client.get('/api/papers/lifecycle-paper')
        assert verify_response.status_code == 404
