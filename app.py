from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, session, flash
import uuid
import time
from github_analyzer import analyze_repository, GitHubRepositoryFetcher
from chat_handler import handle_chat, handle_modify_request, apply_changes
from dotenv import load_dotenv
import os
import sys
import db
import traceback
import json
import openai
from chat_handler import detect_github_push_intent
import requests
import bcrypt  # 비밀번호 해싱을 위한 모듈 추가

load_dotenv()

# GitHub OAuth 설정
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")

# GITHUB_CLIENT_ID와 GITHUB_CLIENT_SECRET이 .env 파일에 있는지 확인
if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
    print("오류: GitHub OAuth Client ID 또는 Secret이 설정되어 있지 않습니다. .env 파일에 GITHUB_CLIENT_ID와 GITHUB_CLIENT_SECRET을 등록하세요.")
    # 실제 운영 환경에서는 여기서 프로그램을 종료하거나 기본값으로 설정하는 등의 처리가 필요할 수 있습니다.
    # 여기서는 경고만 출력하고 진행합니다.
    # sys.exit(1) # 필요에 따라 주석 해제

import openai
openai.api_key = os.environ.get("OPENAI_API_KEY")

key = os.environ.get("OPENAI_API_KEY")
print(f"[DEBUG] OPENAI_API_KEY loaded: {key[:8]}...{key[-4:] if key else ''}")

if not key:
    print("오류: OpenAI API 키가 설정되어 있지 않습니다. .env 파일에 OPENAI_API_KEY를 등록하세요.")
    sys.exit(1)

# 데이터베이스 초기화
db_initialized = db.init_db()
if not db_initialized:
    print("오류: 데이터베이스 초기화에 실패했습니다.")
    sys.exit(1)

# 세션 데이터를 파일에 저장하고 로드하는 함수
def save_sessions(sessions_data):
    try:
        os.makedirs('sessions', exist_ok=True)
        with open('sessions/sessions.json', 'w', encoding='utf-8') as f:
            json.dump(sessions_data, f, ensure_ascii=False, indent=2)
        print(f"[DEBUG] 세션 데이터 저장 완료 (세션 수: {len(sessions_data)})")
    except Exception as e:
        print(f"[DEBUG] 세션 데이터 저장 오류: {e}")

def load_sessions():
    try:
        if os.path.exists('sessions/sessions.json'):
            with open('sessions/sessions.json', 'r', encoding='utf-8') as f:
                sessions_data = json.load(f)
            print(f"[DEBUG] 세션 데이터 로드 완료 (세션 수: {len(sessions_data)})")
            return sessions_data
    except Exception as e:
        print(f"[DEBUG] 세션 데이터 로드 오류: {e}")
    return {}

app = Flask(__name__)
app.secret_key = os.urandom(24) # Flask 세션을 위한 secret_key 설정

sessions = load_sessions()  # session_id: {'repo_url': ..., 'token': ..., 'files': ...}

@app.route('/')
def home():
    # 로그인 상태 확인
    if 'user_id' in session:
        return redirect(url_for('index')) # 로그인 되어 있으면 index로
    return render_template('landing.html') # 아니면 landing 페이지

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('사용자 이름과 비밀번호를 모두 입력해주세요.', 'error')
            return render_template('login.html')
        
        # 사용자 정보 조회
        user = db.get_user_by_username(username)
        
        if not user:
            flash('사용자 이름 또는 비밀번호가 올바르지 않습니다.', 'error')
            return render_template('login.html')
        
        # 비밀번호 검증
        if user.get('is_github_user'):
            # GitHub 사용자인 경우 (비밀번호가 없을 수 있음)
            flash('GitHub 로그인을 이용해주세요.', 'error')
            return render_template('login.html')
        
        if not user.get('password'):
            flash('비밀번호가 설정되지 않은 계정입니다. 관리자에게 문의하세요.', 'error')
            return render_template('login.html')
        
        # 비밀번호 확인
        if not bcrypt.checkpw(password.encode('utf-8'), user.get('password').encode('utf-8')):
            flash('사용자 이름 또는 비밀번호가 올바르지 않습니다.', 'error')
            return render_template('login.html')
        
        # 로그인 성공 처리
        session['user_id'] = user.get('id')
        session['username'] = user.get('username')
        
        # 마지막 로그인 시간 업데이트
        db.update_last_login(user.get('id'))
        
        return redirect(url_for('index'))
    
    # GET 요청 처리
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

