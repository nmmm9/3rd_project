import requests
import chromadb
import os
import re
import openai
import git

# 주요 파일 확장자
MAIN_EXTENSIONS = ['.py', '.js', '.md']

# 청크 크기
CHUNK_SIZE = 500

# ChromaDB 기본 클라이언트 (로컬)
chroma_client = chromadb.Client()

def parse_github_repo(repo_url):
    """
    https://github.com/user/repo 형태에서 ('user', 'repo') 추출
    """
    m = re.match(r'https?://github.com/([^/]+)/([^/]+)', repo_url)
    if not m:
        raise ValueError('잘못된 GitHub URL')
    return m.group(1), m.group(2)

class GitHubAnalyzer:
    def __init__(self, repo_url, token=None, session_id=None):
        self.repo_url = repo_url
        self.token = token
        self.headers = {'Authorization': f'token {token}'} if token else {}
        self.files = []
        self.owner, self.repo = parse_github_repo(repo_url)
        self.session_id = session_id or f"{self.owner}_{self.repo}"
        self.repo_path = f"./repos/{self.session_id}"

    def clone_repo(self):
        if not os.path.exists(self.repo_path):
            try:
                git.Repo.clone_from(self.repo_url, self.repo_path)
            except Exception as e:
                print("[DEBUG] GitHub 클론 에러:", e)
                raise

    def fetch_file_list(self):
        # GitHub API로 전체 파일 트리 가져오기
        url = f'https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/HEAD?recursive=1'
        try:
            r = requests.get(url, headers=self.headers)
            if r.status_code != 200:
                print(f"[DEBUG] GitHub API 에러: {r.status_code} {r.text}")
                raise Exception(f'GitHub API 오류: {r.status_code} {r.text}')
            data = r.json()
            
            # 전체 트리 데이터 저장
            self.tree_data = data.get('tree', [])
            
            # 파일 경로만 추출 (기존 방식)
            self.all_files = [item['path'] for item in self.tree_data if item['type'] == 'blob']
            
            # 디렉토리 구조 생성
            self.directory_structure = self.build_directory_structure(self.tree_data)
        except Exception as e:
            print("[DEBUG] GitHub API 파일 목록 에러:", e)
            raise
            
    def build_directory_structure(self, tree_data):
        """
        GitHub API에서 가져온 트리 데이터를 계층형 디렉토리 구조로 변환
        """
        root = {'name': self.repo, 'type': 'directory', 'children': {}}
        
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
                current_level[last_part] = {'name': last_part, 'type': 'file', 'path': item['path'], 'size': item.get('size', 0)}
            elif item['type'] == 'tree' and last_part not in current_level:
                current_level[last_part] = {'name': last_part, 'type': 'directory', 'children': {}}
        
        return root
        
    def get_directory_structure_text(self, node=None, prefix='', is_last=True):
        """
        디렉토리 구조를 텍스트로 변환 (트리 형태로 출력)
        """
        if node is None:
            # 최초 호출시 디버그 로그 추가
            print(f"[DEBUG] 디렉토리 구조 텍스트 생성 시작 (repo: {self.repo})")
            node = self.directory_structure
            result = f"{node['name']} (프로젝트 루트)\n"
            prefix = ''
        else:
            connector = '└── ' if is_last else '├── '
            result = f"{prefix}{connector}{node['name']}\n"
            prefix += '    ' if is_last else '│   '
        
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
                # 전체 디렉토리 구조 출력
                print("[DEBUG] 디렉토리 구조 전체:\n" + result)
            else:
                print("[DEBUG] 생성된 디렉토리 구조가 비어있습니다.")
        
        return result

    def fetch_file_content(self, path):
        # 파일 내용 읽기 (raw.githubusercontent.com 사용)
        url = f'https://raw.githubusercontent.com/{self.owner}/{self.repo}/HEAD/{path}'
        try:
            r = requests.get(url, headers=self.headers)
            if r.status_code == 200:
                return r.text
            print(f"[DEBUG] GitHub 파일 내용 에러: {r.status_code} {r.text}")
            return ''
        except Exception as e:
            print("[DEBUG] GitHub 파일 내용 에러:", e)
            return ''

    def filter_main_files(self):
        # 주요 파일만 선별
        self.files = [f for f in self.all_files if any(f.endswith(ext) for ext in MAIN_EXTENSIONS)]

    def chunk_and_embed(self):
        # 주요 파일의 내용을 읽어 self.files를 [{'path': ..., 'content': ...}]로 변환
        file_objs = []
        for path in self.files:
            content = self.fetch_file_content(path)
            file_objs.append({'path': path, 'content': content})
        self.files = file_objs

        # ChromaDB 컬렉션 생성 (session_id 기준)
        collection = chroma_client.get_or_create_collection(name=f"repo_{self.session_id}")
        chunk_id = 0
        api_key = os.environ.get("OPENAI_API_KEY")
        print(f"[DEBUG] 임베딩 직전 OPENAI_API_KEY: {api_key[:8]}...{api_key[-4:]}")
        client = openai.OpenAI(api_key=api_key)
        for file in self.files:
            content = file['content']
            path = file['path']
            # 500자 단위 청크 분할
            for i in range(0, len(content), CHUNK_SIZE):
                chunk = content[i:i+CHUNK_SIZE]
                # OpenAI 임베딩 생성 (최신 방식)
                try:
                    response = client.embeddings.create(
                        input=chunk,
                        model="text-embedding-3-small"
                    )
                    embedding = response.data[0].embedding
                except Exception as e:
                    print("[DEBUG] OpenAI 임베딩 에러:", e)
                    raise
                # ChromaDB에 저장 (메타데이터: 파일경로, 청크 인덱스)
                collection.add(
                    ids=[f"{path}_{i//CHUNK_SIZE}"],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[{"path": path, "chunk_index": i // CHUNK_SIZE}]
                )
                chunk_id += 1

def analyze_repository(repo_url, token=None, session_id=None):
    analyzer = GitHubAnalyzer(repo_url, token, session_id)
    analyzer.clone_repo()
    analyzer.fetch_file_list()
    analyzer.filter_main_files()
    analyzer.chunk_and_embed()
    
    # 디렉토리 구조 텍스트 생성
    directory_structure_text = analyzer.get_directory_structure_text()
    
    # 파일 리스트와 함께 디렉토리 구조 반환
    return {
        'files': analyzer.files,
        'directory_structure': directory_structure_text
    }