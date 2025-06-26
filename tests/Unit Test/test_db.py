import unittest
from db import create_user, get_user_by_username, get_db_connection

class TestDB(unittest.TestCase):
    def setUp(self):
        self.username = "unittest_user"
        self.email = "unittest@example.com"
        self.password = "testpass"

    def test_create_and_get_user(self):
        success, result = create_user(self.username, self.email, self.password)
        self.assertTrue(success)
        user = get_user_by_username(self.username)
        self.assertIsNotNone(user)
        self.assertEqual(user['email'], self.email)

    def tearDown(self):
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE username=%s", (self.username,))
            conn.commit()
            conn.close()

if __name__ == "__main__":
    unittest.main() 