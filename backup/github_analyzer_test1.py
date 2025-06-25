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
import traceback

# 주요 파일 확장자
MAIN_EXTENSIONS = ['.py', '.js', '.md']

# 청크 크기
CHUNK_SIZE = 500

# chromadb 클라이언트 초기화
# 기존 chroma_db 디렉토리가 손상되었을 수 있으므로 삭제 후 재생성
import shutil

chroma_client = None

try:
    # 기존 chroma_db 디렉토리 삭제 시도
    if os.path.exists("./chroma_db"):
        print("[DEBUG] 기존 ChromaDB 디렉토리 삭제 시도 중...")
        try:
            shutil.rmtree("./chroma_db")
            print("[DEBUG] 기존 ChromaDB 디렉토리 삭제 성공")
        except Exception as e:
            print(f"[WARNING] 기존 ChromaDB 디렉토리 삭제 실패: {e}")
    
    print("[DEBUG] ChromaDB PersistentClient 초기화 시도 중...")
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    print("[DEBUG] ChromaDB 클라이언트 초기화 성공 (PersistentClient)")
    
    # 테스트: 클라이언트가 제대로 작동하는지 확인
    try:
        collections = chroma_client.list_collections()
        print(f"[DEBUG] ChromaDB 컬렉션 목록 조회 성공: {[col.name for col in collections]}")
    except Exception as e:
        print(f"[ERROR] ChromaDB 컬렉션 목록 조회 실패: {e}")
        # 컬렉션 목록 조회 실패 시 EphemeralClient로 전환
        raise Exception(f"컬렉션 목록 조회 실패: {e}")
        
except Exception as e:
    print(f"[ERROR] ChromaDB PersistentClient 초기화 실패: {e}")
    try:
        print("[DEBUG] ChromaDB EphemeralClient 초기화 시도 중...")
        chroma_client = chromadb.EphemeralClient()
        print("[DEBUG] ChromaDB 클라이언트 초기화 성공 (EphemeralClient)")
        
        # 테스트: EphemeralClient가 제대로 작동하는지 확인
        try:
            collections = chroma_client.list_collections()
            print(f"[DEBUG] ChromaDB EphemeralClient 컬렉션 목록 조회 성공: {[col.name for col in collections]}")
        except Exception as e:
            print(f"[ERROR] ChromaDB EphemeralClient 컬렉션 목록 조회 실패: {e}")
            raise Exception(f"ChromaDB EphemeralClient 컬렉션 목록 조회 실패: {e}")
    except Exception as e:
        print(f"[ERROR] ChromaDB EphemeralClient 초기화 실패: {e}")
        raise Exception(f"ChromaDB 클라이언트 초기화 실패: {e}")

