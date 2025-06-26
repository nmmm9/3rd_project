import unittest
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import (
    create_user, get_user_by_username, get_user_by_email, get_user_by_github_id,
    update_user, update_last_login, create_session, delete_session, get_session_data_from_db, get_db_connection
)

class TestDB(unittest.TestCase):
    def setUp(self):
        self.username = "unittest_user"
        self.email = "unittest@example.com"
        self.password = "testpass"
        self.github_id = "unittest_github"
        self.user_id = None
                # 테스트 시작 전 혹시 남아있을지 모를 데이터 삭제
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE username=%s", (self.username,))
                cursor.execute("DELETE FROM users WHERE email=%s", (self.email,))
            conn.commit()
            conn.close()


    def test_create_user_and_duplicate(self):
        # 정상 생성
        success, result = create_user(self.username, self.email, self.password, github_id=self.github_id)
        self.assertTrue(success)
        self.user_id = result

        # 중복 이메일
        success, msg = create_user("other", self.email, "pw")
        self.assertFalse(success)
        self.assertIn("이메일", msg)

        # 중복 username
        success, msg = create_user(self.username, "other@example.com", "pw")
        self.assertFalse(success)
        self.assertIn("사용자 이름", msg)

        # 중복 github_id
        success, msg = create_user("other2", "other2@example.com", "pw", github_id=self.github_id)
        self.assertFalse(success)
        self.assertIn("GitHub", msg)

    def test_get_user(self):
        create_user(self.username, self.email, self.password, github_id=self.github_id)
        user = get_user_by_username(self.username)
        self.assertIsNotNone(user)
        self.assertEqual(user['email'], self.email)
        user2 = get_user_by_email(self.email)
        self.assertIsNotNone(user2)
        user3 = get_user_by_github_id(self.github_id)
        self.assertIsNotNone(user3)

    def test_update_user(self):
        create_user(self.username, self.email, self.password)
        user = get_user_by_username(self.username)
        success, msg = update_user(user['id'], {"email": "newemail@example.com"})
        self.assertTrue(success)
        updated = get_user_by_email("newemail@example.com")
        self.assertIsNotNone(updated)

    def test_update_last_login(self):
        create_user(self.username, self.email, self.password)
        user = get_user_by_username(self.username)
        self.assertTrue(update_last_login(user['id']))

    def test_session_crud(self):
        create_user(self.username, self.email, self.password)
        user = get_user_by_username(self.username)
        session_id = "unittest_session"
        self.assertTrue(create_session(session_id, user['id']))
        data = get_session_data_from_db(session_id)
        self.assertIsNotNone(data)
        self.assertTrue(delete_session(session_id))
        self.assertIsNone(get_session_data_from_db(session_id))

    def tearDown(self):
        # 테스트 데이터 정리
        from db import get_db_connection
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE username=%s", (self.username,))
                cursor.execute("DELETE FROM users WHERE email=%s", ("newemail@example.com",))
                cursor.execute("DELETE FROM sessions WHERE session_id=%s", ("unittest_session",))
            conn.commit()
            conn.close()

if __name__ == "__main__":
    unittest.main()