# GitHub 로그인 시작
@app.route('/login/github')
def github_login():
    if not GITHUB_CLIENT_ID:
        flash('GitHub Client ID가 설정되지 않았습니다.', 'error')
        return redirect(url_for('login'))
    
    # 사용자를 GitHub 인증 페이지로 리디렉션
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&scope=repo,user"  # 필요한 권한 범위 (예: public_repo, repo, user 등)
    )
    return redirect(github_auth_url)

# GitHub 로그인 콜백 처리
@app.route('/github/callback')
def github_callback():
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        flash('GitHub Client ID 또는 Secret이 설정되지 않았습니다.', 'error')
        return redirect(url_for('login'))

    code = request.args.get('code')
    if not code:
        flash('인증 코드를 받지 못했습니다.', 'error')
        return redirect(url_for('login'))

    # 인증 코드를 사용하여 액세스 토큰 요청
    token_url = "https://github.com/login/oauth/access_token"
    payload = {
        'client_id': GITHUB_CLIENT_ID,
        'client_secret': GITHUB_CLIENT_SECRET,
        'code': code
    }
    headers = {'Accept': 'application/json'}
    token_response = requests.post(token_url, data=payload, headers=headers)
    token_data = token_response.json()

    access_token = token_data.get('access_token')
    if not access_token:
        error_description = token_data.get('error_description', '알 수 없는 오류')
        flash(f'액세스 토큰을 얻는 데 실패했습니다: {error_description}', 'error')
        return redirect(url_for('login'))

    # 액세스 토큰을 사용하여 사용자 정보 가져오기
    user_info_url = "https://api.github.com/user"
    headers = {'Authorization': f'token {access_token}'}
    user_info_response = requests.get(user_info_url, headers=headers)
    user_info = user_info_response.json()

    # GitHub 사용자 정보
    github_id = str(user_info.get('id'))
    github_username = user_info.get('login')
    
    # 이메일 정보 얻기
    # 일부 사용자는 기본 정보에 이메일이 없을 수 있으므로 이메일 API도 호출
    github_email = user_info.get('email')
    if not github_email:
        try:
            emails_url = "https://api.github.com/user/emails"
            emails_response = requests.get(emails_url, headers=headers)
            emails_data = emails_response.json()
            
            # 기본 이메일(primary) 찾기
            for email_info in emails_data:
                if email_info.get('primary'):
                    github_email = email_info.get('email')
                    break
            
            # 기본 이메일이 없으면 첫 번째 이메일 사용
            if not github_email and emails_data:
                github_email = emails_data[0].get('email')
        except Exception as e:
            print(f"[WARNING] GitHub 이메일 정보 조회 실패: {e}")
    
    # 이메일이 여전히 없으면 임의로 생성
    if not github_email:
        github_email = f"{github_username}@github.example.com"
    
    github_avatar_url = user_info.get('avatar_url')
    github_name = user_info.get('name', github_username)  # 이름이 없을 경우 사용자명 사용
    
    # 이미 등록된 GitHub 사용자인지 확인
    user = db.get_user_by_github_id(github_id)
    
    if user:
        # 기존 사용자 - 로그인 처리
        session['user_id'] = user.get('id')
        session['username'] = user.get('username')
        session['is_github_user'] = True
        session['github_token'] = access_token
        
        # GitHub 토큰 업데이트
        db.update_user(user.get('id'), {'github_token': access_token})
        
        # 마지막 로그인 시간 업데이트
        db.update_last_login(user.get('id'))
    else:
        # 새로운 사용자 - 회원가입 처리
        success, result = db.create_user(
            username=github_username,
            email=github_email,
            is_github_user=True,
            github_id=github_id,
            github_username=github_username,
            github_token=access_token,
            github_avatar_url=github_avatar_url
        )
        
        if success:
            user_id = result
            session['user_id'] = user_id
            session['username'] = github_username
            session['is_github_user'] = True
            session['github_token'] = access_token
        else:
            flash(f'GitHub 회원가입 실패: {result}', 'error')
            return redirect(url_for('login'))
    
    # 세션에 GitHub 정보 저장 (기존 코드와의 호환성 유지)
    session['github_token'] = access_token
    session['user_info'] = {
        'login': github_username,
        'id': github_id,
        'avatar_url': github_avatar_url,
        'name': github_name
    }
    
    print(f"[DEBUG] GitHub 로그인 성공: {github_username}")
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        
        # 입력값 검증
        if not all([username, email, password, confirm]):
            flash('모든 필드를 입력해주세요.', 'error')
            return render_template('signup.html', signup_success=False)
        
        if password != confirm:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return render_template('signup.html', signup_success=False)
        
        # 비밀번호 해싱
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # 사용자 생성
        success, result = db.create_user(
            username=username,
            email=email,
            password=hashed_password,
            is_github_user=False
        )
        
        if not success:
            flash(f'회원가입 실패: {result}', 'error')
            return render_template('signup.html', signup_success=False)
        
        # 회원가입 성공 시 성공 페이지 표시
        return render_template('signup.html', signup_success=True)
    
    # GET 요청 처리
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('signup.html', signup_success=False)

