"""
GitHub 저장소 분석 및 임베딩을 위한 모듈

이 모듈은 GitHub 저장소의 내용을 가져와서 분석하고, 
LangChain Document로 변환한 후 ChromaDB에 임베딩하여 저장하는 기능을 제공합니다.

주요 클래스:
    - GitHubRepositoryFetcher: GitHub 저장소에서 파일을 가져오는 클래스
    - RepositoryEmbedder: 저장소 내용을 임베딩하는 클래스

주요 함수:
    - analyze_repository: GitHub 저장소를 분석하고 임베딩하는 메인 함수
    - get_repository_branches: GitHub 저장소의 브랜치 목록을 가져오는 함수
    - get_repository_file_tree: GitHub 저장소의 특정 브랜치 파일 구조를 가져오는 함수
    - get_file_content: GitHub 저장소의 특정 파일 내용을 가져오는 함수
"""

import requests
import chromadb
import os
import re
import openai
import git
import base64
from typing import Optional, List, Dict, Any, Tuple, Union
from langchain.schema import Document
from cryptography.fernet import Fernet
import tiktoken
import ast
import markdown
import concurrent.futures
import asyncio
import sys
import nbformat

# ----------------- 상수 정의 -----------------
MAIN_EXTENSIONS = ['.py', '.js', '.md', '.ts', '.java', '.cpp', '.h', '.hpp', '.c', '.cs', '.txt','.ipynb']  # 분석할 주요 파일 확장자
CHUNK_SIZE = 500  # 텍스트 청크 크기
GITHUB_TOKEN = "GITHUB_TOKEN"  # 환경 변수 키 이름
KEY_FILE = ".key"  # 암호화 키 파일

# ChromaDB 영구 저장소 클라이언트
REPO_DB_PATH = "./repo_analysis_db"
os.makedirs(REPO_DB_PATH, exist_ok=True)
chroma_client = chromadb.PersistentClient(path=REPO_DB_PATH)

