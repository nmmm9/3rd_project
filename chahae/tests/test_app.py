import unittest
from unittest.mock import patch, MagicMock, ANY
import json
from app import app

class TestAppAPI(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        self.test_session_id = "test_session"
        self.test_repo_url = "https://github.com/test/repo"
        self.test_token = "test_token"
        self.test_file_path = "test.py"
        self.test_code = "print('Hello, World!')"
        self.test_changes = "print('Hello, Test!')"

    @patch('app.analyze_repository')
    def test_analyze_endpoint_valid_input(self, mock_analyze):
        mock_analyze.return_value = {
            'files': ['test.py'],
            'directory_structure': 'test.py\n  - Test file'
        }
        response = self.app.post('/analyze', json={
            'repo_url': self.test_repo_url,
            'token': self.test_token,
            'session_id': self.test_session_id
        })
        self.assertEqual(response.status_code, 200)
        response_lines = response.data.decode('utf-8').strip().split('\n')
        first_response = json.loads(response_lines[0])
        last_response = json.loads(response_lines[-1])
        self.assertEqual(first_response['status'], '분석 시작')
        self.assertEqual(first_response['progress'], 0)
        self.assertEqual(last_response['status'], '분석 완료')
        self.assertEqual(last_response['progress'], 100)
        self.assertIn('session_id', last_response)
        self.assertIn('file_count', last_response)
        mock_analyze.assert_called_once_with(
            self.test_repo_url,
            self.test_token,
            ANY  # Use ANY for session_id to avoid strict matching
        )

    def test_analyze_endpoint_invalid_input(self):
        response = self.app.post('/analyze', json={})
        self.assertEqual(response.status_code, 400)
        response = self.app.post('/analyze', json={
            'repo_url': 'invalid_url',
            'token': self.test_token,
            'session_id': self.test_session_id
        })
        self.assertEqual(response.status_code, 400)

    @patch('app.handle_chat')
    def test_chat_endpoint(self, mock_handle_chat):
        mock_handle_chat.return_value = {"answer": "Test response"}
        response = self.app.post('/chat', json={
            'session_id': self.test_session_id,
            'message': "Test message"
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('answer', data)
        mock_handle_chat.assert_called_once_with(
            self.test_session_id,
            "Test message"
        )

    @patch('app.handle_modify_request')
    def test_modify_endpoint(self, mock_handle_modify):
        mock_handle_modify.return_value = {"answer": "Test response"}
        response = self.app.post('/modify_request', json={
            'session_id': self.test_session_id,
            'message': "Test message"
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('answer', data)
        mock_handle_modify.assert_called_once_with(
            self.test_session_id,
            "Test message"
        )

    @patch('app.apply_changes')
    def test_apply_endpoint(self, mock_apply):
        mock_apply.return_value = {"result": "Test response", "success": True}
        response = self.app.post('/apply_changes', json={
            'session_id': self.test_session_id,
            'file_name': self.test_file_path,
            'new_content': self.test_changes
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('result', data)
        self.assertIn('success', data)
        mock_apply.assert_called_once_with(
            self.test_session_id,
            self.test_file_path,
            self.test_changes,
            False,
            None
        )

if __name__ == '__main__':
    unittest.main()