@app.route('/index')
def index():
    # 로그인 여부 확인
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    repositories = []
    user_info = session.get('user_info')

    if 'github_token' in session:
        token = session['github_token']
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        # 사용자의 레포지토리 목록 가져오기
        repos_url = 'https://api.github.com/user/repos?type=owner&sort=updated&per_page=10'
        try:
            response = requests.get(repos_url, headers=headers)
            response.raise_for_status()
            repositories = response.json()
            print(f"[DEBUG] Fetched {len(repositories)} repositories for user {user_info.get('login') if user_info else 'Unknown'}")
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to fetch repositories: {e}")
            repositories = []

    return render_template('index.html', repositories=repositories, user_info=user_info)

@app.route('/chat/<session_id>')
def chat(session_id):
    # 로그인 여부 확인
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    
    # 세션 데이터 확인
    from app import sessions as app_sessions
    session_data = app_sessions.get(session_id, {})
    
    if not session_data:
        flash('존재하지 않는 세션입니다.', 'error')
        return redirect(url_for('index'))
    
    # 레포지토리 URL 가져오기
    repo_url = session_data.get('repo_url', '')
    
    # 사용자의 모든 채팅 세션 가져오기
    chat_sessions = db.get_all_chat_sessions(user_id, repo_url)
    
    return render_template('chat.html', session_id=session_id, repo_url=repo_url, chat_sessions=chat_sessions)

@app.route('/new-chat', methods=['POST'])
def new_chat():
    # 로그인 여부 확인
    if 'user_id' not in session:
        return jsonify({'status': '에러', 'error': '로그인이 필요합니다.'}), 401
    
    user_id = session.get('user_id')
    data = request.get_json()
    repo_url = data.get('repo_url')
    token = data.get('token')
    
    if not repo_url:
        return jsonify({'status': '에러', 'error': '레포지토리 URL이 필요합니다.'}), 400
    
    # 새 채팅 세션 생성
    session_id = db.create_new_chat_session(user_id, repo_url, token)
    
    if not session_id:
        return jsonify({'status': '에러', 'error': '새 채팅 생성 실패'}), 500
    
    # 세션 메모리에 기본 데이터 추가
    try:
        # 기존 세션에서 파일 정보 복사
        from app import sessions as app_sessions
        # 같은 레포의 기존 세션 찾기
        existing_sessions = [s_id for s_id, s_data in app_sessions.items() 
                            if s_data.get('repo_url') == repo_url]
        
        # 세션 데이터 초기화
        app_sessions[session_id] = {
            'repo_url': repo_url,
            'token': token
        }
        
        # 기존 세션이 있으면 파일 정보 복사
        if existing_sessions:
            existing_session_id = existing_sessions[0]
            existing_data = app_sessions.get(existing_session_id, {})
            if 'files' in existing_data:
                app_sessions[session_id]['files'] = existing_data['files']
            if 'directory_structure' in existing_data:
                app_sessions[session_id]['directory_structure'] = existing_data['directory_structure']
        
        # 세션 데이터 저장
        save_sessions(app_sessions)
    except Exception as e:
        print(f"[ERROR] 세션 메모리 업데이트 실패: {e}")
    
    return jsonify({'status': '성공', 'session_id': session_id})

