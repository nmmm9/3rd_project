import pymysql
import os
from dotenv import load_dotenv
import uuid

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
                username VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE,
                password_hash VARCHAR(255),
                is_github_user BOOLEAN DEFAULT FALSE,
                github_id VARCHAR(255),
                github_username VARCHAR(255),
                github_token VARCHAR(255),
                github_avatar_url VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP NULL
            )
            ''')
            
            # 세션 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL UNIQUE,
                user_id INT NOT NULL,
                repo_url VARCHAR(255),
                token VARCHAR(255),
                name VARCHAR(255),
                display_order INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            ''')
            
            # 채팅 기록 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
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
            
            # 필요한 경우 ALTER TABLE 명령으로 기존 테이블에 컬럼 추가
            try:
                # name 컬럼 추가 (IF NOT EXISTS 문법은 MySQL에서 지원하지 않으므로 예외 처리로 관리)
                try:
                    cursor.execute("ALTER TABLE sessions ADD COLUMN name VARCHAR(255)")
                    print("[INFO] sessions 테이블에 name 컬럼 추가됨")
                except Exception as column_error:
                    if "Duplicate column" in str(column_error):
                        print("[INFO] name 컬럼이 이미 존재합니다.")
                    else:
                        raise column_error
                
                # display_order 컬럼 추가
                try:
                    cursor.execute("ALTER TABLE sessions ADD COLUMN display_order INT DEFAULT 0")
                    print("[INFO] sessions 테이블에 display_order 컬럼 추가됨")
                except Exception as column_error:
                    if "Duplicate column" in str(column_error):
                        print("[INFO] display_order 컬럼이 이미 존재합니다.")
                    else:
                        raise column_error
                
            except Exception as e:
                print(f"[WARNING] 컬럼 추가 중 오류 발생: {e}")
                print("[INFO] 오류가 발생했지만 계속 진행합니다. (컬럼이 이미 존재할 수 있음)")
        
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

def get_session_by_repo_url(user_id, repo_url):
    """특정 사용자의 레포지토리 URL로 세션을 검색하는 함수"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cursor:
            # 최신 세션이 아닌 첫 번째 생성된 세션을 반환
            sql = "SELECT * FROM sessions WHERE user_id = %s AND repo_url = %s ORDER BY created_at ASC LIMIT 1"
            cursor.execute(sql, (user_id, repo_url))
            return cursor.fetchone()
    except Exception as e:
        print(f"[ERROR] 레포지토리 URL로 세션 검색 오류: {e}")
        return None
    finally:
        conn.close()

def get_chat_history(session_id, limit=100):
    """특정 세션의 채팅 기록을 가져오는 함수"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM chat_history WHERE session_id = %s ORDER BY timestamp ASC LIMIT %s"
            cursor.execute(sql, (session_id, limit))
            return cursor.fetchall()
    except Exception as e:
        print(f"[ERROR] 채팅 기록 조회 오류: {e}")
        return []
    finally:
        conn.close()

def add_chat_history(session_id, role, content):
    """채팅 기록을 데이터베이스에 추가하는 함수"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            sql = '''
            INSERT INTO chat_history (session_id, role, content)
            VALUES (%s, %s, %s)
            '''
            cursor.execute(sql, (session_id, role, content))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] 채팅 기록 추가 오류: {e}")
        return False
    finally:
        conn.close()

def create_new_chat_session(user_id, repo_url, token):
    """같은 사용자와 레포에 대한 새 채팅 세션을 만드는 함수"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        # 새 세션 ID 생성
        session_id = str(uuid.uuid4())
        
        with conn.cursor() as cursor:
            sql = '''
            INSERT INTO sessions (session_id, user_id, repo_url, token)
            VALUES (%s, %s, %s, %s)
            '''
            cursor.execute(sql, (session_id, user_id, repo_url, token))
        conn.commit()
        return session_id
    except Exception as e:
        print(f"[ERROR] 새 채팅 세션 생성 오류: {e}")
        return None
    finally:
        conn.close()