if chroma_client is None:
    raise Exception("ChromaDB 클라이언트가 초기화되지 않았습니다.")

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
            self.directory_structure = self.generate_directory_structure(self.tree_data)
            print(f"[DEBUG] 디렉토리 구조 생성 완료")
        except Exception as e:
            print(f"[ERROR] GitHub API 파일 목록 에러: {e}")
            raise Exception(f"GitHub 파일 목록 가져오기 실패: {e}")

            
    def generate_directory_structure(self, tree_data: List[Dict[str, Any]]) -> str:
        """
        GitHub API의 tree 데이터를 기반으로 디렉토리 구조를 텍스트로 생성
        
        Args:
            tree_data (list): GitHub API에서 반환한 tree 데이터
        
        Returns:
            str: 디렉토리 구조를 표현하는 텍스트
        """
        print(f"[DEBUG] 디렉토리 구조 생성 시작 (트리 데이터 항목 수: {len(tree_data)})")
        
        # 디렉토리 구조를 저장할 딕셔너리
        dir_structure = {}
        
        # 트리 데이터를 순회하며 디렉토리 구조 구성
        for item in tree_data:
            path = item['path']
            item_type = item['type']
            
            # .git 폴더와 숨김 파일 제외
            if path.startswith('.git') or '/.' in path:
                continue
            
            # 경로 분할
            parts = path.split('/')
            current = dir_structure
            
            # 디렉토리 구조 구성
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # 마지막 부분은 파일 또는 디렉토리
                    if item_type == 'blob':
                        current[f"📄 {part}"] = None  # 파일은 None으로 표시
                    else:
                        current[f"📁 {part}"] = {}  # 디렉토리는 빈 딕셔너리로 표시
                else:
                    # 중간 경로는 디렉토리
                    if f"📁 {part}" not in current:
                        current[f"📁 {part}"] = {}
                    current = current[f"📁 {part}"]
        
        # 디렉토리 구조를 텍스트로 변환
        text_structure = []
        
        def traverse(node, prefix=""):
            for key, value in sorted(node.items()):
                text_structure.append(f"{prefix}{key}")
                if value is not None:  # 디렉토리인 경우
                    traverse(value, prefix + "  ")
        
        traverse(dir_structure)
        result = "\n".join(text_structure)
        print(f"[DEBUG] 디렉토리 구조 생성 완료 (길이: {len(result)} 문자)")
        print(f"[DEBUG] 디렉토리 구조 미리보기: {result[:200]}...")
        return result

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
            # 기존 콜렉션 목록 확인
            try:
                collections = chroma_client.list_collections()
                collection_names = [col.name for col in collections]
                print(f"[DEBUG] 현재 ChromaDB 컬렉션 목록: {collection_names}")
            except Exception as e:
                print(f"[ERROR] ChromaDB 컬렉션 목록 조회 실패: {e}")
                collection_names = []
            
            # 기존 콜렉션이 있으면 삭제
            if collection_name in collection_names:
                print(f"[DEBUG] 기존 콜렉션 삭제 시도: {collection_name}")
                try:
                    chroma_client.delete_collection(collection_name)
                    print(f"[DEBUG] 기존 콜렉션 삭제 성공: {collection_name}")
                except Exception as e:
                    print(f"[ERROR] 기존 콜렉션 삭제 실패: {e}")
            
            # 새 콜렉션 생성
            print(f"[DEBUG] ChromaDB 콜렉션 생성 시도: {collection_name}")
            collection = chroma_client.create_collection(
                name=collection_name,
                metadata={"session_id": self.session_id}
            )
            print(f"[DEBUG] ChromaDB 콜렉션 생성 성공: {collection_name}")
            
            # 콜렉션 생성 확인
            try:
                count = collection.count()
                print(f"[DEBUG] 새 콜렉션 문서 수: {count}")
            except Exception as e:
                print(f"[WARNING] 콜렉션 문서 수 조회 실패: {e}")
                
        except Exception as e:
            print(f"[ERROR] ChromaDB 콜렉션 생성 오류: {e}")
            raise Exception(f"ChromaDB 콜렉션 생성 오류: {e}")
        
        # OpenAI 클라이언트 초기화
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("[ERROR] OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
            raise Exception("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
            
        print(f"[DEBUG] OpenAI API 클라이언트 초기화 (API Key: {api_key[:4]}...{api_key[-4:]})") 
        try:
            client = openai.OpenAI(api_key=api_key)
            # 테스트: 클라이언트가 제대로 작동하는지 확인
            test_response = client.embeddings.create(
                input="테스트 임베딩",
                model="text-embedding-3-small"
            )
            print(f"[DEBUG] OpenAI API 클라이언트 초기화 성공 (임베딩 차원: {len(test_response.data[0].embedding)})")
        except Exception as e:
            print(f"[ERROR] OpenAI API 클라이언트 초기화 실패: {e}")
            raise Exception(f"OpenAI API 클라이언트 초기화 실패: {e}")
        
        # 문서 청크화 및 임베딩
        chunk_count = 0
        embedding_errors = 0
        
        # 각 문서를 청크로 분할하고 임베딩
        for doc in documents:
            content = doc.page_content
            path = doc.metadata["path"]
            
            # 청크 분할
            for i in range(0, len(content), CHUNK_SIZE):
                chunk = content[i:i+CHUNK_SIZE]
                chunk_id = f"{path}_{i//CHUNK_SIZE}"
                
                try:
                    print(f"[DEBUG] 임베딩 생성 시도 중 ({path}, 청크 {i//CHUNK_SIZE}, 크기: {len(chunk)} 문자)")
                    # OpenAI 임베딩 생성
                    response = client.embeddings.create(
                        input=chunk,
                        model="text-embedding-3-small"
                    )
                    embedding = response.data[0].embedding
                    print(f"[DEBUG] 임베딩 생성 성공 ({path}, 청크 {i//CHUNK_SIZE}, 차원: {len(embedding)})")
                    
                    # ChromaDB에 저장
                    try:
                        print(f"[DEBUG] ChromaDB에 저장 시도 중 ({path}, 청크 {i//CHUNK_SIZE})")
                        # 임베딩 데이터 검증
                        if not embedding or not isinstance(embedding, list):
                            print(f"[ERROR] 유효하지 않은 임베딩 데이터: {type(embedding)}")
                            raise ValueError("유효하지 않은 임베딩 데이터")
                            
                        # 메타데이터 준비
                        metadata = {
                            "path": path, 
                            "chunk_index": str(i//CHUNK_SIZE),  # 숫자를 문자열로 변환
                            "source": doc.metadata["source"],
                            "file_type": doc.metadata["file_type"]
                        }
                        
                        print(f"[DEBUG] ChromaDB 저장 데이터: id={chunk_id}, 임베딩 차원={len(embedding)}, 문서 길이={len(chunk)}, 메타데이터={metadata}")
                        
                        # ChromaDB에 저장
                        collection.add(
                            ids=[chunk_id],
                            embeddings=[embedding],
                            documents=[chunk],
                            metadatas=[metadata]
                        )
                        
                        print(f"[DEBUG] ChromaDB 저장 성공 ({path}, 청크 {i//CHUNK_SIZE})")
                        chunk_count += 1
                    except Exception as e:
                        print(f"[ERROR] ChromaDB 저장 오류 ({path}, 청크 {i//CHUNK_SIZE}): {e}")
                        print(f"[ERROR] 오류 세부 정보: {type(e).__name__}")
                        traceback.print_exc()
                        embedding_errors += 1
                except Exception as e:
                    print(f"[ERROR] 임베딩 생성 오류 ({path}, 청크 {i//CHUNK_SIZE}): {e}")
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