@app.route('/chat-sessions', methods=['GET'])
def get_chat_sessions():
    # 로그인 여부 확인
    if 'user_id' not in session:
        return jsonify({'status': '에러', 'error': '로그인이 필요합니다.'}), 401
    
    user_id = session.get('user_id')
    repo_url = request.args.get('repo_url')
    
    if not repo_url:
        return jsonify({'status': '에러', 'error': '레포지토리 URL이 필요합니다.'}), 400
    
    # 채팅 세션 목록 가져오기
    chat_sessions = db.get_all_chat_sessions(user_id, repo_url)
    
    return jsonify({
        'status': '성공',
        'chat_sessions': chat_sessions
    })

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        # 로그인 여부 확인
        if 'user_id' not in session:
            return jsonify({'status': '에러', 'error': '로그인이 필요합니다.'}), 401
        
        user_id = session.get('user_id')
        data = request.get_json()
        repo_url = data.get('repo_url')
        token = data.get('token')
        if not repo_url or not repo_url.startswith('https://github.com/'):
            return jsonify({'status': '에러', 'error': '올바른 GitHub 저장소 URL을 입력하세요.'}), 400
        
        # GitHub 분석 모듈 미리 임포트
        from github_analyzer import analyze_repository, GitHubRepositoryFetcher
        
        # 새 세션 ID 생성 - 처음부터 생성하여 사용
        session_id = str(uuid.uuid4())
        print(f"[DEBUG] 새 세션 ID 생성: {session_id}")
        
        # 이미 분석한 레포지토리인지 확인
        existing_session = db.get_session_by_repo_url(user_id, repo_url)
        if existing_session:
            session_id = existing_session['session_id']
            print(f"[DEBUG] 기존에 분석된 레포지토리를 발견했습니다. 세션 ID: {session_id}")
            # 채팅 기록 가져오기
            chat_history = db.get_chat_history(session_id)
            if chat_history:
                print(f"[DEBUG] 기존 채팅 기록이 {len(chat_history)}건 있습니다.")
            
            # 기존 세션 데이터가 메모리에 없으면 복원
            if session_id not in sessions:
                print(f"[DEBUG] 세션 ID {session_id}의 데이터를 메모리에 복원합니다.")
                # DB에서 조회한 세션 정보로 기본 데이터 설정
                sessions[session_id] = {
                    'repo_url': repo_url,
                    'token': token
                }
                
                # github_analyzer.py 사용하여 파일 정보 복원 (필요시)
                try:
                    # 레포지토리에서 직접 파일 정보 불러오기
                    fetcher = GitHubRepositoryFetcher(repo_url, token, session_id)
                    if fetcher.repo_path and os.path.exists(fetcher.repo_path):
                        print(f"[DEBUG] 기존 저장소 경로 확인: {fetcher.repo_path}")
                        # 기존 데이터 불러오기
                        if fetcher.load_repo_data():
                            sessions[session_id]['files'] = fetcher.files
                            sessions[session_id]['directory_structure'] = fetcher.get_directory_structure()
                            save_sessions(sessions)
                            print(f"[DEBUG] 세션 ID {session_id}의 기존 파일 정보가 복원되었습니다.")
                        else:
                            print(f"[WARNING] 기존 데이터 불러오기 실패, 새로 분석합니다")
                            # 실패시 새로 분석
                            result = analyze_repository(repo_url, token, session_id)
                            if 'files' in result and 'directory_structure' in result:
                                sessions[session_id]['files'] = result['files']
                                sessions[session_id]['directory_structure'] = result['directory_structure']
                                save_sessions(sessions)
                                print(f"[DEBUG] 세션 ID {session_id}의 파일 정보가 재분석되어 복원되었습니다.")
                    else:
                        # 저장소 폴더가 없으면 새로 분석
                        result = analyze_repository(repo_url, token, session_id)
                        if 'files' in result and 'directory_structure' in result:
                            sessions[session_id]['files'] = result['files']
                            sessions[session_id]['directory_structure'] = result['directory_structure']
                            save_sessions(sessions)
                            print(f"[DEBUG] 세션 ID {session_id}의 파일 정보가 새로 분석되어 복원되었습니다.")
                except Exception as e:
                    print(f"[WARNING] 세션 파일 정보 복원 중 오류: {e}")
                    traceback.print_exc()
            
            # 기존 채팅 화면으로 리다이렉트
            return jsonify({
                'status': '분석 완료', 
                'progress': 100,
                'session_id': session_id,
                'message': '이미 분석된 레포지토리입니다. 기존 채팅 화면으로 이동합니다.'
            })
        
        # 분석 진행 상황을 위한 응답 헤더 설정
        def generate_progress():
            # 초기 진행 상태 - 0%
            yield json.dumps({'status': '분석 시작', 'progress': 0, 'session_id': session_id}) + '\n'
            time.sleep(0.5)  # 상태 변경 사이에 약간의 지연 추가
            
            # 저장소 정보 수집 - 5%
            yield json.dumps({'status': '저장소 정보 수집 중...', 'progress': 5, 'session_id': session_id}) + '\n'
            time.sleep(0.5)
            
            try:
                # 저장소 클론 시작 - 10%
                yield json.dumps({'status': '저장소 클론 중...', 'progress': 10, 'session_id': session_id}) + '\n'
                time.sleep(0.5)
                
                # 저장소 클론 진행 - 15%
                yield json.dumps({'status': '저장소 파일 다운로드 중...', 'progress': 15, 'session_id': session_id}) + '\n'
                
                print(f"[DEBUG] analyze_repository 호출 시작 (repo_url: {repo_url}, session_id: {session_id})")
                try:
                    # 저장소 클론 완료 - 20%
                    yield json.dumps({'status': '저장소 클론 완료', 'progress': 20, 'session_id': session_id}) + '\n'
                    time.sleep(0.5)
                    
                    # 파일 구조 분석 - 25%
                    yield json.dumps({'status': '파일 구조 분석 중...', 'progress': 25, 'session_id': session_id}) + '\n'
                    time.sleep(0.5)
                    
                    # 코드 분석 시작 - 30%
                    yield json.dumps({'status': '코드 분석 시작...', 'progress': 30, 'session_id': session_id}) + '\n'
                    
                    result = analyze_repository(repo_url, token, session_id)
                    print(f"[DEBUG] analyze_repository 결과: {list(result.keys())}")
                    
                    # 코드 분석 진행 - 40%
                    yield json.dumps({'status': '코드 청크 생성 중...', 'progress': 40, 'session_id': session_id}) + '\n'
                    time.sleep(0.5)
                    
                    if 'files' not in result or 'directory_structure' not in result:
                        print(f"[ERROR] analyze_repository 결과가 올바르지 않습니다: {result}")
                        raise Exception("analyze_repository가 올바른 결과를 반환하지 않았습니다.")
                    
                    files = result['files']
                    directory_structure = result['directory_structure']
                    
                    # 임베딩 생성 - 50%
                    yield json.dumps({'status': '임베딩 생성 중...', 'progress': 50, 'session_id': session_id}) + '\n'
                    time.sleep(0.5)
                    
                    print(f"[DEBUG] 분석된 파일 수: {len(files)}")
                    print(f"[DEBUG] 디렉토리 구조 길이: {len(directory_structure) if directory_structure else 0}")
                    
                    # 파일 분석 완료 - 60%
                    yield json.dumps({'status': '파일 분석 완료', 'progress': 60, 'session_id': session_id}) + '\n'
                except Exception as e:
                    print(f"[ERROR] analyze_repository 호출 중 오류: {e}")
                    traceback.print_exc()
                    yield json.dumps({'status': '에러', 'error': str(e), 'progress': -1, 'session_id': session_id}) + '\n'
                    raise e
                
                # 디렉토리 구조 정보 로그 추가
                # 디렉토리 구조 생성 - 65%
                yield json.dumps({'status': '디렉토리 구조 생성 중...', 'progress': 65, 'session_id': session_id}) + '\n'
                time.sleep(0.5)
                
                if directory_structure:
                    print(f"[DEBUG] 디렉토리 구조 정보 생성 성공 (길이: {len(directory_structure)} 문자)")
                    # 전체 디렉토리 구조 출력
                    print("[DEBUG] 디렉토리 구조 전체:\n" + directory_structure)
                    
                    # 디렉토리 구조 생성 완료 - 70%
                    yield json.dumps({'status': '디렉토리 구조 생성 완료', 'progress': 70, 'session_id': session_id}) + '\n'
                else:
                    print("[DEBUG] 디렉토리 구조 정보가 생성되지 않았습니다.")
                    yield json.dumps({'status': '디렉토리 구조 생성 실패', 'progress': 70, 'session_id': session_id}) + '\n'
                
                # 세션 데이터 준비 - 75%
                yield json.dumps({'status': '세션 데이터 준비 중...', 'progress': 75, 'session_id': session_id}) + '\n'
                time.sleep(0.5)
                
                # 세션 데이터 저장 - 80%
                yield json.dumps({'status': '세션 데이터 저장 중...', 'progress': 80, 'session_id': session_id}) + '\n'
                
                # 세션 데이터를 메모리와 데이터베이스에 저장
                sessions[session_id] = {
                    'repo_url': repo_url,
                    'token': token,
                    'files': files,
                    'directory_structure': directory_structure
                }
                
                # 세션 데이터를 파일에 저장 (기존 호환성 유지)
                save_sessions(sessions)
                
                # 세션 데이터를 데이터베이스에 저장
                db.create_session(session_id, user_id, repo_url, token)
                
                # 세션 데이터 저장 완료 - 90%
                yield json.dumps({'status': '세션 데이터 저장 완료', 'progress': 90, 'session_id': session_id}) + '\n'
                time.sleep(0.5)
                
                # 최종 처리 - 95%
                yield json.dumps({'status': '최종 처리 중...', 'progress': 95, 'session_id': session_id}) + '\n'
                time.sleep(0.5)
                
                # 분석 완료 - 100%
                yield json.dumps({
                    'status': '분석 완료', 
                    'progress': 100,
                    'session_id': session_id, 
                    'file_count': len(files)
                }) + '\n'
                
            except Exception as e:
                error_msg = str(e)
                print(f"[ERROR] 저장소 분석 중 오류 발생: {error_msg}")
                yield json.dumps({'status': '에러', 'error': error_msg, 'progress': -1, 'session_id': session_id}) + '\n'
        
        return Response(generate_progress(), mimetype='application/x-ndjson')
    except Exception as e:
        print("[분석 알 수 없는 에러]", str(e))
        traceback.print_exc()
        return jsonify({'status': '에러', 'error': f'알 수 없는 오류: {str(e)}'}), 500