def get_all_chat_sessions(user_id, repo_url):
    """특정 사용자와 레포에 대한 모든 채팅 세션을 가져오는 함수"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cursor:
            sql = """
            SELECT 
                s.session_id, 
                s.created_at, 
                COALESCE((SELECT COUNT(*) FROM chat_history ch WHERE ch.session_id = s.session_id), 0) as message_count,
                (SELECT MAX(ch.timestamp) FROM chat_history ch WHERE ch.session_id = s.session_id) as last_message_time
            FROM sessions s
            WHERE s.user_id = %s AND s.repo_url = %s
            ORDER BY 
                CASE WHEN (SELECT MAX(ch.timestamp) FROM chat_history ch WHERE ch.session_id = s.session_id) IS NULL THEN 0 ELSE 1 END DESC,
                (SELECT MAX(ch.timestamp) FROM chat_history ch WHERE ch.session_id = s.session_id) DESC,
                s.created_at DESC
            """
            cursor.execute(sql, (user_id, repo_url))
            return cursor.fetchall()
    except Exception as e:
        print(f"[ERROR] 채팅 세션 목록 조회 오류: {e}")
        return []
    finally:
        conn.close()

def get_session_by_id(session_id):
    """세션 ID로 세션 정보를 조회하는 함수"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM sessions WHERE session_id = %s"
            cursor.execute(sql, (session_id,))
            return cursor.fetchone()
    except Exception as e:
        print(f"[ERROR] 세션 ID로 세션 조회 오류: {e}")
        return None
    finally:
        conn.close()

def update_session_name(session_id, new_name):
    """세션 이름을 업데이트하는 함수"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE sessions SET name = %s WHERE session_id = %s"
            cursor.execute(sql, (new_name, session_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] 세션 이름 업데이트 오류: {e}")
        return False
    finally:
        conn.close()

def update_session_order(session_id, reference_session_id, target_position):
    """세션 순서를 업데이트하는 함수"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        # 현재 세션의 순서 가져오기
        with conn.cursor() as cursor:
            sql = "SELECT display_order FROM sessions WHERE session_id = %s"
            cursor.execute(sql, (session_id,))
            current_order = cursor.fetchone()
            
            # 참조 세션의 순서 가져오기
            sql = "SELECT display_order FROM sessions WHERE session_id = %s"
            cursor.execute(sql, (reference_session_id,))
            reference_order = cursor.fetchone()
            
            if not current_order or not reference_order:
                return False
            
            current_order = current_order['display_order'] if current_order['display_order'] is not None else 0
            reference_order = reference_order['display_order'] if reference_order['display_order'] is not None else 0
            
            # 목표 위치에 따라 순서 변경
            if target_position == 'up':  # 위로 이동
                # 두 세션 사이의 모든 세션 순서 조정
                sql = """
                UPDATE sessions 
                SET display_order = display_order + 1 
                WHERE display_order >= %s AND display_order < %s
                """
                cursor.execute(sql, (reference_order, current_order))
                
                # 현재 세션 순서 변경
                sql = "UPDATE sessions SET display_order = %s WHERE session_id = %s"
                cursor.execute(sql, (reference_order, session_id))
                
            elif target_position == 'down':  # 아래로 이동
                # 두 세션 사이의 모든 세션 순서 조정
                sql = """
                UPDATE sessions 
                SET display_order = display_order - 1 
                WHERE display_order <= %s AND display_order > %s
                """
                cursor.execute(sql, (reference_order, current_order))
                
                # 현재 세션 순서 변경
                sql = "UPDATE sessions SET display_order = %s WHERE session_id = %s"
                cursor.execute(sql, (reference_order, session_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] 세션 순서 업데이트 오류: {e}")
        return False
    finally:
        conn.close()

def delete_session(session_id):
    """세션을 삭제하는 함수"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cursor:
            # 먼저 관련 채팅 기록 삭제
            sql = "DELETE FROM chat_history WHERE session_id = %s"
            cursor.execute(sql, (session_id,))
            
            # 세션 삭제
            sql = "DELETE FROM sessions WHERE session_id = %s"
            cursor.execute(sql, (session_id,))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] 세션 삭제 오류: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    init_db() 