def analyze_repository(repo_url: str, token: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    GitHub 저장소를 분석하고 임베딩하는 함수
    
    Args:
        repo_url (str): GitHub 저장소 URL
        token (Optional[str]): GitHub 개인 액세스 토큰
        session_id (Optional[str]): 세션 ID
        
    Returns:
        Dict[str, Any]: 분석 결과
    """
    try:
        print(f"[DEBUG] 저장소 분석 시작: {repo_url}")
        
        # ChromaDB 디렉토리 정리 (차원 불일치 문제 해결)
        if session_id:
            cleanup_chromadb_for_session(session_id)
        
        # 저장소 정보 가져오기 (GitHub API 사용)
        fetcher = GitHubRepositoryFetcher(repo_url, token, session_id)
        
        # GitHub API를 통한 데이터 로드 (클론 불필요)
        print(f"[DEBUG] GitHub API를 통한 데이터 로드 시작")
        if not fetcher.load_repo_data():
            return {'success': False, 'error': '저장소 데이터를 로드할 수 없습니다.'}
        print(f"[DEBUG] GitHub API 데이터 로드 완료")
        
        files = fetcher.get_file_contents()
        if not files:
            return {'success': False, 'error': '저장소에서 파일을 찾을 수 없습니다.'}
        
        # 디렉토리 구조 생성
        directory_structure = fetcher.get_directory_structure()
        
        print(f"[DEBUG] 파일 수집 완료: {len(files)} 파일")
        
        # 임베딩 처리
        if session_id:
            embedder = RepositoryEmbedder(session_id)
            embedder.process_and_embed(files)
            print(f"[DEBUG] 임베딩 처리 완료")
        
        return {
            'success': True,
            'files': files,
            'directory_structure': directory_structure,
            'total_files': len(files)
        }
        
    except Exception as e:
        import traceback
        print(f"[ERROR] 저장소 분석 실패: {e}")
        traceback.print_exc()
        return {'success': False, 'error': f'저장소 분석 중 오류 발생: {str(e)}'}

def cleanup_chromadb_for_session(session_id: str):
    """
    특정 세션의 ChromaDB 데이터를 정리하는 함수
    
    Args:
        session_id (str): 세션 ID
    """
    try:
        import os
        import shutil
        
        # ChromaDB 디렉토리 경로
        chroma_path = os.path.join("repo_analysis_db", session_id)
        
        if os.path.exists(chroma_path):
            print(f"[DEBUG] ChromaDB 디렉토리 삭제: {chroma_path}")
            shutil.rmtree(chroma_path)
            
    except Exception as e:
        print(f"[WARNING] ChromaDB 정리 중 오류 (무시 가능): {e}")

def get_repository_branches(repo_url: str, token: Optional[str] = None) -> Dict[str, Any]:
    """
    GitHub 저장소의 브랜치 목록을 가져옵니다.
    
    Args:
        repo_url (str): GitHub 저장소 URL
        token (Optional[str]): GitHub 개인 액세스 토큰
        
    Returns:
        Dict[str, Any]: 브랜치 목록 또는 에러 정보
    """
    try:
        print(f"[DEBUG] get_repository_branches 시작: repo_url={repo_url}, token={'있음' if token else '없음'}")
        
        # URL에서 owner, repo 추출
        fetcher = GitHubRepositoryFetcher(repo_url, token)
        owner, repo = fetcher.owner, fetcher.repo
        print(f"[DEBUG] 저장소 정보 추출: owner={owner}, repo={repo}")
        
        # GitHub API로 브랜치 목록 가져오기
        url = f"https://api.github.com/repos/{owner}/{repo}/branches"
        headers = {
            'User-Agent': 'GitHub-Code-Analyzer/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        if token:
            headers['Authorization'] = f'token {token}'
        
        print(f"[DEBUG] GitHub API 호출: {url}")
        print(f"[DEBUG] 헤더 존재: {'Authorization' in headers}")
        print(f"[DEBUG] 토큰 첫 8자리: {token[:8] if token else 'None'}...")
        
        response = requests.get(url, headers=headers, timeout=30)
        print(f"[DEBUG] API 응답: status_code={response.status_code}")
        
        if response.status_code == 200:
            branches = response.json()
            print(f"[DEBUG] 브랜치 목록 수신: {len(branches)}개")
            branch_list = [{'name': branch['name'], 'sha': branch['commit']['sha']} for branch in branches]
            print(f"[DEBUG] 브랜치 이름들: {[b['name'] for b in branch_list]}")
            return {
                'success': True,
                'branches': branch_list
            }
        else:
            error_msg = f'브랜치 목록을 가져올 수 없습니다: {response.status_code}'
            print(f"[ERROR] GitHub API 실패: {error_msg}")
            print(f"[ERROR] 응답 내용: {response.text[:500]}")  # 처음 500자만 로그
            return {
                'success': False,
                'error': error_msg,
                'message': response.text,
                'status_code': response.status_code,
                'url': url
            }
            
    except requests.exceptions.Timeout as e:
        print(f"[ERROR] GitHub API 타임아웃: {str(e)}")
        return {
            'success': False,
            'error': f'GitHub API 타임아웃 발생: {str(e)}'
        }
    except requests.exceptions.ConnectionError as e:
        print(f"[ERROR] GitHub API 연결 오류: {str(e)}")
        return {
            'success': False,
            'error': f'GitHub API 연결 실패: {str(e)}'
        }
    except Exception as e:
        import traceback
        print(f"[ERROR] get_repository_branches 예외 발생: {str(e)}")
        traceback.print_exc()
        return {
            'success': False,
            'error': f'브랜치 목록 조회 중 오류 발생: {str(e)}'
        }

def get_repository_file_tree(repo_url: str, branch: str = 'main', token: Optional[str] = None) -> Dict[str, Any]:
    """
    GitHub 저장소의 특정 브랜치 파일 구조를 가져옵니다.
    
    Args:
        repo_url (str): GitHub 저장소 URL
        branch (str): 브랜치 이름 (기본값: 'main')
        token (Optional[str]): GitHub 개인 액세스 토큰
        
    Returns:
        Dict[str, Any]: 파일 구조 또는 에러 정보
    """
    try:
        print(f"[DEBUG] get_repository_file_tree 시작: repo_url={repo_url}, branch={branch}, token={'있음' if token else '없음'}")
        
        # URL에서 owner, repo 추출
        fetcher = GitHubRepositoryFetcher(repo_url, token)
        owner, repo = fetcher.owner, fetcher.repo
        print(f"[DEBUG] 저장소 정보 추출: owner={owner}, repo={repo}")
        
        # GitHub API로 파일 트리 가져오기
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        headers = {
            'User-Agent': 'GitHub-Code-Analyzer/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        if token:
            headers['Authorization'] = f'token {token}'
        
        print(f"[DEBUG] GitHub API 호출: {url}")
        print(f"[DEBUG] 헤더 존재: {'Authorization' in headers}")
        
        response = requests.get(url, headers=headers)
        print(f"[DEBUG] API 응답: status_code={response.status_code}")
        
        if response.status_code == 200:
            tree_data = response.json()
            print(f"[DEBUG] 파일 트리 데이터 크기: {len(tree_data.get('tree', []))}")
            
            # 파일과 디렉토리를 구분하여 정리
            files = []
            directories = []
            
            for item in tree_data.get('tree', []):
                if item['type'] == 'blob':  # 파일
                    files.append({
                        'path': item['path'],
                        'sha': item['sha'],
                        'size': item.get('size', 0),
                        'type': 'file'
                    })
                elif item['type'] == 'tree':  # 디렉토리
                    directories.append({
                        'path': item['path'],
                        'sha': item['sha'],
                        'type': 'directory'
                    })
            
            print(f"[DEBUG] 파일 트리 정리 완료: 파일={len(files)}개, 디렉토리={len(directories)}개")
            
            return {
                'success': True,
                'files': files,
                'directories': directories,
                'total_files': len(files),
                'total_directories': len(directories)
            }
        else:
            error_msg = f'파일 구조를 가져올 수 없습니다: {response.status_code}'
            print(f"[ERROR] GitHub API 실패: {error_msg}")
            print(f"[ERROR] 응답 내용: {response.text[:500]}")  # 처음 500자만 로그
            return {
                'success': False,
                'error': error_msg,
                'message': response.text,
                'status_code': response.status_code,
                'url': url
            }
            
    except Exception as e:
        import traceback
        print(f"[ERROR] get_repository_file_tree 예외 발생: {str(e)}")
        traceback.print_exc()
        return {
            'success': False,
            'error': f'파일 구조 조회 중 오류 발생: {str(e)}'
        }

def get_file_content(repo_url: str, file_path: str, branch: str = 'main', token: Optional[str] = None) -> Dict[str, Any]:
    """
    GitHub 저장소의 특정 파일 내용을 가져옵니다.
    
    Args:
        repo_url (str): GitHub 저장소 URL
        file_path (str): 파일 경로
        branch (str): 브랜치 이름 (기본값: 'main')
        token (Optional[str]): GitHub 개인 액세스 토큰
        
    Returns:
        Dict[str, Any]: 파일 내용 또는 에러 정보
    """
    try:
        print(f"[DEBUG] get_file_content 시작: repo_url={repo_url}, file_path={file_path}, branch={branch}, token={'있음' if token else '없음'}")
        
        # URL에서 owner, repo 추출
        fetcher = GitHubRepositoryFetcher(repo_url, token)
        owner, repo = fetcher.owner, fetcher.repo
        print(f"[DEBUG] 저장소 정보 추출: owner={owner}, repo={repo}")
        
        # GitHub API로 파일 내용 가져오기
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={branch}"
        headers = {
            'User-Agent': 'GitHub-Code-Analyzer/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        if token:
            headers['Authorization'] = f'token {token}'
        
        print(f"[DEBUG] GitHub API 호출: {url}")
        print(f"[DEBUG] 헤더 존재: {'Authorization' in headers}")
        
        response = requests.get(url, headers=headers)
        print(f"[DEBUG] API 응답: status_code={response.status_code}")
        
        if response.status_code == 200:
            file_data = response.json()
            print(f"[DEBUG] 파일 데이터 수신: size={file_data.get('size', 0)}, encoding={file_data.get('encoding', 'unknown')}")
            
            # Base64로 인코딩된 내용을 디코딩
            if file_data.get('encoding') == 'base64':
                try:
                    content = base64.b64decode(file_data['content']).decode('utf-8')
                    print(f"[DEBUG] Base64 디코딩 성공: 내용 길이={len(content)}")
                except UnicodeDecodeError:
                    # 바이너리 파일인 경우
                    print(f"[DEBUG] 바이너리 파일 감지: {file_path}")
                    return {
                        'success': False,
                        'error': '바이너리 파일은 표시할 수 없습니다.',
                        'is_binary': True
                    }
            else:
                content = file_data.get('content', '')
                print(f"[DEBUG] 직접 내용 사용: 길이={len(content)}")
            
            return {
                'success': True,
                'content': content,
                'size': file_data.get('size', 0),
                'sha': file_data.get('sha', ''),
                'path': file_path,
                'encoding': file_data.get('encoding', 'utf-8')
            }
        else:
            error_msg = f'파일 내용을 가져올 수 없습니다: {response.status_code}'
            print(f"[ERROR] GitHub API 실패: {error_msg}")
            print(f"[ERROR] 응답 내용: {response.text[:500]}")  # 처음 500자만 로그
            return {
                'success': False,
                'error': error_msg,
                'message': response.text,
                'status_code': response.status_code,
                'url': url
            }
            
    except Exception as e:
        import traceback
        print(f"[ERROR] get_file_content 예외 발생: {str(e)}")
        traceback.print_exc()
        return {
            'success': False,
            'error': f'파일 내용 조회 중 오류 발생: {str(e)}'
        }

class GitHubRepositoryFetcher:
    """
    GitHub 저장소에서 파일을 가져오는 클래스
    
    이 클래스는 GitHub API를 사용하여 저장소의 파일과 디렉토리를 가져오고,
    LangChain Document 형식으로 변환하는 기능을 제공합니다.
    """
    
    def __init__(self, repo_url: str, token: Optional[str] = None, session_id: Optional[str] = None):
        """
        GitHub 저장소 뷰어 초기화
        
        Args:
            repo_url (str): GitHub 저장소 URL
            token (Optional[str]): GitHub 개인 액세스 토큰
            session_id (Optional[str]): 세션 ID (기본값: owner_repo)
        """
        self.repo_url = repo_url
        self.token = token
        self.headers = {'Authorization': f'token {token}'} if token else {}
        self.files = []
        
        # 저장소 정보 추출
        self.owner, self.repo, self.path = self.extract_repo_info(repo_url)
        if not self.owner or not self.repo:
            raise ValueError("Invalid GitHub repository URL")
            
        # 세션 및 저장소 경로 설정
        self.session_id = session_id or f"{self.owner}_{self.repo}"
        self.repo_path = f"./repos/{self.session_id}"
        
        # ChromaDB 컬렉션 초기화
        self.collection = chroma_client.get_or_create_collection(
            name=self.session_id,
            metadata={"description": f"Repository: {self.owner}/{self.repo}"}
        )

    def create_error_response(self, message: str, status_code: int) -> Dict[str, Any]:
        """
        API 에러 응답 생성
        
        Args:
            message (str): 에러 메시지
            status_code (int): HTTP 상태 코드
            
        Returns:
            Dict[str, Any]: 에러 정보를 포함하는 딕셔너리
        """
        return {
            'error': True,
            'message': message,
            'status_code': status_code
        }

    def handle_github_response(self, response: requests.Response, path: Optional[str] = None) -> Dict[str, Any]:
        """
        GitHub API 응답 처리
        
        Args:
            response (requests.Response): GitHub API 응답
            path (str, optional): 요청한 파일/디렉토리 경로
            
        Returns:
            Dict[str, Any]: 처리된 응답 데이터 또는 에러 정보
        """
        if response.status_code == 403:
            return self.create_error_response(
                'GitHub API 호출 제한에 도달했습니다. 잠시 후 다시 시도해주세요.',
                403
            )
            
        if response.status_code == 404:
            return self.create_error_response(
                f'파일을 찾을 수 없습니다: {path}' if path else '요청한 리소스를 찾을 수 없습니다.',
                404
            )
            
        if response.status_code == 401:
            return self.create_error_response(
                '비공개 저장소에 접근하려면 GitHub 토큰이 필요합니다.',
                401
            )
            
        if response.status_code != 200:
            return self.create_error_response(
                f'GitHub API 오류: {response.text}',
                response.status_code
            )
        
        return response.json()

    def extract_repo_info(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        GitHub URL에서 소유자, 저장소 이름, 파일 경로를 추출
        
        Args:
            url (str): GitHub 저장소 URL
            
        Returns:
            Tuple[Optional[str], Optional[str], Optional[str]]: 
                (owner, repo, path) 또는 (None, None, None)
        """
        try:
            # URL 정규화
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
                    path = '/'.join(parts[github_index + 3:]) if len(parts) > github_index + 3 else None
                    return owner, repo, path
        except Exception as e:
            print(f"URL 파싱 중 오류 발생: {e}")
        return None, None, None

    def clone_repo(self):
        """
        GitHub 저장소를 로컬에 클론
        
        Raises:
            Exception: 클론 실패 시 예외 발생
        """
        if not os.path.exists(self.repo_path):
            try:
                git.Repo.clone_from(self.repo_url, self.repo_path)
            except Exception as e:
                print("[DEBUG] GitHub 클론 에러:", e)
                raise

    def get_repo_directory_contents(self, path: str = "") -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        GitHub API를 사용하여 저장소의 디렉토리 내용을 가져옴
        
        Args:
            path (str): 디렉토리 경로 (기본값: 루트 디렉토리)
            
        Returns:
            Union[List[Dict[str, Any]], Dict[str, Any]]: 
                디렉토리 내용 목록 또는 에러 정보
                각 항목은 GitHub API 응답 형식의 파일/디렉토리 정보
        """
        try:
            # API 호출 준비
            url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents/{path}"
            headers = {
                "Accept": "application/vnd.github.v3+json"
            }
            if self.token:
                headers["Authorization"] = f"token {self.token}"
            
            # API 요청 실행
            response = requests.get(url, headers=headers)
            content = self.handle_github_response(response, path)
            
            # 응답 검증
            if isinstance(content, dict) and content.get('error'):
                return content
            if isinstance(content, list):
                return content
            return self.create_error_response("잘못된 응답 형식", 500)
            
        except requests.exceptions.RequestException as e:
            return self.create_error_response(f'API 요청 실패: {str(e)}', 500)
        except Exception as e:
            return self.create_error_response(f'예상치 못한 오류: {str(e)}', 500)
            
    def get_repo_content_as_document(self, path: str) -> Optional[Document]:
        """
        GitHub API를 사용하여 저장소의 파일 내용을 LangChain Document로 가져옴
        
        Args:
            path (str): 파일 경로
        
        Returns:
            Optional[Document]: 
                LangChain Document 객체 또는 None (파일이 없는 경우)
                Document는 파일 내용과 메타데이터를 포함
        """
        try:
            # API 호출 준비
            url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents/{path}"
            headers = {
                "Accept": "application/vnd.github.v3+json"
            }
            if self.token:
                headers["Authorization"] = f"token {self.token}"
            
            # API 요청 실행
            response = requests.get(url, headers=headers)
            content_data = self.handle_github_response(response, path)
            
            # 에러 체크
            if not content_data or isinstance(content_data, dict) and content_data.get('error'):
                return None
            
            # Base64 디코딩
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

    def get_repo_directory_as_documents(self, path: str = "") -> List[Document]:
        """
        GitHub API를 사용하여 저장소의 디렉토리 내용을 LangChain Document 리스트로 가져옴
        
        Args:
            path (str): 디렉토리 경로 (기본값: 루트 디렉토리)
            
        Returns:
            List[Document]: 
                LangChain Document 객체 리스트
                각 Document는 파일의 내용과 메타데이터를 포함
        """
        documents = []
        try:
            # 디렉토리 내용 가져오기
            dir_contents = self.get_repo_directory_contents(path)
            if not dir_contents:
                return documents
                
            # 각 항목 처리
            for item in dir_contents:
                if item['type'] == 'file':
                    # 파일인 경우 Document로 변환
                    doc = self.get_repo_content_as_document(item['path'])
                    if doc:
                        documents.append(doc)
                elif item['type'] == 'dir':
                    # 디렉토리인 경우 재귀적으로 처리
                    sub_docs = self.get_repo_directory_as_documents(item['path'])
                    documents.extend(sub_docs)
                    
            return documents
        except Exception as e:
            print(f"[API] Document 리스트 생성 실패: {str(e)}")
            return documents

    def get_all_repo_contents(self) -> List[Document]:
        """
        GitHub 저장소의 모든 파일과 폴더를 LangChain Document 리스트로 가져옴
        
        Returns:
            List[Document]: 모든 파일의 LangChain Document 객체 리스트
        """
        return self.get_repo_directory_as_documents()

    def get_all_main_files(self, path=""):
        files = []
        dir_contents = self.get_repo_directory_contents(path)
        print(f"[DEBUG] get_all_main_files - path: {path}, dir_contents type: {type(dir_contents)}")
        
        if isinstance(dir_contents, dict) and dir_contents.get('error'):
            print(f"[ERROR] get_all_main_files - API 오류: {dir_contents}")
            return files
            
        if isinstance(dir_contents, list):
            print(f"[DEBUG] get_all_main_files - 디렉토리 항목 수: {len(dir_contents)}")
            for item in dir_contents:
                print(f"[DEBUG] get_all_main_files - 항목: {item.get('name', 'Unknown')}, 타입: {item.get('type', 'Unknown')}")
                if item['type'] == 'file' and any(item['path'].endswith(ext) for ext in MAIN_EXTENSIONS):
                    files.append(item['path'])
                    print(f"[DEBUG] get_all_main_files - 주요 파일 추가: {item['path']}")
                elif item['type'] == 'dir':
                    sub_files = self.get_all_main_files(item['path'])
                    files.extend(sub_files)
                    print(f"[DEBUG] get_all_main_files - 하위 디렉토리에서 {len(sub_files)}개 파일 추가")
        else:
            print(f"[WARNING] get_all_main_files - 예상치 못한 응답 타입: {type(dir_contents)}")
            
        print(f"[DEBUG] get_all_main_files - 최종 파일 수: {len(files)}")
        return files

    def filter_main_files(self):
        self.files = self.get_all_main_files()
        print(f"[DEBUG] 필터링된 주요 파일: {self.files}")
        print(f"[DEBUG] 주요 파일 개수: {len(self.files)}")

    def get_file_contents(self) -> List[Dict[str, Any]]:
        """
        주요 파일의 내용을 읽어 딕셔너리 리스트로 반환
        Returns:
            List[Dict[str, Any]]: 
                파일 경로와 내용을 포함하는 딕셔너리 리스트
                [{'path': '...', 'content': '...', 'file_name': ..., 'file_type': ..., 'sha': ..., 'source_url': ...}, ...]
        """
        file_objs = []
        for path in self.files:
            # 큰 파일 제외 (minified JS, CSS 등)
            if any(pattern in path.lower() for pattern in ['.min.js', '.min.css', 'bootstrap.min', 'jquery.min']):
                print(f"[DEBUG] 큰 파일 제외: {path}")
                continue
                
            doc = self.get_repo_content_as_document(path)
            if doc:
                # 내용 크기 확인
                content_size = len(doc.page_content)
                if content_size > 100000:  # 100KB 이상 파일 제외
                    print(f"[DEBUG] 큰 파일 제외 (크기: {content_size}): {path}")
                    continue
                    
                meta = doc.metadata
                file_objs.append({
                    'path': path,
                    'content': doc.page_content,
                    'file_name': meta.get('file_name'),
                    'file_type': meta.get('file_name', '').split('.')[-1] if meta.get('file_name') else '',
                    'sha': meta.get('sha'),
                    'source_url': meta.get('source'),
                })
        return file_objs

    def generate_directory_structure(self) -> str:
        """
        저장소의 전체 디렉토리/파일 구조를 트리 형태의 텍스트로 반환
        """
        # 디렉토리 내용 재귀적으로 가져오기
        def build_tree(path=""):
            items = self.get_repo_directory_contents(path)
            tree = {}
            if not items or isinstance(items, dict) and items.get('error'):
                return tree
            for item in items:
                if item['type'] == 'file':
                    tree[f"📄 {item['name']}"] = None
                elif item['type'] == 'dir':
                    tree[f"📁 {item['name']}"] = build_tree(item['path'])
            return tree
        
        tree = build_tree()
        lines = []
        def traverse(node, prefix=""):
            for key, value in sorted(node.items()):
                lines.append(f"{prefix}{key}")
                if value is not None:
                    traverse(value, prefix + "  ")
        traverse(tree)
        return "\n".join(lines)

    # ----------------- 토큰 관련 기능 -----------------
    @staticmethod
    def generate_key() -> bytes:
        """
        암호화 키 생성
        
        Returns:
            bytes: 생성된 암호화 키
        """
        if not os.path.exists(KEY_FILE):
            key = Fernet.generate_key()
            with open(KEY_FILE, 'wb') as key_file:
                key_file.write(key)
            return key
        else:
            with open(KEY_FILE, 'rb') as key_file:
                return key_file.read()

    @staticmethod
    def encrypt_token(token: str) -> str:
        """
        토큰 암호화
        
        Args:
            token (str): 암호화할 토큰
            
        Returns:
            str: 암호화된 토큰
        """
        key = GitHubRepositoryFetcher.generate_key()
        f = Fernet(key)
        return f.encrypt(token.encode()).decode()

    @staticmethod
    def decrypt_token(encrypted_token: str) -> str:
        """
        토큰 복호화
        
        Args:
            encrypted_token (str): 복호화할 토큰
            
        Returns:
            str: 복호화된 토큰
        """
        key = GitHubRepositoryFetcher.generate_key()
        f = Fernet(key)
        return f.decrypt(encrypted_token.encode()).decode()

    @staticmethod
    def update_token(token: str) -> bool:
        """
        환경 변수 파일에 GitHub 토큰 업데이트
        
        Args:
            token (str): 업데이트할 토큰
            
        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            # 토큰 암호화
            encrypted_token = GitHubRepositoryFetcher.encrypt_token(token)
            
            # 기존 내용 읽기
            with open(".env", 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # GitHub 토큰 찾아서 교체
            token_found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{GITHUB_TOKEN}="):
                    lines[i] = f"{GITHUB_TOKEN}={encrypted_token}\n"
                    token_found = True
                    break
            
            # 토큰이 없으면 새로 추가
            if not token_found:
                lines.append(f"{GITHUB_TOKEN}={encrypted_token}\n")
            
            # 파일 다시 쓰기
            with open(".env", 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            return True
        except Exception as e:
            print(f"[오류] 토큰 저장 실패: {str(e)}")
            return False

    def load_repo_data(self) -> bool:
        """
        GitHub API를 통해 저장소 데이터를 로드합니다.
        
        Returns:
            bool: 데이터 로드 성공 여부
        """
        try:
            # 이미 필터링된 파일 목록이 있는지 확인
            if self.files:
                print("[DEBUG] 이미 파일 목록이 로드되어 있습니다.")
                return True
                
            # GitHub API를 통한 파일 필터링 및 내용 가져오기
            print("[DEBUG] GitHub API를 통한 파일 필터링 시작")
            self.filter_main_files()
            
            if not self.files:
                print("[WARNING] 필터링된 파일 목록이 없습니다.")
                return False
                
            print(f"[DEBUG] GitHub API 데이터 로드 성공: {len(self.files)} 파일")
            return True
        except Exception as e:
            import traceback
            print(f"[ERROR] GitHub API 데이터 로드 실패: {e}")
            traceback.print_exc()
            return False
            
    def get_directory_structure(self) -> str:
        """
        저장소의 디렉토리 구조를 문자열로 반환합니다.
        
        Returns:
            str: 디렉토리 구조 트리 텍스트
        """
        return self.generate_directory_structure()

class RepositoryEmbedder:
    """
    저장소 내용을 임베딩하는 클래스
    
    이 클래스는 GitHub 저장소의 파일 내용을 청크로 나누고,
    OpenAI API를 사용하여 임베딩한 후 ChromaDB에 저장합니다.
    """
    
    def __init__(self, session_id: str):
        """
        임베더 초기화
        
        Args:
            session_id (str): 세션 ID
        """
        self.session_id = session_id
        collection_name = f"repo_{session_id}"
        
        # 기존 컬렉션이 있으면 삭제 (차원 불일치 문제 해결)
        try:
            existing_collections = chroma_client.list_collections()
            for collection in existing_collections:
                if collection.name == collection_name:
                    print(f"[DEBUG] 기존 컬렉션 삭제: {collection_name}")
                    chroma_client.delete_collection(name=collection_name)
                    break
        except Exception as e:
            print(f"[WARNING] 컬렉션 삭제 중 오류 (무시 가능): {e}")
        
        # 새 컬렉션 생성
        self.collection = chroma_client.create_collection(name=collection_name)

    def process_and_embed(self, files: List[Dict[str, Any]]):
        # 내부 비동기 함수 정의
        async def async_process_and_embed(files):
            import openai
            api_key = os.environ.get("OPENAI_API_KEY")
            client = openai.AsyncClient(api_key=api_key)
            enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
            def safe_meta(meta):
                return {k: ('' if v is None else v if not isinstance(v, (int, float, bool)) else v) for k, v in meta.items()}
            def split_by_tokens(text, max_tokens=256, overlap=64):
                tokens = enc.encode(text)
                chunks = []
                start = 0
                while start < len(tokens):
                    end = min(start + max_tokens, len(tokens))
                    chunk = enc.decode(tokens[start:end])
                    chunks.append((chunk, start, end))
                    if end == len(tokens):
                        break
                    start += max_tokens - overlap
                return chunks
            def chunk_python_functions(source_code):
                try:
                    tree = ast.parse(source_code)
                except Exception as e:
                    print(f"[WARNING] AST 파싱 실패: {e}")
                    return [(source_code, 0, len(enc.encode(source_code)), None, None, 1, len(source_code.splitlines()), None, 0, None)]
                
                lines = source_code.splitlines()
                chunks = []
                imports = []
                parent_map = {}  # 부모-자식 관계 추적
                
                # 부모-자식 관계 맵 구축
                for node in ast.walk(tree):
                    for child in ast.iter_child_nodes(node):
                        parent_map[child] = node
                
                # 임포트 문 수집
                for node in tree.body:
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        start = node.lineno - 1
                        end = getattr(node, 'end_lineno', start + 1)
                        import_text = '\n'.join(lines[start:end])
                        imports.append(import_text)
                
                # 전체 임포트 문자열
                imports_text = '\n'.join(imports)
                
                # 복잡도 계산 함수
                def calculate_complexity(node):
                    """AST 노드의 복잡도 계산"""
                    if isinstance(node, ast.FunctionDef):
                        # 기본 복잡도 + 파라미터 수 + 내부 조건문/반복문 수
                        complexity = 1 + len(node.args.args)
                        for n in ast.walk(node):
                            if isinstance(n, (ast.If, ast.For, ast.While, ast.Try)):
                                complexity += 1
                        return complexity
                    elif isinstance(node, ast.ClassDef):
                        # 기본 복잡도 + 상속 수 + 메소드 수
                        complexity = 1 + len(node.bases)
                        for n in node.body:
                            if isinstance(n, ast.FunctionDef):
                                complexity += 1
                        return complexity
                    return 1
                
                # 계층적 청킹 함수
                def process_node(node, parent_class=None, parent_func=None, depth=0):
                    """노드를 재귀적으로 처리하여 청크 생성"""
                    if not hasattr(node, 'lineno'):
                        return
                    
                    start = node.lineno - 1
                    end = getattr(node, 'end_lineno', None)
                    if end is None:
                        return
                    
                    # 노드 유형에 따른 처리
                    if isinstance(node, ast.ClassDef):
                        class_name = node.name
                        func_name = None
                        
                        # 클래스 docstring 추출
                        docstring = ast.get_docstring(node)
                        
                        # 클래스 전체 코드
                        chunk = '\n'.join(lines[start:end])
                        complexity = calculate_complexity(node)
                        
                        # 부모 클래스 정보 추출
                        parent_classes = []
                        for base in node.bases:
                            if isinstance(base, ast.Name):
                                parent_classes.append(base.id)
                        
                        # 가변 청크 크기 (복잡도에 따라 조정)
                        max_tokens = min(512, 128 + complexity * 32)
                        overlap = min(128, 32 + complexity * 8)
                        
                        # 클래스 전체를 하나의 청크로
                        if len(enc.encode(chunk)) <= max_tokens:
                            chunks.append((
                                chunk, 0, len(enc.encode(chunk)), 
                                func_name, class_name, start+1, end, 
                                parent_class, complexity, ','.join(parent_classes)
                            ))
                        else:
                            # 임포트 + 클래스 정의 + docstring을 첫 청크에 포함
                            class_header = f"{imports_text}\n\n" if imports_text else ""
                            class_def_line = lines[start]
                            if docstring:
                                docstring_lines = docstring.splitlines()
                                class_header += f"{class_def_line}\n    \"\"\"\n    {docstring}\n    \"\"\"\n"
                            else:
                                class_header += f"{class_def_line}\n"
                            
                            chunks.append((
                                class_header, 0, len(enc.encode(class_header)), 
                                func_name, class_name, start+1, start+1+(1 if not docstring else len(docstring.splitlines())+2), 
                                parent_class, complexity, ','.join(parent_classes)
                            ))
                            
                            # 나머지 클래스 본문을 청킹
                            class_body = '\n'.join(lines[start+1:end])
                            for sub_chunk, t_start, t_end in split_by_tokens(class_body, max_tokens=max_tokens, overlap=overlap):
                                chunks.append((
                                    sub_chunk, t_start, t_end, 
                                    func_name, class_name, start+1, end, 
                                    parent_class, complexity, ','.join(parent_classes)
                                ))
                        
                        # 클래스 내부 메소드 처리
                        for child in node.body:
                            process_node(child, class_name, None, depth+1)
                    
                    elif isinstance(node, ast.FunctionDef):
                        func_name = node.name
                        
                        # 함수 docstring 추출
                        docstring = ast.get_docstring(node)
                        
                        # 함수 전체 코드
                        chunk = '\n'.join(lines[start:end])
                        complexity = calculate_complexity(node)
                        
                        # 가변 청크 크기 (복잡도에 따라 조정)
                        max_tokens = min(512, 128 + complexity * 32)
                        overlap = min(128, 32 + complexity * 8)
                        
                        # 함수 전체를 하나의 청크로
                        if len(enc.encode(chunk)) <= max_tokens:
                            chunks.append((
                                chunk, 0, len(enc.encode(chunk)), 
                                func_name, parent_class, start+1, end, 
                                parent_func, complexity, None
                            ))
                        else:
                            # 임포트 + 함수 정의 + docstring을 첫 청크에 포함
                            func_header = f"{imports_text}\n\n" if imports_text and not parent_class else ""
                            func_def_line = lines[start]
                            if docstring:
                                docstring_lines = docstring.splitlines()
                                func_header += f"{func_def_line}\n    \"\"\"\n    {docstring}\n    \"\"\"\n"
                            else:
                                func_header += f"{func_def_line}\n"
                            
                            chunks.append((
                                func_header, 0, len(enc.encode(func_header)), 
                                func_name, parent_class, start+1, start+1+(1 if not docstring else len(docstring.splitlines())+2), 
                                parent_func, complexity, None
                            ))
                            
                            # 나머지 함수 본문을 청킹
                            func_body = '\n'.join(lines[start+1:end])
                            for sub_chunk, t_start, t_end in split_by_tokens(func_body, max_tokens=max_tokens, overlap=overlap):
                                chunks.append((
                                    sub_chunk, t_start, t_end, 
                                    func_name, parent_class, start+1, end, 
                                    parent_func, complexity, None
                                ))
                        
                        # 중첩 함수 처리
                        for child in node.body:
                            process_node(child, parent_class, func_name, depth+1)
                
                # 최상위 노드 처리
                for node in tree.body:
                    process_node(node)
                
                # 청크가 없으면 기본 토큰 기반 청킹 적용
                if not chunks:
                    print(f"[INFO] 구조적 청크 없음, 토큰 기반 청킹 적용")
                    for chunk, t_start, t_end in split_by_tokens(source_code, max_tokens=256, overlap=64):
                        chunks.append((chunk, t_start, t_end, None, None, 1, len(source_code.splitlines()), None, 0, None))
                
                return chunks
            def chunk_markdown(md_text):
                # 마크다운 파싱을 위한 개선된 패턴
                section_pattern = r'(^|\n)(#+\s+.+)($|\n)'  # 헤더
                code_pattern = r'(^|\n)```[\s\S]+?```'  # 코드 블록
                
                # 섹션 제목과 코드 블록 찾기
                sections = re.finditer(section_pattern, md_text, re.MULTILINE)
                code_blocks = re.finditer(code_pattern, md_text, re.MULTILINE)
                
                # 섹션과 코드 블록의 위치 정보 수집
                markers = []
                for section in sections:
                    markers.append((section.start(), section.group(2), 'section'))
                for block in code_blocks:
                    markers.append((block.start(), block.group(0), 'code'))
                
                # 위치 순으로 정렬
                markers.sort(key=lambda x: x[0])
                
                # 의미 단위로 분할
                chunks = []
                last_pos = 0
                for pos, content, marker_type in markers:
                    # 이전 위치부터 현재 마커까지의 텍스트 처리
                    if pos > last_pos:
                        prev_text = md_text[last_pos:pos].strip()
                        if prev_text:
                            if len(enc.encode(prev_text)) > 256:
                                for chunk, t_start, t_end in split_by_tokens(prev_text, max_tokens=256, overlap=64):
                                    chunk_title = "일반 텍스트"
                                    chunks.append((chunk, t_start, t_end, None, chunk_title, None, None, None, 1, None))
                            else:
                                chunk_title = "일반 텍스트"
                                chunks.append((prev_text, 0, len(enc.encode(prev_text)), None, chunk_title, None, None, None, 1, None))
                    
                    # 마커 자체 처리
                    if marker_type == 'section':
                        # 섹션 제목 및 다음 내용 파악
                        section_title = content
                        next_marker_pos = md_text.find('\n#', pos + len(content)) if pos + len(content) < len(md_text) else -1
                        if next_marker_pos == -1:
                            next_marker_pos = len(md_text)
                        
                        section_content = md_text[pos:next_marker_pos].strip()
                        if len(enc.encode(section_content)) > 256:
                            for chunk, t_start, t_end in split_by_tokens(section_content, max_tokens=256, overlap=64):
                                chunks.append((chunk, t_start, t_end, None, section_title, None, None, None, 2, None))
                        else:
                            chunks.append((section_content, 0, len(enc.encode(section_content)), None, section_title, None, None, None, 2, None))
                        
                        last_pos = next_marker_pos
                    elif marker_type == 'code':
                        code_block = content
                        code_lang = re.search(r'```(\w+)', code_block)
                        code_lang = code_lang.group(1) if code_lang else ''
                        
                        if len(enc.encode(code_block)) > 256:
                            for chunk, t_start, t_end in split_by_tokens(code_block, max_tokens=256, overlap=64):
                                chunks.append((chunk, t_start, t_end, code_lang, "코드 블록", None, None, None, 3, None))
                        else:
                            chunks.append((code_block, 0, len(enc.encode(code_block)), code_lang, "코드 블록", None, None, None, 3, None))
                        
                        last_pos = pos + len(code_block)
                
                # 남은 텍스트 처리
                if last_pos < len(md_text):
                    remaining_text = md_text[last_pos:].strip()
                    if remaining_text:
                        if len(enc.encode(remaining_text)) > 256:
                            for chunk, t_start, t_end in split_by_tokens(remaining_text, max_tokens=256, overlap=64):
                                chunks.append((chunk, t_start, t_end, None, "일반 텍스트", None, None, None, 1, None))
                        else:
                            chunks.append((remaining_text, 0, len(enc.encode(remaining_text)), None, "일반 텍스트", None, None, None, 1, None))
                
                # 청크가 없으면 기본 토큰 기반 청킹 적용
                if not chunks:
                    for chunk, t_start, t_end in split_by_tokens(md_text, max_tokens=256, overlap=64):
                        chunks.append((chunk, t_start, t_end, None, "마크다운", None, None, None, 1, None))
                
                return chunks
                
            def chunk_js(source_code):
                """JavaScript 코드를 구조적으로 청킹하는 함수"""
                # 함수/클래스/메소드 정의 패턴
                func_pattern = r'(async\s+)?function\s+(\w+)\s*\([^)]*\)\s*\{'
                arrow_func_pattern = r'(const|let|var)\s+(\w+)\s*=\s*(async\s+)?\([^)]*\)\s*=>'
                class_pattern = r'class\s+(\w+)(\s+extends\s+(\w+))?\s*\{'
                method_pattern = r'(async\s+)?(\w+)\s*\([^)]*\)\s*\{'
                
                lines = source_code.splitlines()
                chunks = []
                
                # 임포트/모듈 문 찾기
                import_lines = []
                for i, line in enumerate(lines):
                    if re.match(r'^\s*(import|require|export)\b', line):
                        import_lines.append(line)
                
                imports_text = '\n'.join(import_lines)
                
                # 정규식 패턴 매칭으로 함수/클래스 찾기
                def find_block_end(start_line, opening_char='{', closing_char='}'):
                    """중괄호 짝을 맞춰 블록 끝 라인 찾기"""
                    balance = 0
                    for i in range(start_line, len(lines)):
                        line = lines[i]
                        balance += line.count(opening_char) - line.count(closing_char)
                        if balance <= 0:
                            return i
                    return len(lines) - 1
                
                # 함수/클래스 찾기
                i = 0
                while i < len(lines):
                    line = lines[i]
                    
                    # 함수 정의 찾기
                    func_match = re.search(func_pattern, line)
                    arrow_match = re.search(arrow_func_pattern, line)
                    class_match = re.search(class_pattern, line)
                    
                    if func_match or arrow_match or class_match:
                        start = i
                        
                        if func_match:
                            name = func_match.group(2)
                            is_class = False
                            parent_class = None
                        elif arrow_match:
                            name = arrow_match.group(2)
                            is_class = False
                            parent_class = None
                        else:  # class_match
                            name = class_match.group(1)
                            is_class = True
                            parent_class = class_match.group(3) if class_match.group(2) else None
                        
                        # 블록 끝 찾기
                        end = find_block_end(start)
                        
                        # 전체 코드 청크
                        chunk = '\n'.join(lines[start:end+1])
                        
                        # 복잡도 추정 (라인 수 + 중첩 레벨)
                        complexity = (end - start) // 5 + chunk.count('{') - chunk.count('}')
                        complexity = max(1, complexity)
                        
                        # 가변 청크 크기
                        max_tokens = min(512, 128 + complexity * 32)
                        overlap = min(128, 32 + complexity * 8)
                        
                        if len(enc.encode(chunk)) <= max_tokens:
                            # 전체 함수/클래스를 하나의 청크로
                            chunks.append((
                                chunk, 
                                0, 
                                len(enc.encode(chunk)), 
                                None if is_class else name, 
                                name if is_class else None, 
                                start+1, 
                                end+1,
                                None,  # parent_func
                                complexity,
                                parent_class if is_class else None
                            ))
                        else:
                            # 헤더 (임포트 + 함수/클래스 선언)
                            header = f"{imports_text}\n\n" if imports_text else ""
                            header += lines[start]
                            
                            chunks.append((
                                header,
                                0,
                                len(enc.encode(header)),
                                None if is_class else name,
                                name if is_class else None,
                                start+1,
                                start+1,
                                None,  # parent_func
                                complexity,
                                parent_class if is_class else None
                            ))
                            
                            # 본문 청킹
                            body = '\n'.join(lines[start+1:end+1])
                            for sub_chunk, t_start, t_end in split_by_tokens(body, max_tokens=max_tokens, overlap=overlap):
                                chunks.append((
                                    sub_chunk,
                                    t_start,
                                    t_end,
                                    None if is_class else name,
                                    name if is_class else None,
                                    start+2,  # 본문 시작
                                    end+1,
                                    None,  # parent_func
                                    complexity,
                                    parent_class if is_class else None
                                ))
                        
                        # 클래스 내부 메소드 찾기 (클래스인 경우)
                        if is_class:
                            method_start = start + 1
                            while method_start < end:
                                method_line = lines[method_start]
                                method_match = re.search(method_pattern, method_line)
                                
                                if method_match:
                                    method_name = method_match.group(2)
                                    method_end = find_block_end(method_start)
                                    
                                    method_chunk = '\n'.join(lines[method_start:method_end+1])
                                    method_complexity = (method_end - method_start) // 3
                                    
                                    # 메소드 청킹
                                    if len(enc.encode(method_chunk)) <= max_tokens // 2:
                                        chunks.append((
                                            method_chunk,
                                            0,
                                            len(enc.encode(method_chunk)),
                                            method_name,
                                            name,  # 클래스명
                                            method_start+1,
                                            method_end+1,
                                            None,
                                            method_complexity,
                                            None
                                        ))
                                    else:
                                        for sub_chunk, t_start, t_end in split_by_tokens(method_chunk, max_tokens=max_tokens//2, overlap=overlap//2):
                                            chunks.append((
                                                sub_chunk,
                                                t_start,
                                                t_end,
                                                method_name,
                                                name,  # 클래스명
                                                method_start+1,
                                                method_end+1,
                                                None,
                                                method_complexity,
                                                None
                                            ))
                                    
                                    method_start = method_end + 1
                                else:
                                    method_start += 1
                        
                        i = end + 1
                    else:
                        i += 1
                
                # 청크가 없으면 기본 토큰 기반 청킹 적용
                if not chunks:
                    for chunk, t_start, t_end in split_by_tokens(source_code, max_tokens=256, overlap=64):
                        chunks.append((chunk, t_start, t_end, None, None, 1, len(source_code.splitlines()), None, 0, None))
                
                return chunks
            def chunk_ipynb(ipynb_text):
                try:
                    nb = nbformat.reads(ipynb_text, as_version=4)
                except Exception as e:
                    print(f"[WARNING] ipynb 파싱 실패: {e}")
                    return [(ipynb_text, 0, len(enc.encode(ipynb_text)), None, "ipynb", 1, len(ipynb_text.splitlines()))]
                chunks = []
                for idx, cell in enumerate(nb.cells):
                    cell_type = cell.get('cell_type', '')
                    source = cell.get('source', '')
                    if not source.strip():
                        continue
                    # 셀 타입별로 태그
                    tag = f"{cell_type} 셀"
                    # 토큰 단위로 분할
                    if len(enc.encode(source)) > 256:
                        for chunk, t_start, t_end in split_by_tokens(source, max_tokens=256, overlap=64):
                            chunks.append((chunk, t_start, t_end, None, tag, idx+1, idx+1))
                    else:
                        chunks.append((source, 0, len(enc.encode(source)), None, tag, idx+1, idx+1))
                if not chunks:
                    chunks.append((ipynb_text, 0, len(enc.encode(ipynb_text)), None, "ipynb", 1, len(ipynb_text.splitlines())))
                return chunks
            # 1. 전체 청크 수집
            all_chunks = []
            for file in files:
                content = file['content']
                path = file['path']
                ext = os.path.splitext(path)[1].lower()
                file_name = file.get('file_name')
                file_type = file.get('file_type')
                sha = file.get('sha')
                source_url = file.get('source_url')
                if ext == '.py':
                    chunks = chunk_python_functions(content)
                elif ext == '.md':
                    chunks = chunk_markdown(content)
                elif ext == '.js':
                    chunks = chunk_js(content)
                elif ext == '.ipynb':
                    chunks = chunk_ipynb(content)
                else:
                    # 오류 수정: 일반 파일은 split_by_tokens로 처리하고 7개 필드 구조에 맞게 조정
                    simple_chunks = split_by_tokens(content, max_tokens=256, overlap=64)
                    chunks = []
                    for chunk_data in simple_chunks:
                        # 처음 3개 값은 유지하고 나머지 4개 필요한 값을 None으로 추가
                        chunk, t_start, t_end = chunk_data  # 여기서 3개 값만 언패킹
                        chunks.append((chunk, t_start, t_end, None, None, 1, len(content.splitlines())))
                
                # 이 부분이 중요: chunks의 모든 항목이 정확히 7개 값을 가지고 있는지 확인
                processed_chunks = []
                for chunk_item in chunks:
                    # 정확히 7개 값을 가지는 튜플로 변환
                    if len(chunk_item) == 7:
                        processed_chunks.append(chunk_item)
                    else:
                        # 7개가 아닌 경우 필요한 만큼 None을 추가하거나 잘라서 7개로 맞춤
                        values = list(chunk_item)[:7]  # 최대 7개까지만 사용
                        while len(values) < 7:
                            values.append(None)  # 7개가 될 때까지 None 추가
                        processed_chunks.append(tuple(values))
                
                # 처리된 chunks 사용
                for i, (chunk, t_start, t_end, func_name, class_name, start_line, end_line) in enumerate(processed_chunks):
                    all_chunks.append((chunk, file, i, t_start, t_end, func_name, class_name, start_line, end_line))
                
                # 파일별 청크 수 요약 로그 (과도한 개별 로그 대신)
                if processed_chunks:
                    print(f"[DEBUG] 파일 청킹 완료: {file.get('path')} - {len(processed_chunks)}개 청크")
            # 2. 비동기 임베딩+역할태깅 함수
            async def embed_and_tag_async(args, client):
                chunk, file, i, t_start, t_end, func_name, class_name, start_line, end_line = args
                
                # 청크 크기 확인 및 분할 (8192 토큰 제한)
                chunk_tokens = len(enc.encode(chunk))
                if chunk_tokens > 8000:  # 안전 마진
                    print(f"[WARNING] 청크가 너무 큼 ({chunk_tokens} 토큰), 분할 처리: {file.get('path')}")
                    # 큰 청크를 작은 청크로 분할
                    sub_chunks = split_by_tokens(chunk, max_tokens=4000, overlap=200)
                    # 첫 번째 서브청크만 사용 (또는 전체를 건너뛸 수 있음)
                    if sub_chunks:
                        chunk = sub_chunks[0][0]  # 첫 번째 서브청크의 텍스트
                    else:
                        # 분할도 실패하면 기본 임베딩 사용
                        embedding = [0.0] * 3072
                        return (embedding, "큰 파일 - 분석 생략", chunk[:1000], file, i, t_start, t_end, func_name, class_name, start_line, end_line)
                
                # 임베딩
                try:
                    emb_resp = await client.embeddings.create(
                        input=chunk,
                        model="text-embedding-3-large"
                    )
                    embedding = emb_resp.data[0].embedding
                except Exception as e:
                    print(f"[WARNING] 임베딩 실패: {e}")
                    # text-embedding-3-large는 3072차원
                    embedding = [0.0] * 3072
                # 역할 태깅
                tag_prompt = f"아래 코드는 어떤 역할(기능/목적)을 하나요? 한글로 간단히 요약해줘.\n\n코드:\n{chunk[:1000]}"  # 역할 태깅도 크기 제한
                try:
                    tag_resp = await client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": tag_prompt}],
                        temperature=0.0,
                        max_tokens=64
                    )
                    role_tag = tag_resp.choices[0].message.content.strip()
                    # 역할 태깅 결과 로그를 요약 형태로 변경 (개별 로그 제거)
                except Exception as e:
                    print(f"[WARNING] 역할 태깅 실패: {e}")
                    role_tag = ''
                return (embedding, role_tag, chunk, file, i, t_start, t_end, func_name, class_name, start_line, end_line)
            # 3. 비동기 병렬 실행 (max_concurrent=20)
            print(f"[DEBUG] 임베딩+역할태깅 asyncio 병렬 처리 시작 (청크 수: {len(all_chunks)})")
            semaphore = asyncio.Semaphore(20)
            async def sem_task(args):
                async with semaphore:
                    return await embed_and_tag_async(args, client)
            tasks = [sem_task(args) for args in all_chunks]
            results = await asyncio.gather(*tasks)
            print(f"[DEBUG] 임베딩+역할태깅 asyncio 병렬 처리 완료")
            # 4. DB 저장 (동기)
            successful_saves = 0
            for embedding, role_tag, chunk, file, i, t_start, t_end, func_name, class_name, start_line, end_line in results:
                file_name = file.get('file_name')
                file_type = file.get('file_type')
                sha = file.get('sha')
                source_url = file.get('source_url')
                path = file['path']
                # 청크 타입 결정 (class, method, function, code)  
                chunk_type = "class" if class_name and not func_name else \
                            "method" if class_name and func_name else \
                            "function" if func_name and not class_name else \
                            "code"
                
                # 복잡도 추정 (청크 크기 기반)
                complexity = 0
                parent_entity = None
                inheritance = None
                
                # 청크 튜플에서 추가 메타데이터 추출 (새 형식인 경우)
                # chunk_data 변수는 이 스코프에 없으므로 사용하지 않음
                # 대신 현재 언패킹된 값들을 사용
                
                metadata = {
                    "path": path or '',
                    "file_name": file_name or '',
                    "file_type": file_type or '',
                    "sha": sha or '',
                    "source_url": source_url or '',
                    "chunk_index": i,
                    "function_name": func_name or '',
                    "class_name": class_name or '',
                    "start_line": start_line if start_line is not None else -1,
                    "end_line": end_line if end_line is not None else -1,
                    "token_start": t_start if t_start is not None else -1,
                    "token_end": t_end if t_end is not None else -1,
                    "role_tag": role_tag,
                    "chunk_type": chunk_type,
                    "complexity": complexity or 1,
                    "parent_entity": parent_entity or '',
                    "inheritance": inheritance or ''
                }
                self.collection.add(
                    ids=[f"{path}_{i}"],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[safe_meta(metadata)]
                )
                # DB 저장 로그를 개별 로그 대신 요약으로 처리
                successful_saves += 1
            
            # 전체 처리 완료 요약 로그
            print(f"[INFO] 임베딩 처리 완료: 총 {successful_saves}개 청크 저장")
        # 동기 함수에서 비동기 실행
        if sys.version_info >= (3, 7):
            asyncio.run(async_process_and_embed(files))
        else:
            raise RuntimeError("Python 3.7 이상에서만 지원됩니다.")
