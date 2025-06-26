import unittest
from unittest.mock import patch, MagicMock
from chat_handler import handle_chat, handle_modify_request, apply_changes

class TestChatHandler(unittest.TestCase):
    @patch('chat_handler.chroma_client')
    @patch('chat_handler.openai')
    
    
    def test_handle_chat(self, mock_openai, mock_chroma):
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

        result = handle_chat("test_session", "Test message")
        self.assertIsInstance(result, dict)
        self.assertIn('answer', result)

if __name__ == "__main__":
    unittest.main() 