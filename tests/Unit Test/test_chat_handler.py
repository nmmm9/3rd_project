import unittest
import sys, os
from unittest.mock import patch, MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chat_handler

class TestChatHandler(unittest.TestCase):
    def setUp(self):
        self.session_id = "unittest_session"
        self.message = "테스트 메시지"
        # 세션 mock 데이터
        self.session_data = {
            'repo_url': 'https://github.com/test/repo',
            'directory_structure': 'test.py',
            'token': 'test_token'
        }

    @patch('chat_handler.db.get_session_data_from_db')
    @patch('chat_handler.openai')
    @patch('chat_handler.chroma_client')
    def test_handle_chat_success(self, mock_chroma, mock_openai, mock_get_session):
        # 세션 데이터 정상 반환
        mock_get_session.return_value = self.session_data

        # OpenAI 임베딩 mock
        mock_embedding = MagicMock()
        mock_embedding.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_openai.embeddings.create.return_value = mock_embedding

        # ChromaDB mock
        mock_collection = MagicMock()
        mock_chroma.get_collection.return_value = mock_collection
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            'documents': [['Test content']],
            'metadatas': [[{'file_name': 'test.py', 'function_name': 'test_func'}]]
        }

        # OpenAI chat completion mock
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        mock_openai.chat.completions.create.return_value = mock_response

        result = chat_handler.handle_chat(self.session_id, self.message)
        self.assertIsInstance(result, dict)
        self.assertIn('answer', result)

    @patch('chat_handler.db.get_session_data_from_db', return_value=None)
    def test_handle_chat_no_session(self, mock_get_session):
        # 세션이 없을 때
        result = chat_handler.handle_chat(self.session_id, self.message)
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'session_not_found')

    @patch('chat_handler.db.get_session_data_from_db')
    @patch('chat_handler.openai')
    @patch('chat_handler.chroma_client')
    def test_handle_chat_embedding_error(self, mock_chroma, mock_openai, mock_get_session):
        mock_get_session.return_value = self.session_data
        # OpenAI 임베딩에서 예외 발생
        mock_openai.embeddings.create.side_effect = Exception("임베딩 에러")
        result = chat_handler.handle_chat(self.session_id, self.message)
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'embedding_error')

    # 필요에 따라 handle_modify_request, apply_changes 등도 유사하게 테스트 추가

if __name__ == "__main__":
    unittest.main()
