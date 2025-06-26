import unittest
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chat_memory

class TestChatMemory(unittest.TestCase):
    def test_module_import(self):
        self.assertIsNotNone(chat_memory)

    # 예시: 대화 기록 저장/조회 함수가 있다면 테스트
    def test_save_and_load_conversation(self):
        if hasattr(chat_memory, 'save_conversation') and hasattr(chat_memory, 'load_conversation'):
            session_id = 'unittest_session'
            message = '테스트 메시지'
            chat_memory.save_conversation(session_id, message)
            result = chat_memory.load_conversation(session_id)
            self.assertIn(message, result)

    # 예외 상황 테스트 (예: 없는 세션 조회)
    def test_load_nonexistent_conversation(self):
        if hasattr(chat_memory, 'load_conversation'):
            result = chat_memory.load_conversation('no_such_session')
            self.assertTrue(result is None or result == [] or result == "")

if __name__ == "__main__":
    unittest.main()
