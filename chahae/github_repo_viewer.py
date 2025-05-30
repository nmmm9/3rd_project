import subprocess
import sys

def install_required_packages():
    """필요한 패키지들을 자동으로 설치합니다."""
    required_packages = {
        'requests': '2.31.0',
        'python-dotenv': '1.0.0',
        'langchain': '0.1.0'
    }
    
    for package, version in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            print(f"[설치] {package} 패키지를 설치합니다...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", f"{package}=={version}"])
            print(f"[설치] {package} 패키지 설치 완료")

# 필요한 패키지 설치
install_required_packages()

import requests
import base64
import sys
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import os
from getpass import getpass
import platform
import subprocess
import shutil
from cryptography.fernet import Fernet
from langchain.schema import Document

# Windows 전용 모듈
if platform.system() == "Windows":
    import msvcrt

# ----------------- 상수 정의 -----------------
ENV_TOKEN_KEY = "GITHUB_TOKEN"
ENV_FILE = ".env"
KEY_FILE = ".key"  # 암호화 키 파일

# ----------------- Git 관련 기능 -----------------
def check_git_installation():
    """Git 설치 여부 확인"""
    git_path = shutil.which('git')
    if git_path:
        print(f"[Git] Git이 설치되어 있습니다: {git_path}")
        return True
    return False

def install_git():
    """Git 설치 시도"""
    if platform.system() != "Windows":
        print("[Git] Windows가 아닌 환경에서는 Git을 수동으로 설치해주세요.")
        print("Git 다운로드: https://git-scm.com/downloads")
        return False

    try:
        print("[Git] Git 설치를 시작합니다...")
        result = subprocess.run(
            ["winget", "install", "--id", "Git.Git", "-e", "--source", "winget"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print("[Git] Git 설치가 완료되었습니다.")
        print("[Git] 설치 후 프로그램을 다시 실행해주세요.")
        return True
    except subprocess.CalledProcessError as e:
        print("[Git] Git 설치 실패:")
        print(e.stderr)
        print("\n[Git] 수동으로 Git을 설치해주세요:")
        print("Git 다운로드: https://git-scm.com/downloads")
        return False

def setup_git():
    """Git 설치 확인 및 필요시 설치"""
    if check_git_installation():
        return True

    print("[Git] Git이 설치되어 있지 않습니다.")
    choice = input("Git을 설치하시겠습니까? (y/n): ").strip().lower()
    
    if choice == 'y':
        return install_git()
    else:
        print("[Git] Git 설치가 필요합니다.")
        print("Git 다운로드: https://git-scm.com/downloads")
        return False

# ----------------- 토큰 관련 기능 -----------------
def get_secure_input(prompt):
    """보안이 강화된 입력 처리"""
    if platform.system() == "Windows":
        print(prompt, end='', flush=True)
        password = []
        while True:
            key = msvcrt.getch()
            if key == b'\r':  # Enter 키
                print()  # 줄바꿈
                break
            elif key == b'\x08':  # Backspace 키
                if password:
                    password.pop()
                    print('\b \b', end='', flush=True)
            else:
                password.append(key)
                print('*', end='', flush=True)
        return ''.join(char.decode('utf-8') for char in password)
    else:
        return getpass(prompt)

def generate_key():
    """암호화 키 생성"""
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, 'wb') as key_file:
            key_file.write(key)
        return key
    else:
        with open(KEY_FILE, 'rb') as key_file:
            return key_file.read()

def encrypt_token(token):
    """토큰 암호화"""
    key = generate_key()
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token):
    """토큰 복호화"""
    key = generate_key()
    f = Fernet(key)
    return f.decrypt(encrypted_token.encode()).decode()

def create_env_file(token):
    """환경 변수 파일 생성"""
    if os.path.exists(ENV_FILE):
        return False
        
    try:
        # 토큰 암호화
        encrypted_token = encrypt_token(token)
        
        with open(ENV_FILE, 'w', encoding='utf-8') as f:
            f.write(f"{ENV_TOKEN_KEY}={encrypted_token}\n")
        print("[환경] 토큰이 안전하게 암호화되어 저장되었습니다.")
        return True
    except Exception as e:
        print(f"[오류] 토큰 저장 실패: {str(e)}")
        return False

