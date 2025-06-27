import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from unittest.mock import patch, MagicMock
import chat_handler

@pytest.fixture
def session_data():
    return {
        'repo_url': 'https://github.com/test/repo',
        'directory_structure': 'test.py',
        'token': 'test_token'
    }

def test_handle_chat_success(session_data):
    with patch('chat_handler.db.get_session_data_from_db') as mock_get_session, \
         patch('chat_handler.openai') as mock_openai, \
         patch('chat_handler.chroma_client') as mock_chroma:
        mock_get_session.return_value = session_data
        mock_embedding = MagicMock()
        mock_embedding.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_openai.embeddings.create.return_value = mock_embedding
        mock_collection = MagicMock()
        mock_chroma.get_collection.return_value = mock_collection
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            'documents': [['Test content']],
            'metadatas': [[{'file_name': 'test.py', 'function_name': 'test_func'}]]
        }
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        mock_openai.chat.completions.create.return_value = mock_response
        result = chat_handler.handle_chat('unittest_session', '테스트 메시지')
        assert isinstance(result, dict)
        assert 'answer' in result

def test_handle_chat_no_session():
    with patch('chat_handler.db.get_session_data_from_db', return_value=None):
        result = chat_handler.handle_chat('unittest_session', '테스트 메시지')
        assert 'error' in result
        assert result['error'] == 'session_not_found'

def test_handle_chat_api_key_missing(session_data):
    with patch('chat_handler.db.get_session_data_from_db', return_value=session_data), \
         patch('chat_handler.openai') as mock_openai:
        mock_openai.api_key = None
        result = chat_handler.handle_chat('unittest_session', '테스트 메시지')
        assert result['error'] == 'api_key_missing'

def test_handle_chat_embedding_empty(session_data):
    with patch('chat_handler.db.get_session_data_from_db', return_value=session_data), \
         patch('chat_handler.openai') as mock_openai:
        mock_embedding = MagicMock()
        mock_embedding.data = [MagicMock(embedding=None)]
        mock_openai.api_key = 'testkey'
        mock_openai.embeddings.create.return_value = mock_embedding
        result = chat_handler.handle_chat('unittest_session', '테스트 메시지')
        assert result['error'] == 'empty_embedding'

def test_handle_chat_embedding_error(session_data):
    with patch('chat_handler.db.get_session_data_from_db') as mock_get_session, \
         patch('chat_handler.openai') as mock_openai, \
         patch('chat_handler.chroma_client') as mock_chroma:
        mock_get_session.return_value = session_data
        mock_openai.embeddings.create.side_effect = Exception("임베딩 에러")
        result = chat_handler.handle_chat('unittest_session', '테스트 메시지')
        assert 'error' in result
        assert result['error'] == 'embedding_error'

def test_handle_chat_collection_access_error(session_data):
    with patch('chat_handler.db.get_session_data_from_db', return_value=session_data), \
         patch('chat_handler.openai') as mock_openai, \
         patch('chat_handler.chroma_client.get_collection', side_effect=Exception('컬렉션 에러')):
        mock_embedding = MagicMock()
        mock_embedding.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_openai.api_key = 'testkey'
        mock_openai.embeddings.create.return_value = mock_embedding
        result = chat_handler.handle_chat('unittest_session', '테스트 메시지')
        assert result['error'] == 'collection_not_found'

def test_handle_chat_empty_collection(session_data):
    with patch('chat_handler.db.get_session_data_from_db', return_value=session_data), \
         patch('chat_handler.openai') as mock_openai, \
         patch('chat_handler.chroma_client') as mock_chroma:
        mock_embedding = MagicMock()
        mock_embedding.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_openai.api_key = 'testkey'
        mock_openai.embeddings.create.return_value = mock_embedding
        mock_collection = MagicMock()
        mock_chroma.get_collection.return_value = mock_collection
        mock_collection.count.return_value = 0
        mock_collection.query.return_value = {'documents': [[]], 'metadatas': [[]]}
        result = chat_handler.handle_chat('unittest_session', '테스트 메시지')
        assert 'answer' in result
        # empty_collection 에러는 directory_structure가 없을 때만 발생

def test_handle_chat_llm_empty_response(session_data):
    with patch('chat_handler.db.get_session_data_from_db', return_value=session_data), \
         patch('chat_handler.openai') as mock_openai, \
         patch('chat_handler.chroma_client') as mock_chroma:
        mock_embedding = MagicMock()
        mock_embedding.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_openai.api_key = 'testkey'
        mock_openai.embeddings.create.return_value = mock_embedding
        mock_collection = MagicMock()
        mock_chroma.get_collection.return_value = mock_collection
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            'documents': [['Test content']],
            'metadatas': [[{'file_name': 'test.py', 'function_name': 'test_func'}]]
        }
        mock_response = MagicMock()
        mock_response.choices = []  # LLM 응답 없음
        mock_openai.chat.completions.create.return_value = mock_response
        result = chat_handler.handle_chat('unittest_session', '테스트 메시지')
        assert result['error'] == 'collection_not_found'

def test_handle_chat_llm_error(session_data):
    with patch('chat_handler.db.get_session_data_from_db', return_value=session_data), \
         patch('chat_handler.openai') as mock_openai, \
         patch('chat_handler.chroma_client') as mock_chroma:
        mock_embedding = MagicMock()
        mock_embedding.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_openai.api_key = 'testkey'
        mock_openai.embeddings.create.return_value = mock_embedding
        mock_collection = MagicMock()
        mock_chroma.get_collection.return_value = mock_collection
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            'documents': [['Test content']],
            'metadatas': [[{'file_name': 'test.py', 'function_name': 'test_func'}]]
        }
        mock_openai.chat.completions.create.side_effect = Exception('LLM 에러')
        result = chat_handler.handle_chat('unittest_session', '테스트 메시지')
        assert result['error'] == 'collection_not_found'