@app.route('/chat', methods=['POST'])
def chat_api():
    try:
        # 로그인 여부 확인
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        data = request.get_json()
        session_id = data.get('session_id')
        message = data.get('message')
        if not session_id or not message:
            return jsonify({'error': '세션ID와 질문을 모두 입력하세요.'}), 400
        try:
            import chat_handler
            result = chat_handler.handle_chat(session_id, message)
            return jsonify(result)
        except Exception as e:
            msg = str(e)
            print("[챗봇 에러]", msg)
            traceback.print_exc()
            if 'OPENAI_API_KEY' in msg:
                return jsonify({'error': 'OpenAI API 키가 올바르지 않거나 누락되었습니다.'}), 400
            elif 'context length' in msg:
                return jsonify({'error': '질문 또는 코드가 너무 깁니다. 질문을 더 짧게 입력해 주세요.'}), 400
            else:
                return jsonify({'error': f'챗봇 응답 오류: {msg}'}), 500
    except Exception as e:
        return jsonify({'error': f'서버 오류: {str(e)}'}), 500

@app.route('/get_chat_history', methods=['GET'])
def get_chat_history():
    # 로그인 여부 확인
    if 'user_id' not in session:
        return jsonify({'status': '에러', 'error': '로그인이 필요합니다.'}), 401
    
    session_id = request.args.get('session_id')
    
    if not session_id:
        return jsonify({'status': '에러', 'error': '세션 ID가 필요합니다.'}), 400
    
    # DB에서 채팅 기록 가져오기
    chat_history = db.get_chat_history(session_id)
    
    return jsonify({
        'status': '성공',
        'chat_history': chat_history
    })

