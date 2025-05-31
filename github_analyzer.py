"""GitHub 저장소 분석 및 임베딩을 위한 모듈

이 모듈은 GitHub 저장소의 내용을 가져와서 분석하고, 임베딩하여 저장하는 기능을 제공합니다.

주요 클래스:
    - GitHubAnalyzer: GitHub 저장소에서 파일을 가져오고 분석하는 클래스

주요 함수:
    - analyze_repository: GitHub 저장소를 분석하고 임베딩하는 메인 함수
"""

import requests
import chromadb
import os
import re
import openai
import git
from typing import Optional, List, Dict, Any, Tuple
from langchain.schema import Document

# 주요 파일 확장자
MAIN_EXTENSIONS = ['.py', '.js', '.md']

# 청크 크기
CHUNK_SIZE = 500

# ChromaDB 기본 클라이언트 (로컬)
chroma_client = chromadb.Client()

def parse_github_repo(repo_url: str) -> Tuple[str, str]:
    """
    https://github.com/user/repo 형태에서 ('user', 'repo') 추출
    
    Args:
        repo_url (str): GitHub 저장소 URL
        
    Returns:
        Tuple[str, str]: (owner, repo) 튜플
        
    Raises:
        ValueError: 잘못된 GitHub URL 형식인 경우
    """
    m = re.match(r'https?://github.com/([^/]+)/([^/]+)', repo_url)
    if not m:
        raise ValueError('잘못된 GitHub URL')
    return m.group(1), m.group(2)

