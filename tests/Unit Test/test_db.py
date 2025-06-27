import os
import pytest
from dotenv import load_dotenv

# .env만 로드
load_dotenv()

# 상위 폴더의 db.py 불러오기
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import (
    create_user, get_user_by_username, get_user_by_email, get_user_by_github_id,
    update_user, update_last_login, create_session, delete_session, get_session_data_from_db, get_db_connection, init_db
)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    init_db()
    username = "unittest_user"
    email = "unittest@example.com"
    github_id = "unittest_github"
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM sessions WHERE session_id = %s", ("unittest_session",))
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))
            cursor.execute("DELETE FROM users WHERE email = %s", (email,))
            cursor.execute("DELETE FROM users WHERE github_id = %s", (github_id,))
        conn.commit()
        conn.close()
    yield
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM sessions WHERE session_id = %s", ("unittest_session",))
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))
            cursor.execute("DELETE FROM users WHERE email = %s", ("newemail@example.com",))
            cursor.execute("DELETE FROM users WHERE github_id = %s", (github_id,))
        conn.commit()
        conn.close()

def test_create_user_and_duplicate():
    username = "unittest_user"
    email = "unittest@example.com"
    password = "testpass"
    github_id = "unittest_github"
    success, result = create_user(username, email, password, github_id=github_id)
    assert success
    # 중복 이메일
    success, msg = create_user("other", email, "pw")
    assert not success
    assert "이메일" in msg
    # 중복 username
    success, msg = create_user(username, "other@example.com", "pw")
    assert not success
    assert "사용자 이름" in msg
    # 중복 github_id
    success, msg = create_user("other2", "other2@example.com", "pw", github_id=github_id)
    assert not success
    assert "GitHub" in msg

def test_get_user():
    username = "unittest_user"
    email = "unittest@example.com"
    password = "testpass"
    github_id = "unittest_github"
    create_user(username, email, password, github_id=github_id)
    user = get_user_by_username(username)
    assert user is not None
    assert user['email'] == email
    user2 = get_user_by_email(email)
    assert user2 is not None
    user3 = get_user_by_github_id(github_id)
    assert user3 is not None

def test_update_user():
    username = "unittest_user"
    email = "unittest@example.com"
    password = "testpass"
    create_user(username, email, password)
    user = get_user_by_username(username)
    success, msg = update_user(user['id'], {"email": "newemail@example.com"})
    assert success
    updated = get_user_by_email("newemail@example.com")
    assert updated is not None

def test_update_last_login():
    username = "unittest_user"
    email = "unittest@example.com"
    password = "testpass"
    create_user(username, email, password)
    user = get_user_by_username(username)
    assert update_last_login(user['id'])

def test_session_crud():
    username = "unittest_user"
    email = "unittest@example.com"
    password = "testpass"
    create_user(username, email, password)
    user = get_user_by_username(username)
    session_id = "unittest_session"
    assert create_session(session_id, user['id'])
    data = get_session_data_from_db(session_id)
    assert data is not None
    assert delete_session(session_id)
    assert get_session_data_from_db(session_id) is None