@app.route('/modify_request', methods=['POST'])
def modify_request():
    try:
        # 로그인 여부 확인
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        data = request.get_json()
        session_id = data.get('session_id')
        message = data.get('message')
        if not session_id or not message:
            return jsonify({'error': '세션ID와 수정 요청을 모두 입력하세요.'}), 400
        try:
            result = handle_modify_request(session_id, message)
            return jsonify(result)
        except Exception as e:
            msg = str(e)
            print("[코드수정 에러]", msg)
            traceback.print_exc()
            if 'OPENAI_API_KEY' in msg:
                return jsonify({'error': 'OpenAI API 키가 올바르지 않거나 누락되었습니다.'}), 400
            elif 'context length' in msg:
                return jsonify({'error': '수정 요청 또는 코드가 너무 깁니다. 요청을 더 구체적으로 입력해 주세요.'}), 400
            else:
                return jsonify({'error': f'코드 수정 중 오류: {msg}'}), 400
    except Exception as e:
        print("[코드수정 알 수 없는 에러]", str(e))
        traceback.print_exc()
        return jsonify({'error': f'알 수 없는 오류: {str(e)}'}), 500

@app.route('/apply_changes', methods=['POST'])
def apply_changes_api():
    try:
        # 로그인 여부 확인
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        data = request.get_json()
        session_id = data.get('session_id')
        file_name = data.get('file_name')
        new_content = data.get('new_content')
        push_to_github = data.get('push_to_github', False)
        commit_msg = data.get('commit_msg')
        
        if not session_id or not file_name or not new_content:
            return jsonify({'error': '세션ID, 파일명, 코드 내용을 모두 입력하세요.'}), 400
        
        # GitHub 푸시 요청 시 토큰 확인
        if push_to_github and not sessions.get(session_id, {}).get('token'):
            return jsonify({
                'error': 'GitHub 토큰이 없어 원격 저장소에 푸시할 수 없습니다. 시작 화면에서 토큰을 입력해주세요.',
                'code': 'token_required',
                'requires_token': True
            }), 400
        
        try:
            result = apply_changes(session_id, file_name, new_content, push_to_github, commit_msg)
            return jsonify(result)
        except Exception as e:
            msg = str(e)
            print("[코드적용 에러]", msg)
            traceback.print_exc()
            if 'not found' in msg or 'No such file' in msg:
                return jsonify({'error': '해당 파일을 찾을 수 없습니다. 파일명을 다시 확인하세요.'}), 400
            elif 'branch' in msg:
                return jsonify({'error': '브랜치 생성 또는 커밋 중 오류가 발생했습니다.'}), 400
            elif 'remote: Invalid username or password' in msg or 'Authentication failed' in msg:
                return jsonify({
                    'error': 'GitHub 인증에 실패했습니다. 토큰이 유효한지 확인해주세요.',
                    'code': 'authentication_failed'
                }), 400
            else:
                return jsonify({'error': f'코드 적용 중 오류: {msg}'}), 400
    except Exception as e:
        print("[코드적용 알 수 없는 에러]", str(e))
        traceback.print_exc()
        return jsonify({'error': f'알 수 없는 오류: {str(e)}'}), 500

