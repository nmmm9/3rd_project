# git_modifier.py
import git
import os
import base64
import urllib.parse

def check_branch_exists(repo, branch_name):
    """지정된 브랜치가 존재하는지 확인"""
    try:
        return branch_name in [ref.name for ref in repo.refs if 'origin/' + branch_name not in ref.name] or branch_name in [ref.name.replace('origin/', '') for ref in repo.refs if 'origin/' in ref.name]
    except Exception as e:
        print(f"[ERROR] 브랜치 확인 중 오류: {e}")
        return False

def checkout_branch(repo, branch_name, base_branch='main'):
    """브랜치 체크아웃 (없으면 생성)"""
    try:
        if check_branch_exists(repo, branch_name):
            print(f"[INFO] 기존 브랜치 {branch_name} 체크아웃")
            repo.git.checkout(branch_name)
        else:
            print(f"[INFO] 새 브랜치 {branch_name} 생성 (base: {base_branch})")
            # base_branch가 존재하는지 확인
            if not check_branch_exists(repo, base_branch) and not f"origin/{base_branch}" in [ref.name for ref in repo.refs]:
                base_branch = 'master'  # 기본값으로 폴백
                if not check_branch_exists(repo, base_branch) and not f"origin/{base_branch}" in [ref.name for ref in repo.refs]:
                    raise Exception(f"기본 브랜치({base_branch})를 찾을 수 없습니다.")
            
            # 현재 브랜치 저장
            current_branch = repo.active_branch.name
            
            # base_branch로 체크아웃
            if check_branch_exists(repo, base_branch):
                repo.git.checkout(base_branch)
            else:
                repo.git.checkout(f"origin/{base_branch}")
            
            # 새 브랜치 생성 및 체크아웃
            new_branch = repo.create_head(branch_name)
            repo.head.reference = new_branch
            repo.head.reset(index=True, working_tree=True)
        return True
    except Exception as e:
        print(f"[ERROR] 브랜치 체크아웃 중 오류: {e}")
        raise

def push_to_github(repo, branch_name, token=None):
    """GitHub에 변경사항 푸시 (토큰 필요)"""
    if not token:
        print("[WARNING] GitHub 토큰이 제공되지 않아 푸시를 건너뜁니다.")
        return False
    
    try:
        # 원격 저장소 URL에 토큰 추가
        origin = repo.remote(name='origin')
        old_url = list(origin.urls)[0]
        
        # URL에 토큰 삽입
        url_parts = old_url.split('://')
        if len(url_parts) > 1 and 'github.com' in url_parts[1]:
            if '@' in url_parts[1]:  # 이미 사용자 정보가 있는 경우
                print("[INFO] URL에 이미 인증 정보가 있어 교체합니다.")
                user_repo = url_parts[1].split('@')[1]
                new_url = f"{url_parts[0]}://{token}@{user_repo}"
            else:  # 사용자 정보가 없는 경우
                new_url = f"{url_parts[0]}://{token}@{url_parts[1]}"
            
            # 일시적으로 URL 변경
            origin.set_url(new_url)
            
            try:
                # 푸시 실행
                print(f"[INFO] GitHub에 {branch_name} 브랜치 푸시 시작")
                push_info = origin.push(branch_name)
                print(f"[INFO] 푸시 결과: {push_info[0].summary}")
                
                # URL 복원
                origin.set_url(old_url)
                
                return True
            except Exception as e:
                # 에러 발생 시에도 URL 복원
                origin.set_url(old_url)
                raise e
        else:
            raise Exception("원격 저장소 URL 형식이 올바르지 않습니다.")
    except Exception as e:
        print(f"[ERROR] GitHub 푸시 중 오류: {e}")
        raise

def create_branch_and_commit(repo_path, branch_name, file_path, new_content, commit_msg, token=None):
    """파일 수정, 커밋, 선택적 푸시를 수행"""
    try:
        repo = git.Repo(repo_path)
        
        # 1. 브랜치 체크아웃 (없으면 생성)
        checkout_branch(repo, branch_name)
        
        # 2. 파일 수정
        abs_path = os.path.join(repo_path, file_path)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        repo.index.add([file_path])
        
        # 3. 커밋
        repo.index.commit(commit_msg)
        
        # 4. 토큰이 제공된 경우 푸시
        push_result = False
        if token:
            push_result = push_to_github(repo, branch_name, token)
        
        return {
            'success': True,
            'pushed': push_result,
            'branch': branch_name,
            'file': file_path
        }
    except Exception as e:
        print(f"[ERROR] 파일 수정 및 커밋 중 오류: {e}")
        raise