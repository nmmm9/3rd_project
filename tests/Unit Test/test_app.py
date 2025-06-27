import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_app_import():
    assert app is not None

def test_home_page(client):
    response = client.get('/')
    # 홈페이지가 정상적으로 렌더링되는지 확인
    assert response.status_code == 200
    # 실제 페이지에 있는 텍스트 확인
    data_str = response.data.decode(errors='ignore')
    assert 'github' in data_str.lower() or 'html' in data_str.lower()

def test_home_route(client):
    response = client.get('/')
    assert response.status_code == 200 or response.status_code in (301, 302)

def test_login_page(client):
    response = client.get('/login')
    assert response.status_code == 200
    data_str = response.data.decode(errors='ignore')
    assert 'Login' in data_str or 'Sign' in data_str

def test_login_get(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert 'login' in response.data.decode(errors='ignore').lower()

def test_login_post_invalid(client):
    response = client.post('/login', data={'username': 'no_user', 'password': 'wrong'})
    assert response.status_code == 200
    assert '로그인' in response.data.decode(errors='ignore') or 'login' in response.data.decode(errors='ignore').lower()

def test_signup_page(client):
    response = client.get('/signup')
    assert response.status_code == 200
    data_str = response.data.decode(errors='ignore')
    assert 'Sign Up' in data_str or '회원가입' in data_str or 'sign' in data_str.lower()

def test_signup_get(client):
    response = client.get('/signup')
    assert response.status_code == 200
    assert 'sign up' in response.data.decode(errors='ignore').lower() or '회원가입' in response.data.decode(errors='ignore')

def test_signup_post_invalid(client):
    response = client.post('/signup', data={'username': '', 'email': '', 'password': '', 'confirm': ''})
    assert response.status_code == 200
    assert '회원가입' in response.data.decode(errors='ignore') or 'sign up' in response.data.decode(errors='ignore').lower()

def test_logout_redirect(client):
    response = client.get('/logout')
    # 로그아웃 후 리다이렉트 또는 로그인 안내
    data_str = response.data.decode(errors='ignore')
    assert response.status_code in (301, 302) or '로그인' in data_str or 'login' in data_str.lower()

def test_logout(client):
    response = client.get('/logout')
    assert response.status_code in (301, 302)

def test_index_requires_login(client):
    response = client.get('/index')
    assert response.status_code in (301, 302)

def test_profile_requires_login(client):
    response = client.get('/profile')
    assert response.status_code in (301, 302)

def test_chat_api_requires_login(client):
    response = client.post('/chat', json={'session_id': 'dummy', 'message': 'test'})
    assert response.status_code == 401

def test_analyze_requires_login(client):
    response = client.post('/analyze', json={'repo_url': 'https://github.com/test/repo'})
    assert response.status_code == 401