class GitHubAnalyzer:
    """
    GitHub 저장소에서 파일을 가져오고 분석하는 클래스
    
    이 클래스는 GitHub API를 사용하여 저장소의 파일과 디렉토리를 가져오고,
    디렉토리 구조를 분석하며, 파일 내용을 청크로 나누어 임베딩하는 기능을 제공합니다.
    """
    def __init__(self, repo_url: str, token: Optional[str] = None, session_id: Optional[str] = None):
        """
        GitHub 저장소 분석기 초기화
        
        Args:
            repo_url (str): GitHub 저장소 URL
            token (Optional[str]): GitHub 개인 액세스 토큰
            session_id (Optional[str]): 세션 ID (기본값: owner_repo)
        """
        self.repo_url = repo_url
        self.token = token
        self.headers = {'Authorization': f'token {token}'} if token else {}
        self.files = []
        self.owner, self.repo = parse_github_repo(repo_url)
        self.session_id = session_id or f"{self.owner}_{self.repo}"
        self.repo_path = f"./repos/{self.session_id}"
        self.tree_data = []
        self.all_files = []
        self.directory_structure = {}

    def clone_repo(self) -> None:
        """
        GitHub 저장소를 로컬에 클론
        
        저장소를 로컬 디렉토리에 클론합니다. 이미 클론된 경우 스킵합니다.
        
        Raises:
            Exception: 클론 실패 시 예외 발생
        """
        print(f"[DEBUG] 저장소 클론 시작: {self.repo_url} -> {self.repo_path}")
        
        if not os.path.exists(self.repo_path):
            try:
                git.Repo.clone_from(self.repo_url, self.repo_path)
                print(f"[DEBUG] 저장소 클론 성공: {self.repo_path}")
            except Exception as e:
                print(f"[ERROR] GitHub 클론 에러: {e}")
                raise Exception(f"GitHub 저장소 클론 오류: {e}")
        else:
            print(f"[DEBUG] 이미 클론된 저장소 사용: {self.repo_path}")

    def fetch_file_list(self) -> None:
        """
        GitHub API를 사용하여 저장소의 파일 목록과 디렉토리 구조를 가져옴
        
        GitHub API를 통해 전체 파일 트리를 가져와서 파일 목록과 계층형 디렉토리 구조를 생성합니다.
        
        Raises:
            Exception: GitHub API 요청 실패 또는 데이터 처리 오류 시 발생
        """
        print(f"[DEBUG] GitHub API로 파일 목록 가져오기 시작: {self.owner}/{self.repo}")
        
        # GitHub API로 전체 파일 트리 가져오기
        url = f'https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/HEAD?recursive=1'
        try:
            r = requests.get(url, headers=self.headers)
            if r.status_code != 200:
                print(f"[ERROR] GitHub API 에러: {r.status_code} {r.text}")
                raise Exception(f'GitHub API 오류: {r.status_code} {r.text}')
            data = r.json()
            
            # 전체 트리 데이터 저장
            self.tree_data = data.get('tree', [])
            print(f"[DEBUG] 파일 트리 가져오기 성공: {len(self.tree_data)} 항목")
            
            # 파일 경로만 추출
            self.all_files = [item['path'] for item in self.tree_data if item['type'] == 'blob']
            print(f"[DEBUG] 전체 파일 수: {len(self.all_files)}")
            
            # 디렉토리 구조 생성
            self.directory_structure = self.build_directory_structure(self.tree_data)
            print(f"[DEBUG] 디렉토리 구조 생성 완료")
        except Exception as e:
            print(f"[ERROR] GitHub API 파일 목록 에러: {e}")
            raise Exception(f"GitHub 파일 목록 가져오기 실패: {e}")

            
    def build_directory_structure(self, tree_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        GitHub API에서 가져온 트리 데이터를 계층형 디렉토리 구조로 변환
        
        Args:
            tree_data (List[Dict[str, Any]]): GitHub API에서 가져온 트리 데이터 리스트
            
        Returns:
            Dict[str, Any]: 계층형 디렉토리 구조를 표현하는 중첩 사전
            
        Example:
            {
                'name': 'repo-name',
                'type': 'directory',
                'children': {
                    'src': {
                        'name': 'src',
                        'type': 'directory',
                        'children': {...}
                    },
                    'README.md': {
                        'name': 'README.md',
                        'type': 'file',
                        'path': 'README.md',
                        'size': 5000
                    }
                }
            }
        """
        print(f"[DEBUG] 디렉토리 구조 생성 시작 (항목 수: {len(tree_data)})")
        
        root = {'name': self.repo, 'type': 'directory', 'children': {}}
        
        try:
            # 모든 파일과 디렉토리를 계층 구조로 구성
            for item in tree_data:
                path_parts = item['path'].split('/')
                current_level = root['children']
                
                # 경로의 각 부분을 순회하며 구조 생성
                for i, part in enumerate(path_parts[:-1]):
                    if part not in current_level:
                        current_level[part] = {'name': part, 'type': 'directory', 'children': {}}
                    current_level = current_level[part]['children']
                
                # 마지막 부분 (파일명 또는 디렉토리명)
                last_part = path_parts[-1]
                if item['type'] == 'blob':
                    current_level[last_part] = {
                        'name': last_part, 
                        'type': 'file', 
                        'path': item['path'], 
                        'size': item.get('size', 0)
                    }
                elif item['type'] == 'tree' and last_part not in current_level:
                    current_level[last_part] = {
                        'name': last_part, 
                        'type': 'directory', 
                        'children': {}
                    }
            
            print(f"[DEBUG] 디렉토리 구조 생성 완료")
            return root
            
        except Exception as e:
            print(f"[ERROR] 디렉토리 구조 생성 오류: {e}")
            # 오류 발생 시 기본 구조라도 반환
            return root
        
    def get_directory_structure_text(self, node: Optional[Dict[str, Any]] = None, prefix: str = '', is_last: bool = True) -> str:
        """
        디렉토리 구조를 텍스트로 변환 (트리 형태로 출력)
        
        이 함수는 재귀적으로 디렉토리 구조를 탐색하며 텍스트 트리로 변환합니다.
        
        Args:
            node (Optional[Dict[str, Any]]): 현재 처리할 노드. None이면 루트 노드로 간주
            prefix (str): 현재 라인의 들여쓰기 접두사
            is_last (bool): 현재 노드가 해당 레벨의 마지막 노드인지 여부
            
        Returns:
            str: 트리 형태로 표현된 디렉토리 구조 텍스트
        """
        try:
            if node is None:
                # 최초 호출시 디버그 로그 추가
                print(f"[DEBUG] 디렉토리 구조 텍스트 생성 시작 (repo: {self.repo})")
                node = self.directory_structure
                result = f"{node['name']} (프로젝트 루트)\n"
                prefix = ''
            else:
                connector = '└── ' if is_last else '├── '  # └── or ├──
                result = f"{prefix}{connector}{node['name']}\n"
                prefix += '    ' if is_last else '│   '  # │
            
            if node['type'] == 'directory' and 'children' in node:
                # 자식 노드를 정렬하여 디렉토리가 먼저 오고 파일이 나중에 오도록 함
                dirs = [(k, v) for k, v in node['children'].items() if v['type'] == 'directory']
                files = [(k, v) for k, v in node['children'].items() if v['type'] == 'file']
                
                # 이름 기준으로 정렬
                dirs.sort(key=lambda x: x[0])
                files.sort(key=lambda x: x[0])
                
                # 모든 항목 합치기 (디렉토리 먼저, 그 다음 파일)
                children = dirs + files
                
                for i, (_, child) in enumerate(children):
                    is_last_child = (i == len(children) - 1)
                    result += self.get_directory_structure_text(child, prefix, is_last_child)
            
            # 최종 결과 반환 시 디버그 로그 추가 (최상위 호출에서만)
            if node is self.directory_structure:
                result_length = len(result)
                print(f"[DEBUG] 디렉토리 구조 텍스트 생성 완료 (길이: {result_length} 문자)")
                if result_length > 0:
                    # 전체 디렉토리 구조 출력 (길이가 너무 길면 일부만 출력)
                    if result_length > 500:
                        preview = result[:250] + "\n... (중략) ...\n" + result[-250:]
                        print(f"[DEBUG] 디렉토리 구조 미리보기 (전체 {result_length} 문자):\n{preview}")
                    else:
                        print("[DEBUG] 디렉토리 구조 전체:\n" + result)
                else:
                    print("[DEBUG] 생성된 디렉토리 구조가 비어있습니다.")
            
            return result
            
        except Exception as e:
            print(f"[ERROR] 디렉토리 구조 텍스트 생성 오류: {e}")
            # 오류 발생 시 기본 문자열 반환
            return f"{self.repo} (오류 발생)\n"

    def fetch_file_content(self, path: str) -> str:
        """
        GitHub 저장소에서 파일 내용을 가져옴
        
        Args:
            path (str): 파일 경로
            
        Returns:
            str: 파일 내용 (오류 발생 시 빈 문자열 반환)
        """
        # 파일 내용 읽기 (raw.githubusercontent.com 사용)
        url = f'https://raw.githubusercontent.com/{self.owner}/{self.repo}/HEAD/{path}'
        try:
            print(f"[DEBUG] 파일 내용 가져오기: {path}")
            r = requests.get(url, headers=self.headers)
            if r.status_code == 200:
                content_length = len(r.text)
                print(f"[DEBUG] 파일 내용 가져오기 성공: {path} ({content_length} 문자)")
                return r.text
            print(f"[ERROR] GitHub 파일 내용 에러: {path} - {r.status_code}")
            return ''
        except Exception as e:
            print(f"[ERROR] GitHub 파일 내용 에러: {path} - {e}")
            return ''

    def filter_main_files(self) -> None:
        """
        주요 파일 확장자를 가진 파일만 필터링
        
        MAIN_EXTENSIONS 목록에 있는 확장자를 가진 파일만 선택하여 self.files에 저장합니다.
        """
        self.files = [f for f in self.all_files if any(f.endswith(ext) for ext in MAIN_EXTENSIONS)]
        print(f"[DEBUG] 필터링된 주요 파일 수: {len(self.files)} / {len(self.all_files)}")
        print(f"[DEBUG] 필터링된 파일 확장자: {MAIN_EXTENSIONS}")

    def chunk_and_embed(self) -> None:
        """
        파일 내용을 청크로 분할하고 임베딩하여 ChromaDB에 저장
        
        파일 내용을 가져와서 LangChain Document 객체로 변환한 후,
        청크로 분할하고 OpenAI 임베딩을 생성하여 ChromaDB에 저장합니다.
        
        Raises:
            Exception: 임베딩 생성 시 오류가 발생하면 예외 발생
        """
        print(f"[DEBUG] 파일 청크화 및 임베딩 시작 (파일 수: {len(self.files)})")
        
        # 주요 파일의 내용을 읽어 Document 객체 생성
        documents: List[Document] = []
        file_objs = []
        
        for path in self.files:
            content = self.fetch_file_content(path)
            if content:  # 빈 내용이 아닐 경우만 처리
                file_obj = {'path': path, 'content': content}
                file_objs.append(file_obj)
                
                # LangChain Document 객체 생성
                doc = Document(
                    page_content=content,
                    metadata={
                        "path": path,
                        "source": f"{self.owner}/{self.repo}/{path}",
                        "file_type": os.path.splitext(path)[1][1:] if '.' in path else ""
                    }
                )
                documents.append(doc)
        
        self.files = file_objs
        print(f"[DEBUG] 파일 내용 가져오기 완료 (총 {len(self.files)} 파일)")

        # ChromaDB 콜렉션 생성 (session_id 기준)
        collection_name = f"repo_{self.session_id}"
        try:
            # 기존 콜렉션이 있으면 삭제
            if collection_name in [col.name for col in chroma_client.list_collections()]:
                print(f"[DEBUG] 기존 콜렉션 삭제: {collection_name}")
                chroma_client.delete_collection(collection_name)
            
            collection = chroma_client.get_or_create_collection(name=collection_name)
            print(f"[DEBUG] ChromaDB 콜렉션 생성: {collection_name}")
        except Exception as e:
            print(f"[ERROR] ChromaDB 콜렉션 생성 오류: {e}")
            raise Exception(f"ChromaDB 콜렉션 생성 오류: {e}")
        
        # OpenAI 클라이언트 초기화
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise Exception("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
            
        print(f"[DEBUG] OpenAI API 클라이언트 초기화 (API Key: {api_key[:4]}...{api_key[-4:]})")
        client = openai.OpenAI(api_key=api_key)
        
        # 문서 청크화 및 임베딩
        chunk_count = 0
        embedding_errors = 0
        
        for doc in documents:
            content = doc.page_content
            path = doc.metadata["path"]
            
            # 청크 분할
            chunks = []
            for i in range(0, len(content), CHUNK_SIZE):
                chunk = content[i:i+CHUNK_SIZE]
                chunks.append(chunk)
            
            print(f"[DEBUG] 파일 청크화: {path} ({len(chunks)} 청크)")
            
            # 각 청크 임베딩 및 저장
            for i, chunk in enumerate(chunks):
                chunk_id = f"{path}_{i}"
                try:
                    # OpenAI 임베딩 생성
                    response = client.embeddings.create(
                        input=chunk,
                        model="text-embedding-3-small"
                    )
                    embedding = response.data[0].embedding
                    
                    # ChromaDB에 저장
                    collection.add(
                        ids=[chunk_id],
                        embeddings=[embedding],
                        documents=[chunk],
                        metadatas=[{
                            "path": path, 
                            "chunk_index": i,
                            "source": doc.metadata["source"],
                            "file_type": doc.metadata["file_type"]
                        }]
                    )
                    chunk_count += 1
                    
                except Exception as e:
                    print(f"[ERROR] 임베딩 오류 ({path}, 청크 {i}): {e}")
                    embedding_errors += 1
                    # 개별 청크 오류는 무시하고 계속 진행
        
        print(f"[DEBUG] 임베딩 완료: 총 {chunk_count} 청크 처리, {embedding_errors} 오류 발생")
        
        if embedding_errors > 0 and chunk_count == 0:
            # 모든 임베딩이 실패한 경우
            raise Exception(f"임베딩 실패: 모든 {embedding_errors} 청크의 임베딩이 실패했습니다.")


def analyze_repository(repo_url: str, token: Optional[str] = None, session_id: Optional[str] = None, progress_callback: Optional[callable] = None) -> Dict[str, Any]:
    """
    GitHub 저장소를 분석하고 임베딩하는 메인 함수
    
    Args:
        repo_url (str): GitHub 저장소 URL
        token (Optional[str]): GitHub 개인 액세스 토큰 (선택사항)
        session_id (Optional[str]): 세션 ID (선택사항)
        progress_callback (Optional[callable]): 진행 상황을 보고하기 위한 콜백 함수 (선택사항)
        
    Returns:
        Dict[str, Any]: 분석 결과가 포함된 사전 (파일 목록과 디렉토리 구조 포함)
        
    Raises:
        Exception: 저장소 분석 중 오류 발생 시 예외 발생
    """
    print(f"[INFO] GitHub 저장소 분석 시작: {repo_url}")
    
    # 진행률 보고를 위한 기본 콜백 함수
    if progress_callback is None:
        progress_callback = lambda status, progress, message: print(f"[PROGRESS] {status}: {progress:.1f}% - {message}")
    
    try:
        # 분석기 초기화
        analyzer = GitHubAnalyzer(repo_url, token, session_id)
        progress_callback("initializing", 0, f"분석기 초기화: {repo_url}")
        
        # 저장소 클론
        progress_callback("cloning", 10, f"저장소 클론 중: {repo_url}")
        analyzer.clone_repo()
        
        # 파일 목록 가져오기
        progress_callback("fetching_files", 30, "파일 목록 가져오는 중...")
        analyzer.fetch_file_list()
        
        # 주요 파일 필터링
        progress_callback("filtering_files", 50, "주요 파일 필터링 중...")
        analyzer.filter_main_files()
        
        # 파일 청크화 및 임베딩
        progress_callback("embedding", 60, "파일 내용 임베딩 중...")
        analyzer.chunk_and_embed()
        
        # 디렉토리 구조 텍스트 생성
        progress_callback("generating_structure", 90, "디렉토리 구조 생성 중...")
        directory_structure_text = analyzer.get_directory_structure_text()
        
        # 분석 완료
        progress_callback("completed", 100, "분석 완료!")
        print(f"[INFO] GitHub 저장소 분석 완료: {repo_url}")
        
        # 결과 반환
        return {
            'files': analyzer.files,
            'directory_structure': directory_structure_text,
            'status': 'success'
        }
        
    except Exception as e:
        print(f"[ERROR] 저장소 분석 오류: {e}")
        progress_callback("error", 0, f"오류 발생: {str(e)}")
        
        # 오류 정보 포함하여 반환
        return {
            'files': [],
            'directory_structure': '',
            'status': 'error',
            'error_message': str(e)
        }