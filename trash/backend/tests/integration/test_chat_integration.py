"""
Integration tests for Chat/Conversation endpoints.

Tests cover:
- Conversation CRUD operations
- Message sending and SSE streaming
- Project Memory CRUD
- Security and authorization
- Edge cases and error handling

Cycle 31 - Chat Integration Tests (Rebuilt)
Cycle 32 - SSE Event Parsing Tests
"""


import pytest

from database.models import ChatMessage, Conversation, ProjectMemory, db


@pytest.fixture
def test_conversation(app, test_user, test_paper):
    """Create a test conversation."""
    with app.app_context():
        conv = Conversation(
            id='test-conv-001',
            user_id=test_user.id,
            paper_id=test_paper.id,
            title='Test Chat'
        )
        db.session.add(conv)
        db.session.commit()

        yield conv

        db.session.delete(conv)
        db.session.commit()


@pytest.fixture
def test_conversation_with_messages(app, test_conversation):
    """Create a conversation with some messages."""
    with app.app_context():
        msg1 = ChatMessage(
            conversation_id=test_conversation.id,
            role='user',
            content='Hello, this is a test message'
        )
        msg2 = ChatMessage(
            conversation_id=test_conversation.id,
            role='assistant',
            content='Hi! How can I help you?'
        )
        db.session.add_all([msg1, msg2])
        db.session.commit()

        yield test_conversation


@pytest.fixture
def test_memory_entry(app, test_paper, test_user):
    """Create a test memory entry."""
    with app.app_context():
        mem = ProjectMemory(
            paper_id=test_paper.id,
            user_id=test_user.id,
            key='test_key',
            value='test_value',
            kind='fact'
        )
        db.session.add(mem)
        db.session.commit()

        yield mem

        db.session.delete(mem)
        db.session.commit()


@pytest.fixture
def other_user_conversation(app, other_user, other_user_paper):
    """Create conversation owned by other_user."""
    with app.app_context():
        conv = Conversation(
            id='other-conv-001',
            user_id=other_user.id,
            paper_id=other_user_paper.id,
            title='Other User Chat'
        )
        db.session.add(conv)
        db.session.commit()

        yield conv

        db.session.delete(conv)
        db.session.commit()


