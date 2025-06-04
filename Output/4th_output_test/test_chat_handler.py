import unittest
from unittest.mock import patch, MagicMock
from chat_handler import handle_chat, handle_modify_request, apply_changes

class TestChatHandler(unittest.TestCase):
    def setUp(self):
        self.test_session_id = "test_session"
        self.test_repo_url = "https://github.com/test/repo"
        self.test_token = "test_token"
        self.test_file_path = "test.py"
        self.test_code = "print('Hello, World!')"
        self.test_changes = "print('Hello, Test!')"
        self.test_session_data = {
            'repo_url': self.test_repo_url,
            'directory_structure': 'test.py',
            'token': self.test_token
        }

    @patch('chat_handler.openai')
    @patch('chat_handler.chroma_client')
    @patch('chat_handler.save_conversation')
    @patch('chat_handler.sessions', {'test_session': {'repo_url': 'https://github.com/test/repo', 'directory_structure': 'test.py', 'token': 'test_token'}})
    def test_handle_chat(self, mock_save, mock_chroma, mock_openai):
        # Mock OpenAI embeddings
        mock_embedding = MagicMock()
        mock_embedding.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_openai.embeddings.create.return_value = mock_embedding

        # Mock ChromaDB
        mock_collection = MagicMock()
        mock_chroma.get_collection.return_value = mock_collection
        mock_collection.count.return_value = 1
        mock_collection.query.return_value = {
            'documents': [['Test content']],
            'metadatas': [[{'file_name': 'test.py', 'function_name': 'test_func'}]]
        }

        # Mock OpenAI chat completion
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        mock_openai.chat.completions.create.return_value = mock_response

        result = handle_chat(self.test_session_id, "Test message")
        self.assertIsInstance(result, dict)
        self.assertIn('answer', result)

    @patch('chat_handler.openai')
    @patch('chat_handler.get_relevant_conversations')
    @patch('chat_handler.save_conversation')
    @patch('chat_handler.sessions', {'test_session': {'repo_url': 'https://github.com/test/repo', 'directory_structure': 'test.py', 'token': 'test_token'}})
    def test_handle_modify_request(self, mock_save, mock_get_conv, mock_openai):
        mock_get_conv.return_value = "이전 대화 없음"
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        mock_openai.chat.completions.create.return_value = mock_response

        result = handle_modify_request(self.test_session_id, "Test message")
        self.assertIsInstance(result, dict)
        self.assertIn('answer', result)

    @patch('chat_handler.openai')
    @patch('chat_handler.save_conversation')
    @patch('chat_handler.sessions', {'test_session': {'repo_url': 'https://github.com/test/repo', 'directory_structure': 'test.py', 'token': 'test_token'}})
    def test_apply_changes(self, mock_save, mock_openai):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        mock_openai.chat.completions.create.return_value = mock_response

        result = apply_changes(
            self.test_session_id,
            self.test_file_path,
            self.test_changes,
            False,
            None
        )
        self.assertIsInstance(result, dict)
        self.assertIn('result', result)
        self.assertIn('success', result)

if __name__ == '__main__':
    unittest.main()