def setup_environment():
    """환경 설정 (토큰 관리)"""
    # .env 파일 처리
    if os.path.exists(ENV_FILE):
        while True:
            print(f"\n[환경] 기존 환경 파일 ({ENV_FILE})이 있습니다.")
            choice = input("저장된 GitHub 토큰을 사용하시겠습니까? (y/n): ").strip().lower()
            
            if choice == 'y':
                load_dotenv()
                encrypted_token = os.getenv(ENV_TOKEN_KEY)
                if encrypted_token:
                    try:
                        token = decrypt_token(encrypted_token)
                        os.environ[ENV_TOKEN_KEY] = token
                        print("[환경] 저장된 토큰을 사용합니다.")
                        return token
                    except Exception as e:
                        print(f"[오류] 토큰 복호화 실패: {str(e)}")
                        print("[환경] 저장된 토큰 파일에 문제가 있습니다. 새 토큰을 입력합니다.")
                        break
                else:
                    print("[오류] 환경 파일에 토큰이 없습니다. 새 토큰을 입력합니다.")
                    break
            
            elif choice == 'n':
                print("[환경] 새 GitHub 토큰을 입력합니다.")
                # 기존 .env 및 .key 파일 삭제
                if os.path.exists(ENV_FILE):
                    os.remove(ENV_FILE)
                    print(f"[환경] 기존 파일 삭제: {ENV_FILE}")
                if os.path.exists(KEY_FILE):
                    os.remove(KEY_FILE)
                    print(f"[환경] 기존 파일 삭제: {KEY_FILE}")
                break
            
            else:
                print("[오류] 잘못된 입력입니다. 'y' 또는 'n'을 입력해주세요.")

    # .env 파일이 없거나 기존 파일 삭제 후 새로 입력받는 경우
    print("\n[환경] GitHub 토큰을 입력해주세요.")
    if platform.system() == "Windows":
        token = get_secure_input("GitHub 토큰: ").strip()
    else:
        token = getpass("GitHub 토큰: ").strip()

    if not token:
        print("[오류] 토큰이 입력되지 않았습니다.")
        sys.exit(1)

    if not create_env_file(token):
        sys.exit(1)

    # 새로 저장된 토큰 로드 및 설정
    load_dotenv()
    encrypted_token = os.getenv(ENV_TOKEN_KEY)
    if encrypted_token:
        try:
            token = decrypt_token(encrypted_token)
            os.environ[ENV_TOKEN_KEY] = token
            print("[환경] 새 토큰이 설정되었습니다.")
            return token
        except Exception as e:
            print(f"[오류] 새로 저장된 토큰 복호화 실패: {str(e)}")
            sys.exit(1)
    else:
        print("[오류] 토큰을 불러올 수 없습니다.")
        sys.exit(1)

# ----------------- GitHub API 기능 -----------------
def get_repo_content(owner: str, repo: str, path: str, token: str) -> Optional[Dict[str, Any]]:
    """
    GitHub API를 사용하여 저장소의 파일 내용을 가져옵니다.
    
    Args:
        owner (str): 저장소 소유자
        repo (str): 저장소 이름
        path (str): 파일 경로
        token (str): GitHub 개인 액세스 토큰
    
    Returns:
        Optional[Dict[str, Any]]: 파일 내용과 메타데이터를 포함하는 딕셔너리 또는 None (파일이 없는 경우)
    """
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        # API 호출 제한(레이트 리밋) 체크
        if response.status_code == 403:
            print("[API] 호출 제한 초과: GitHub API Rate Limit에 걸렸습니다. 잠시 후 다시 시도하세요.")
            return None
            
        if response.status_code == 404:
            print(f"[API] 파일을 찾을 수 없습니다: {path}")
            return None
            
        if response.status_code != 200:
            print(f"[API] 오류 발생: {response.status_code} - {response.text}")
            return None
        
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[API] 요청 실패: {str(e)}")
        return None
    except Exception as e:
        print(f"[API] 예상치 못한 오류: {str(e)}")
        return None

def get_repo_content_with_metadata(owner: str, repo: str, path: str, token: str) -> Dict[str, Any]:
    """
    GitHub API를 사용하여 저장소의 파일 내용과 메타데이터를 가져옵니다.
    
    Args:
        owner (str): 저장소 소유자
        repo (str): 저장소 이름
        path (str): 파일 경로
        token (str): GitHub 개인 액세스 토큰
    
    Returns:
        Dict[str, Any]: 파일 내용과 메타데이터를 포함하는 딕셔너리
    """
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        # API 호출 제한(레이트 리밋) 체크
        if response.status_code == 403:
            print("[API] 호출 제한 초과: GitHub API Rate Limit에 걸렸습니다. 잠시 후 다시 시도하세요.")
            return {}
            
        if response.status_code == 404:
            print(f"[API] 파일을 찾을 수 없습니다: {path}")
            return {}
            
        if response.status_code != 200:
            print(f"[API] 오류 발생: {response.status_code} - {response.text}")
            return {}
        
        content = response.json()
        if isinstance(content, dict):
            result = {
                "name": content.get("name"),
                "path": content.get("path"),
                "sha": content.get("sha"),
                "size": content.get("size"),
                "url": content.get("url"),
                "html_url": content.get("html_url"),
                "git_url": content.get("git_url"),
                "download_url": content.get("download_url"),
                "type": content.get("type"),
                "content": None
            }
            
            if "content" in content:
                try:
                    result["content"] = base64.b64decode(content["content"]).decode("utf-8")
                except UnicodeDecodeError:
                    print("[API] 파일이 텍스트 형식이 아닙니다.")
                    result["content"] = None
                except Exception as e:
                    print(f"[API] 파일 내용 디코딩 실패: {str(e)}")
                    result["content"] = None
            
            return result
        return {}
    except requests.exceptions.RequestException as e:
        print(f"[API] 요청 실패: {str(e)}")
        return {}
    except Exception as e:
        print(f"[API] 예상치 못한 오류: {str(e)}")
        return {}

