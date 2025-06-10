import pymysql
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# GCP MySQL 연결 정보
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')
DB_PORT = int(os.environ.get('DB_PORT', 3306))

def get_db_connection():
    """데이터베이스 연결을 반환하는 함수"""
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection
    except Exception as e:
        print(f"[ERROR] 데이터베이스 연결 오류: {e}")
        return None

def init_db():
    """데이터베이스와 필요한 테이블들을 초기화하는 함수"""
    conn = get_db_connection()
    if not conn:
        print("[ERROR] 데이터베이스 연결 실패")
        return False
    
    try:
        with conn.cursor() as cursor:
            # 사용자 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255),
                is_github_user BOOLEAN DEFAULT FALSE,
                github_id VARCHAR(50) UNIQUE,
                github_username VARCHAR(50),
                github_token TEXT,
                github_avatar_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
            ''')
            
            # 세션 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id VARCHAR(255) PRIMARY KEY,
                user_id INT,
                repo_url TEXT,
                token TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            ''')
            
            # 채팅 기록 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(255),
                role VARCHAR(50),
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
            ''')
            
            # 코드 변경 내역 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS code_changes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(255),
                file_name TEXT,
                old_code LONGTEXT,
                new_code LONGTEXT,
                commit_hash TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
            ''')
        
        conn.commit()
        print("[INFO] 데이터베이스 테이블 초기화 완료")
        return True
    except Exception as e:
        print(f"[ERROR] 데이터베이스 테이블 생성 오류: {e}")
        return False
    finally:
        conn.close()

# 사용자 관리 함수들
def create_user(username, email, password=None, is_github_user=False, github_id=None, 
                github_username=None, github_token=None, github_avatar_url=None):
    """새 사용자를 생성하는 함수"""
    conn = get_db_connection()
    if not conn:
        return False, "데이터베이스 연결 실패"
    
    try:
        with conn.cursor() as cursor:
            sql = '''
            INSERT INTO users 
            (username, email, password, is_github_user, github_id, github_username, github_token, github_avatar_url) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            '''
            cursor.execute(sql, (username, email, password, is_github_user, github_id, 
                                github_username, github_token, github_avatar_url))
        conn.commit()
        return True, cursor.lastrowid
    except pymysql.err.IntegrityError as e:
        if "Duplicate entry" in str(e):
            if "username" in str(e):
                return False, "이미 사용 중인 사용자 이름입니다."
            elif "email" in str(e):
                return False, "이미 사용 중인 이메일입니다."
            elif "github_id" in str(e):
                return False, "이미 연결된 GitHub 계정입니다."
        return False, str(e)
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_user_by_username(username):
    """사용자 이름으로 사용자를 조회하는 함수"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM users WHERE username = %s"
            cursor.execute(sql, (username,))
            return cursor.fetchone()
    except Exception as e:
        print(f"[ERROR] 사용자 조회 오류: {e}")
        return None
    finally:
        conn.close()

def get_user_by_email(email):
    """이메일로 사용자를 조회하는 함수"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM users WHERE email = %s"
            cursor.execute(sql, (email,))
            return cursor.fetchone()
    except Exception as e:
        print(f"[ERROR] 사용자 조회 오류: {e}")
        return None
    finally:
        conn.close()

def get_user_by_github_id(github_id):
    """GitHub ID로 사용자를 조회하는 함수"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM users WHERE github_id = %s"
            cursor.execute(sql, (github_id,))
            return cursor.fetchone()
    except Exception as e:
        print(f"[ERROR] 사용자 조회 오류: {e}")
        return None
    finally:
        conn.close()

def update_user(user_id, data):
    """사용자 정보를 업데이트하는 함수"""
    conn = get_db_connection()
    if not conn:
        return False, "데이터베이스 연결 실패"
    
    try:
        placeholders = []
        values = []
        
        for key, value in data.items():
            placeholders.append(f"{key} = %s")
            values.append(value)
        
        values.append(user_id)  # WHERE 조건에 사용할 user_id
        
        with conn.cursor() as cursor:
            sql = f"UPDATE users SET {', '.join(placeholders)} WHERE id = %s"
            cursor.execute(sql, values)
        
        conn.commit()
        return True, "사용자 정보가 업데이트되었습니다."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_last_login(user_id):
    """사용자의 마지막 로그인 시간을 업데이트하는 함수"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s"
            cursor.execute(sql, (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] 로그인 시간 업데이트 오류: {e}")
        return False
    finally:
        conn.close()

def create_session(session_id, user_id, repo_url=None, token=None):
    """새 세션을 생성하는 함수"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            sql = '''
            INSERT INTO sessions (session_id, user_id, repo_url, token)
            VALUES (%s, %s, %s, %s)
            '''
            cursor.execute(sql, (session_id, user_id, repo_url, token))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] 세션 생성 오류: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    init_db() 