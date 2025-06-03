from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
import uuid
import time
from github_analyzer import analyze_repository
from chat_handler import handle_chat, handle_modify_request, apply_changes
from dotenv import load_dotenv
import os
import sys
import db
import traceback
import json
import openai
from chat_handler import detect_github_push_intent

load_dotenv()

import openai
openai.api_key = os.environ.get("OPENAI_API_KEY")

key = os.environ.get("OPENAI_API_KEY")
print(f"[DEBUG] OPENAI_API_KEY loaded: {key[:8]}...{key[-4:] if key else ''}")

if not key:
    print("오류: OpenAI API 키가 설정되어 있지 않습니다. .env 파일에 OPENAI_API_KEY를 등록하세요.")
    sys.exit(1)

db.init_db()

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

sessions = load_sessions()  # session_id: {'repo_url': ..., 'token': ..., 'files': ...}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat/<session_id>')
def chat(session_id):
    return render_template('chat.html', session_id=session_id)

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        repo_url = data.get('repo_url')
        token = data.get('token')
        if not repo_url or not repo_url.startswith('https://github.com/'):
            return jsonify({'status': '에러', 'error': '올바른 GitHub 저장소 URL을 입력하세요.'}), 400
        
        # 새 세션 ID 생성
        session_id = str(uuid.uuid4())
        
        # 분석 진행 상황을 위한 응답 헤더 설정
        def generate_progress():
            # 초기 진행 상태 - 0%
            yield json.dumps({'status': '분석 시작', 'progress': 0}) + '\n'
            time.sleep(0.5)  # 상태 변경 사이에 약간의 지연 추가
            
            # 저장소 정보 수집 - 5%
            yield json.dumps({'status': '저장소 정보 수집 중...', 'progress': 5}) + '\n'
            time.sleep(0.5)
            
            try:
                # 저장소 클론 시작 - 10%
                yield json.dumps({'status': '저장소 클론 중...', 'progress': 10}) + '\n'
                time.sleep(0.5)
                
                # 저장소 클론 진행 - 15%
                yield json.dumps({'status': '저장소 파일 다운로드 중...', 'progress': 15}) + '\n'
                
                print(f"[DEBUG] analyze_repository 호출 시작 (repo_url: {repo_url}, session_id: {session_id})")
                try:
                    # 저장소 클론 완료 - 20%
                    yield json.dumps({'status': '저장소 클론 완료', 'progress': 20}) + '\n'
                    time.sleep(0.5)
                    
                    # 파일 구조 분석 - 25%
                    yield json.dumps({'status': '파일 구조 분석 중...', 'progress': 25}) + '\n'
                    time.sleep(0.5)
                    
                    # 코드 분석 시작 - 30%
                    yield json.dumps({'status': '코드 분석 시작...', 'progress': 30}) + '\n'
                    
                    result = analyze_repository(repo_url, token, session_id)
                    print(f"[DEBUG] analyze_repository 결과: {list(result.keys())}")
                    
                    # 코드 분석 진행 - 40%
                    yield json.dumps({'status': '코드 청크 생성 중...', 'progress': 40}) + '\n'
                    time.sleep(0.5)
                    
                    if 'files' not in result or 'directory_structure' not in result:
                        print(f"[ERROR] analyze_repository 결과가 올바르지 않습니다: {result}")
                        raise Exception("analyze_repository가 올바른 결과를 반환하지 않았습니다.")
                    
                    files = result['files']
                    directory_structure = result['directory_structure']
                    
                    # 임베딩 생성 - 50%
                    yield json.dumps({'status': '임베딩 생성 중...', 'progress': 50}) + '\n'
                    time.sleep(0.5)
                    
                    print(f"[DEBUG] 분석된 파일 수: {len(files)}")
                    print(f"[DEBUG] 디렉토리 구조 길이: {len(directory_structure) if directory_structure else 0}")
                    
                    # 파일 분석 완료 - 60%
                    yield json.dumps({'status': '파일 분석 완료', 'progress': 60}) + '\n'
                except Exception as e:
                    print(f"[ERROR] analyze_repository 호출 중 오류: {e}")
                    traceback.print_exc()
                    raise e
                
                # 디렉토리 구조 정보 로그 추가
                # 디렉토리 구조 생성 - 65%
                yield json.dumps({'status': '디렉토리 구조 생성 중...', 'progress': 65}) + '\n'
                time.sleep(0.5)
                
                if directory_structure:
                    print(f"[DEBUG] 디렉토리 구조 정보 생성 성공 (길이: {len(directory_structure)} 문자)")
                    # 전체 디렉토리 구조 출력
                    print("[DEBUG] 디렉토리 구조 전체:\n" + directory_structure)
                    
                    # 디렉토리 구조 생성 완료 - 70%
                    yield json.dumps({'status': '디렉토리 구조 생성 완료', 'progress': 70}) + '\n'
                else:
                    print("[DEBUG] 디렉토리 구조 정보가 생성되지 않았습니다.")
                    yield json.dumps({'status': '디렉토리 구조 생성 실패', 'progress': 70}) + '\n'
                
                # 세션 데이터 준비 - 75%
                yield json.dumps({'status': '세션 데이터 준비 중...', 'progress': 75}) + '\n'
                time.sleep(0.5)
                
                # 세션 데이터 저장 - 80%
                yield json.dumps({'status': '세션 데이터 저장 중...', 'progress': 80}) + '\n'
                
                # 세션 데이터 저장
                sessions[session_id] = {
                    'repo_url': repo_url,
                    'token': token,
                    'files': files,
                    'directory_structure': directory_structure
                }
                
                # 세션 데이터를 파일에 저장
                save_sessions(sessions)
                
                # 세션 데이터 저장 완료 - 90%
                yield json.dumps({'status': '세션 데이터 저장 완료', 'progress': 90}) + '\n'
                time.sleep(0.5)
                
                # 최종 처리 - 95%
                yield json.dumps({'status': '최종 처리 중...', 'progress': 95}) + '\n'
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
                yield json.dumps({'status': '에러', 'error': error_msg, 'progress': -1}) + '\n'
        
        return Response(generate_progress(), mimetype='application/x-ndjson')
    except Exception as e:
        print("[분석 알 수 없는 에러]", str(e))
        traceback.print_exc()
        return jsonify({'status': '에러', 'error': f'알 수 없는 오류: {str(e)}'}), 500

@app.route('/chat', methods=['POST'])
def chat_api():
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        message = data.get('message')
        if not session_id or not message:
            return jsonify({'error': '세션ID와 질문을 모두 입력하세요.'}), 400
        try:
            result = handle_chat(session_id, message)
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
                return jsonify({'error': f'답변 생성 중 오류: {msg}'}), 400
    except Exception as e:
        print("[챗봇 알 수 없는 에러]", str(e))
        traceback.print_exc()
        return jsonify({'error': f'알 수 없는 오류: {str(e)}'}), 500

@app.route('/modify_request', methods=['POST'])
def modify_request():
    try:
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

if __name__ == '__main__':
    app.run(debug=False) 