def get_repo_directory_contents(owner: str, repo: str, path: str, token: str) -> Optional[list]:
    """
    GitHub API를 사용하여 저장소의 디렉토리 내용을 가져옵니다.
    
    Args:
        owner (str): 저장소 소유자
        repo (str): 저장소 이름
        path (str): 디렉토리 경로
        token (str): GitHub 개인 액세스 토큰
    
    Returns:
        Optional[list]: 디렉토리 내용 목록 또는 None (디렉토리가 없는 경우)
    """
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        # API 호출 제한(레이트 리밋) 체크
        if response.status_code == 403:
            print("[API] 호출 제한 초과: GitHub API Rate Limit에 걸렸습니다. 잠시 후 다시 시도하세요.")
            return None
            
        if response.status_code == 404:
            print(f"[API] 디렉토리를 찾을 수 없습니다: {path}")
            return None
            
        if response.status_code != 200:
            print(f"[API] 오류 발생: {response.status_code} - {response.text}")
            return None
        
        content = response.json()
        if isinstance(content, list):
            return content
        return None
    except requests.exceptions.RequestException as e:
        print(f"[API] 요청 실패: {str(e)}")
        return None
    except Exception as e:
        print(f"[API] 예상치 못한 오류: {str(e)}")
        return None

# ----------------- 저장소 정보 추출 기능 -----------------