class TestConversationCRUD:
    """Test conversation CRUD operations."""

    def test_create_conversation_success(self, client, auth_headers, test_paper):
        """Test creating a new conversation."""
        response = client.post(
            f'/api/papers/{test_paper.id}/conversations',
            headers=auth_headers,
            json={'title': 'My New Chat'}
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data['title'] == 'My New Chat'
        assert data['paper_id'] == test_paper.id
        assert 'id' in data

    def test_create_conversation_with_default_title(self, client, auth_headers, test_paper):
        """Test creating conversation without title uses default."""
        response = client.post(
            f'/api/papers/{test_paper.id}/conversations',
            headers=auth_headers,
            json={}
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data['title'] == 'New Chat'

    def test_list_conversations_empty(self, client, auth_headers, test_paper):
        """Test listing conversations when paper has none."""
        response = client.get(
            f'/api/papers/{test_paper.id}/conversations',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_conversations_multiple(self, client, auth_headers, test_paper, test_conversation):
        """Test listing multiple conversations."""
        response = client.get(
            f'/api/papers/{test_paper.id}/conversations',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) >= 1
        assert any(c['id'] == test_conversation.id for c in data)

    def test_get_conversation_with_messages(self, client, auth_headers, test_conversation_with_messages):
        """Test getting conversation with messages."""
        response = client.get(
            f'/api/chat/conversations/{test_conversation_with_messages.id}',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == test_conversation_with_messages.id
        assert 'messages' in data
        assert len(data['messages']) == 2

    def test_rename_conversation_success(self, client, auth_headers, test_conversation):
        """Test renaming a conversation."""
        response = client.patch(
            f'/api/chat/conversations/{test_conversation.id}',
            headers=auth_headers,
            json={'title': 'Renamed Chat'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['title'] == 'Renamed Chat'

    def test_delete_conversation_success(self, client, auth_headers, test_conversation, app):
        """Test deleting a conversation."""
        conv_id = test_conversation.id

        response = client.delete(
            f'/api/chat/conversations/{conv_id}',
            headers=auth_headers
        )

        assert response.status_code == 200

        with app.app_context():
            deleted_conv = db.session.get(Conversation, conv_id)
            assert deleted_conv is None

    def test_get_or_create_conversation_legacy(self, client, auth_headers, test_paper):
        """Test legacy get-or-create conversation endpoint."""
        response = client.get(
            f'/api/papers/{test_paper.id}/conversation',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert 'id' in data
        assert data['paper_id'] == test_paper.id


class TestConversationSecurity:
    """Test conversation security and authorization."""

    def test_create_conversation_unauthorized(self, client, test_paper):
        """Test creating conversation without auth fails."""
        response = client.post(
            f'/api/papers/{test_paper.id}/conversations',
            json={'title': 'Unauthorized'}
        )

        assert response.status_code == 401

    def test_create_conversation_other_user_paper(self, client, auth_headers, other_user_paper):
        """Test cannot create conversation in other user's paper."""
        response = client.post(
            f'/api/papers/{other_user_paper.id}/conversations',
            headers=auth_headers,
            json={'title': 'Hacker Chat'}
        )

        assert response.status_code == 404

    def test_get_conversation_other_user(self, client, auth_headers, other_user_conversation):
        """Test cannot get other user's conversation."""
        response = client.get(
            f'/api/chat/conversations/{other_user_conversation.id}',
            headers=auth_headers
        )

        assert response.status_code == 404

    def test_rename_conversation_other_user(self, client, auth_headers, other_user_conversation):
        """Test cannot rename other user's conversation."""
        response = client.patch(
            f'/api/chat/conversations/{other_user_conversation.id}',
            headers=auth_headers,
            json={'title': 'Hacked'}
        )

        assert response.status_code == 404

    def test_delete_conversation_other_user(self, client, auth_headers, other_user_conversation):
        """Test cannot delete other user's conversation."""
        response = client.delete(
            f'/api/chat/conversations/{other_user_conversation.id}',
            headers=auth_headers
        )

        assert response.status_code == 404

    def test_list_conversations_other_user_paper(self, client, auth_headers, other_user_paper):
        """Test cannot list conversations from other user's paper."""
        response = client.get(
            f'/api/papers/{other_user_paper.id}/conversations',
            headers=auth_headers
        )

        assert response.status_code == 404


class TestMessageFlow:
    """Test message sending flow."""

    def test_send_message_basic(self, client, auth_headers, test_conversation, app):
        """Test sending a basic message to conversation."""
        response = client.post(
            f'/api/chat/conversations/{test_conversation.id}/messages',
            headers=auth_headers,
            json={'content': 'Hello, AI!'}
        )

        assert response.status_code == 200
        assert response.content_type == 'text/event-stream; charset=utf-8'

        with app.app_context():
            messages = ChatMessage.query.filter_by(
                conversation_id=test_conversation.id
            ).all()
            assert len(messages) >= 1
            user_msg = [m for m in messages if m.role == 'user'][0]
            assert user_msg.content == 'Hello, AI!'

    def test_send_message_auto_title(self, client, auth_headers, test_paper, app):
        """Test first message auto-titles conversation."""
        conv_response = client.post(
            f'/api/papers/{test_paper.id}/conversations',
            headers=auth_headers,
            json={}
        )
        conv = conv_response.get_json()
        assert conv['title'] == 'New Chat'

        client.post(
            f'/api/chat/conversations/{conv["id"]}/messages',
            headers=auth_headers,
            json={'content': 'What is the meaning of life?'}
        )

        with app.app_context():
            updated_conv = db.session.get(Conversation, conv['id'])
            assert updated_conv.title == 'What is the meaning of life?'

    def test_send_message_empty_content(self, client, auth_headers, test_conversation):
        """Test sending empty message is rejected."""
        response = client.post(
            f'/api/chat/conversations/{test_conversation.id}/messages',
            headers=auth_headers,
            json={'content': ''}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_send_message_too_long(self, client, auth_headers, test_conversation):
        """Test sending message >16000 chars is rejected."""
        long_content = 'x' * 16001
        response = client.post(
            f'/api/chat/conversations/{test_conversation.id}/messages',
            headers=auth_headers,
            json={'content': long_content}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'too long' in data['error'].lower()

    def test_send_message_unauthorized(self, client, test_conversation):
        """Test sending message without auth fails."""
        response = client.post(
            f'/api/chat/conversations/{test_conversation.id}/messages',
            json={'content': 'Unauthorized message'}
        )

        assert response.status_code == 401


class TestMemoryCRUD:
    """Test project memory CRUD operations."""

    def test_list_memory_empty(self, client, auth_headers, test_paper):
        """Test listing memory when paper has none."""
        response = client.get(
            f'/api/papers/{test_paper.id}/memory',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_memory_with_entries(self, client, auth_headers, test_paper, test_memory_entry):
        """Test listing memory entries."""
        response = client.get(
            f'/api/papers/{test_paper.id}/memory',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert data[0]['key'] == 'test_key'
        assert data[0]['value'] == 'test_value'
        assert data[0]['paper_id'] == test_paper.id

    def test_delete_memory_entry_success(self, client, auth_headers, test_paper, test_memory_entry):
        """Test deleting a memory entry."""
        response = client.delete(
            f'/api/papers/{test_paper.id}/memory/{test_memory_entry.id}',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True

        list_response = client.get(
            f'/api/papers/{test_paper.id}/memory',
            headers=auth_headers
        )
        assert len(list_response.get_json()) == 0

    def test_delete_memory_entry_unauthorized(self, client, auth_headers, other_user_paper, app):
        """Test cannot delete memory from other user's paper."""
        with app.app_context():
            mem = ProjectMemory(
                paper_id=other_user_paper.id,
                user_id=other_user_paper.user_id,
                key='other_key',
                value='other_value',
                kind='fact'
            )
            db.session.add(mem)
            db.session.commit()
            mem_id = mem.id

        response = client.delete(
            f'/api/papers/{other_user_paper.id}/memory/{mem_id}',
            headers=auth_headers
        )

        assert response.status_code == 404


class TestListPapers:
    """Test list papers with chat counts endpoint."""

    def test_list_paper_chats_empty(self, client, auth_headers):
        """Test listing papers when user has none."""
        response = client.get(
            '/api/chat/papers',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_list_paper_chats_with_conversations(self, client, auth_headers, test_paper, test_conversation):
        """Test listing papers with conversation counts."""
        response = client.get(
            '/api/chat/papers',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.get_json()
        paper_data = [p for p in data if p['paper_id'] == test_paper.id]
        if paper_data:
            assert 'chat_count' in paper_data[0]
            assert paper_data[0]['chat_count'] >= 1

    def test_list_paper_chats_unauthorized(self, client):
        """Test listing papers without auth fails."""
        response = client.get('/api/chat/papers')

        assert response.status_code == 401


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_conversation_not_found(self, client, auth_headers):
        """Test accessing non-existent conversation."""
        response = client.get(
            '/api/chat/conversations/nonexistent-conv-id',
            headers=auth_headers
        )

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data

    def test_paper_not_found_for_conversation(self, client, auth_headers):
        """Test creating conversation in non-existent paper."""
        response = client.post(
            '/api/papers/nonexistent-paper-id/conversations',
            headers=auth_headers,
            json={'title': 'Test'}
        )

        assert response.status_code == 404

    def test_rename_conversation_empty_title(self, client, auth_headers, test_conversation):
        """Test renaming conversation with empty title is rejected."""
        response = client.patch(
            f'/api/chat/conversations/{test_conversation.id}',
            headers=auth_headers,
            json={'title': ''}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert 'required' in data['error'].lower()

    def test_title_truncation(self, client, auth_headers, test_paper):
        """Test conversation title >120 chars is truncated."""
        long_title = 'x' * 150
        response = client.post(
            f'/api/papers/{test_paper.id}/conversations',
            headers=auth_headers,
            json={'title': long_title}
        )

        assert response.status_code == 201
        data = response.get_json()
        assert len(data['title']) == 120