@app.route('/check_push_intent', methods=['POST'])
def check_push_intent():
    """사용자 메시지에서 GitHub 푸시 의도를 감지하는 API"""
    try:
        # 로그인 여부 확인
        if 'user_id' not in session:
            return jsonify({'error': '로그인이 필요합니다.'}), 401
        
        data = request.get_json()
        message = data.get('message', '')
        session_id = data.get('session_id')
        
        if not message or not session_id:
            return jsonify({'error': '메시지와 세션 ID를 모두 입력해주세요.'}), 400
        
        # 푸시 의도 감지
        has_push_intent = detect_github_push_intent(message)
        
        # 토큰 확인
        token_exists = bool(sessions.get(session_id, {}).get('token'))
        
        return jsonify({
            'has_push_intent': has_push_intent,
            'token_exists': token_exists,
            'requires_confirmation': has_push_intent,
            'message': '깃허브에 적용하려면 확인이 필요합니다.' if has_push_intent else ''
        })
    except Exception as e:
        print("[의도감지 에러]", str(e))
        traceback.print_exc()
        return jsonify({'error': f'알 수 없는 오류: {str(e)}'}), 500

@app.route('/push_to_github', methods=['POST'])
def push_to_github():
    try:
        # 로그인 여부 확인
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '로그인이 필요합니다.'}), 401
        
        data = request.get_json()
        session_id = data.get('session_id')
        file_name = data.get('file_name')
        modified_code = data.get('modified_code')
        
        if not all([session_id, file_name, modified_code]):
            return jsonify({'success': False, 'error': '필수 파라미터가 누락되었습니다.'})
        
        # 세션 데이터 확인
        if session_id not in sessions:
            return jsonify({'success': False, 'error': '세션을 찾을 수 없습니다.'})
        
        # 토큰 확인
        if not sessions.get(session_id, {}).get('token'):
            return jsonify({'success': False, 'error': 'GitHub 토큰이 설정되지 않았습니다.'})
        
        # 기본 커밋 메시지
        commit_msg = f'AI 분석기를 통한 {file_name} 업데이트'
        
        # 변경사항 적용 및 GitHub 푸시
        result = apply_changes(session_id, file_name, modified_code, True, commit_msg)
        
        if result.get('success'):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': result.get('error', '알 수 없는 오류가 발생했습니다.')})
    except Exception as e:
        print(f"[ERROR] GitHub 푸시 중 오류: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/apply_local', methods=['POST'])
def apply_local():
    try:
        # 로그인 여부 확인
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '로그인이 필요합니다.'}), 401
        
        data = request.get_json()
        session_id = data.get('session_id')
        file_name = data.get('file_name')
        modified_code = data.get('modified_code')
        
        if not all([session_id, file_name, modified_code]):
            return jsonify({'success': False, 'error': '필수 파라미터가 누락되었습니다.'})
        
        # 세션 데이터 확인
        if session_id not in sessions:
            return jsonify({'success': False, 'error': '세션을 찾을 수 없습니다.'})
        
        # 변경사항 로컬에만 적용
        result = apply_changes(session_id, file_name, modified_code, False, None)
        
        if result.get('success'):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': result.get('error', '알 수 없는 오류가 발생했습니다.')})
    except Exception as e:
        print(f"[ERROR] 로컬 적용 중 오류: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

# 사용자 프로필 페이지
@app.route('/profile')
def profile():
    # 로그인 여부 확인
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    
    # 데이터베이스에서 사용자 정보 조회
    user = None
    conn = db.get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
        finally:
            conn.close()
    
    if not user:
        flash('사용자 정보를 찾을 수 없습니다.', 'error')
        return redirect(url_for('index'))
    
    return render_template('profile.html', user=user)

@app.route('/rename-chat-session', methods=['POST'])
def rename_chat_session():
    """채팅 세션 이름 변경 API"""
    # 로그인 여부 확인
    if 'user_id' not in session:
        return jsonify({'status': '에러', 'error': '로그인이 필요합니다.'}), 401
    
    data = request.get_json()
    session_id = data.get('session_id')
    new_name = data.get('new_name')
    
    if not session_id or not new_name:
        return jsonify({'status': '에러', 'error': '세션 ID와 새 이름이 필요합니다.'}), 400
    
    # 세션 정보 조회
    session_info = db.get_session_by_id(session_id)
    if not session_info:
        return jsonify({'status': '에러', 'error': '해당 세션을 찾을 수 없습니다.'}), 404
    
    # 현재 사용자의 세션인지 확인
    if session_info['user_id'] != session.get('user_id'):
        return jsonify({'status': '에러', 'error': '권한이 없습니다.'}), 403
    
    # 세션 이름 업데이트
    success = db.update_session_name(session_id, new_name)
    if success:
        return jsonify({'status': '성공', 'message': '세션 이름이 변경되었습니다.'})
    else:
        return jsonify({'status': '에러', 'error': '세션 이름 변경 실패'}), 500

@app.route('/reorder-chat-session', methods=['POST'])
def reorder_chat_session():
    """채팅 세션 순서 변경 API"""
    # 로그인 여부 확인
    if 'user_id' not in session:
        return jsonify({'status': '에러', 'error': '로그인이 필요합니다.'}), 401
    
    data = request.get_json()
    session_id = data.get('session_id')
    target_position = data.get('target_position')  # 'up' 또는 'down'
    reference_session_id = data.get('reference_session_id')
    
    if not session_id or not target_position or not reference_session_id:
        return jsonify({'status': '에러', 'error': '필수 파라미터가 누락되었습니다.'}), 400
    
    # 세션 정보 조회
    session_info = db.get_session_by_id(session_id)
    if not session_info:
        return jsonify({'status': '에러', 'error': '해당 세션을 찾을 수 없습니다.'}), 404
    
    # 현재 사용자의 세션인지 확인
    if session_info['user_id'] != session.get('user_id'):
        return jsonify({'status': '에러', 'error': '권한이 없습니다.'}), 403
    
    # 세션 순서 업데이트
    success = db.update_session_order(session_id, reference_session_id, target_position)
    if success:
        return jsonify({'status': '성공', 'message': '세션 순서가 변경되었습니다.'})
    else:
        return jsonify({'status': '에러', 'error': '세션 순서 변경 실패'}), 500

@app.route('/delete-chat-session', methods=['POST'])
def delete_chat_session():
    """채팅 세션 삭제 API"""
    # 로그인 여부 확인
    if 'user_id' not in session:
        return jsonify({'status': '에러', 'error': '로그인이 필요합니다.'}), 401
    
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'status': '에러', 'error': '세션 ID가 필요합니다.'}), 400
    
    # 세션 정보 조회
    session_info = db.get_session_by_id(session_id)
    if not session_info:
        return jsonify({'status': '에러', 'error': '해당 세션을 찾을 수 없습니다.'}), 404
    
    # 현재 사용자의 세션인지 확인
    if session_info['user_id'] != session.get('user_id'):
        return jsonify({'status': '에러', 'error': '권한이 없습니다.'}), 403
    
    # 레포지토리 정보 저장
    repo_url = session_info['repo_url']
    user_id = session.get('user_id')
    
    # 세션 삭제
    success = db.delete_session(session_id)
    if not success:
        return jsonify({'status': '에러', 'error': '세션 삭제 실패'}), 500
    
    # 같은 레포의 다른 세션 찾기
    remaining_sessions = db.get_all_chat_sessions(user_id, repo_url)
    next_session_id = remaining_sessions[0]['session_id'] if remaining_sessions else None
    
    # 세션 데이터에서도 삭제
    if session_id in sessions:
        del sessions[session_id]
    
    return jsonify({
        'status': '성공', 
        'message': '세션이 삭제되었습니다.',
        'next_session_id': next_session_id
    })

if __name__ == '__main__':
    app.run(debug=False) 