def extract_repo_info(url: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    GitHub URL에서 소유자, 저장소 이름, 파일 경로를 추출합니다.
    
    Args:
        url (str): GitHub 저장소 URL
    
    Returns:
        tuple[Optional[str], Optional[str], Optional[str]]: (owner, repo, path) 또는 (None, None, None)
    """
    try:
        # URL에서 불필요한 부분 제거
        url = url.strip().rstrip('/')
        if url.endswith('.git'):
            url = url[:-4]
            
        # URL 파싱
        parts = url.split('/')
        if 'github.com' in parts:
            github_index = parts.index('github.com')
            if len(parts) >= github_index + 3:
                owner = parts[github_index + 1]
                repo = parts[github_index + 2]
                # 파일 경로가 있는 경우 추출
                path = '/'.join(parts[github_index + 3:]) if len(parts) > github_index + 3 else None
                return owner, repo, path
    except Exception as e:
        print(f"URL 파싱 중 오류 발생: {e}")
    return None, None, None

def get_repo_content_as_document(owner: str, repo: str, path: str, token: str) -> Optional[Document]:
    """
    GitHub API를 사용하여 저장소의 파일 내용을 LangChain Document로 가져옵니다.
    
    Args:
        owner (str): 저장소 소유자
        repo (str): 저장소 이름
        path (str): 파일 경로
        token (str): GitHub 개인 액세스 토큰
    
    Returns:
        Optional[Document]: LangChain Document 객체 또는 None (파일이 없는 경우)
    """
    try:
        content_data = get_repo_content(owner, repo, path, token)
        if not content_data:
            return None
        
        # Base64로 인코딩된 내용을 디코딩
        content = base64.b64decode(content_data['content']).decode('utf-8')
        
        # Document 객체 생성
        return Document(
            page_content=content,
            metadata={
                'source': content_data['html_url'],
                'file_name': content_data['name'],
                'file_path': content_data['path'],
                'sha': content_data['sha'],
                'size': content_data['size'],
                'type': content_data['type']
            }
        )
    except Exception as e:
        print(f"Document 변환 중 오류 발생: {e}")
        return None

def get_repo_directory_as_documents(owner: str, repo: str, path: str, token: str) -> List[Document]:
    """
    GitHub API를 사용하여 저장소의 디렉토리 내용을 LangChain Document 리스트로 가져옵니다.
    
    Args:
        owner (str): 저장소 소유자
        repo (str): 저장소 이름
        path (str): 디렉토리 경로
        token (str): GitHub 개인 액세스 토큰
    
    Returns:
        List[Document]: LangChain Document 객체 리스트
    """
    documents = []
    try:
        dir_contents = get_repo_directory_contents(owner, repo, path, token)
        if not dir_contents:
            return documents
            
        for item in dir_contents:
            if item['type'] == 'file':
                doc = get_repo_content_as_document(owner, repo, item['path'], token)
                if doc:
                    documents.append(doc)
            elif item['type'] == 'dir':
                # 재귀적으로 하위 디렉토리 처리
                sub_docs = get_repo_directory_as_documents(owner, repo, item['path'], token)
                documents.extend(sub_docs)
                
        return documents
    except Exception as e:
        print(f"[API] Document 리스트 생성 실패: {str(e)}")
        return documents

def get_all_repo_contents(owner: str, repo: str, token: str) -> List[Document]:
    """
    GitHub 저장소의 모든 파일과 폴더를 LangChain Document 리스트로 가져옵니다.
    
    Args:
        owner (str): 저장소 소유자
        repo (str): 저장소 이름
        token (str): GitHub 개인 액세스 토큰
    
    Returns:
        List[Document]: 모든 파일의 LangChain Document 객체 리스트
    """
    documents = []
    try:
        # 루트 디렉토리부터 시작
        root_contents = get_repo_directory_contents(owner, repo, "", token)
        if not root_contents:
            return documents
            
        for item in root_contents:
            if item['type'] == 'file':
                doc = get_repo_content_as_document(owner, repo, item['path'], token)
                if doc:
                    documents.append(doc)
            elif item['type'] == 'dir':
                # 재귀적으로 하위 디렉토리 처리
                sub_docs = get_repo_directory_as_documents(owner, repo, item['path'], token)
                documents.extend(sub_docs)
                
        return documents
    except Exception as e:
        print(f"[API] 전체 저장소 내용 가져오기 실패: {str(e)}")
        return documents

def main(token: Optional[str] = None):
    # 환경 설정 수행 (토큰 관리)
    if token is None:
        token = setup_environment()
    
    # Git 설치 확인
    setup_git()
    
    # 저장소 URL 입력 받기
    while True:
        repo_url = input("GitHub 저장소 URL을 입력하세요: ").strip()
        owner, repo, path = extract_repo_info(repo_url)
        
        if owner and repo:
            print(f"\n[정보] 저장소 소유자: {owner}")
            print(f"[정보] 저장소 이름: {repo}")
            if path:
                print(f"[정보] 파일 경로: {path}")
            break
        else:
            print("[오류] 올바른 GitHub 저장소 URL을 입력해주세요.")
            print("예시: https://github.com/octocat/Hello-World")
            print("또는: https://github.com/octocat/Hello-World/blob/main/README.md")

    # 파일 경로가 URL에 없는 경우에만 입력 받기
    if not path:
        path = input("파일 또는 디렉토리 경로를 입력하세요 (예: README.md) 또는 'all'을 입력하여 전체 저장소를 가져오세요: ").strip()

    if path.lower() == 'all':
        # 전체 저장소 내용 가져오기
        print("\n[정보] 전체 저장소 내용을 가져오는 중...")
        return get_all_repo_contents(owner, repo, token)
    else:
        # 단일 파일 또는 디렉토리 가져오기
        doc = get_repo_content_as_document(owner, repo, path, token)
        if doc:
            return [doc]
        else:
            # 디렉토리인 경우 모든 파일을 Document로 가져오기
            return get_repo_directory_as_documents(owner, repo, path, token)

if __name__ == "__main__":
    # 저장소의 모든 파일 내용을 변수에 저장
    repo_documents = main()
    
    # 이제 repo_documents 변수에서 각 파일의 내용과 메타데이터에 접근가능
    # 예시:
    # for doc in repo_documents:
    #     content = doc.page_content  # 파일 내용
    #     metadata = doc.metadata    # 파일 메타데이터
    #     file_name = metadata['file_name']  # 파일 이름
    #     file_path = metadata['file_path']  # 파일 경로


    # 확인용으로 변수 내용 출력
    print(len(repo_documents))
    print("==================page_content=================")
    print(repo_documents[150].page_content)
    print("===============================================")
    print("==================metadata=================")
    print(repo_documents[150].metadata)
    print("===============================================")
    print("==================file_name=================")
    print(repo_documents[150].metadata['file_name'])
    print("===============================================")
    print("==================file_path=================")
    print(repo_documents[150].metadata['file_path'])
    print("===============================================")
