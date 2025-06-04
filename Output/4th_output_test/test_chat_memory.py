import unittest
import os
from chat_memory import save_conversation, get_relevant_conversations, reset_memory

class TestChatMemory(unittest.TestCase):
    def setUp(self):
        self.test_session_id = "test_session"
        self.test_question = "이 함수는 무엇을 하나요?"
        self.test_response = "이 함수는 X 작업을 수행합니다"

    def tearDown(self):
        # 테스트 메모리 정리
        reset_memory(self.test_session_id)

    def test_save_conversation(self):
        """대화 저장 테스트"""
        result = save_conversation(
            self.test_session_id,
            self.test_question,
            self.test_response
        )
        self.assertTrue(result)

    def test_get_relevant_conversations(self):
        """관련 대화 검색 테스트"""
        # 테스트 대화 저장
        test_conversations = [
            ("로그인 함수는 어떻게 작동하나요?", "사용자 인증을 처리합니다"),
            ("메인 함수의 목적이 뭐인가요?", "프로그램의 진입점입니다"),
            ("에러 핸들링을 설명해주세요", "예외를 처리합니다")
        ]

        for question, response in test_conversations:
            save_conversation(
                self.test_session_id,
                question,
                response
            )

        # 관련 대화 검색 테스트
        relevant_conversations = get_relevant_conversations(
            self.test_session_id,
            "로그인 기능에 대해 알려주세요"
        )
        self.assertIsNotNone(relevant_conversations)
        self.assertNotEqual(relevant_conversations, "이전 대화 없음")

if __name__ == '__main__':
    unittest.main() 