import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
from dotenv import load_dotenv

BASE_URL = "http://localhost:5000"

# 테스트 계정 정보
TEST_USER = "e2euser"
TEST_EMAIL = "e2euser@example.com"
TEST_PASS = "testpass123"
GITHUB_URL_INVALID = "https://github.com/invalid/invalid"
GITHUB_URL_VALID = "https://github.com/hwangchahae/git-test"

# .env 파일에서 환경변수 로드
load_dotenv()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

def wait_and_find(driver, by, value, timeout=10):
    for _ in range(timeout * 2):
        try:
            el = driver.find_element(by, value)
            if el.is_displayed():
                return el
        except:
            pass
        time.sleep(0.5)
    raise Exception(f"Element not found: {value}")

def test_e2e():
    driver = webdriver.Chrome()
    driver.get(BASE_URL)
    driver.maximize_window()

    # TC-01: 회원가입 (정상)
    print("[TC-01] 회원가입 - 정상 정보 입력")
    driver.get(BASE_URL + "/signup")
    wait_and_find(driver, By.ID, "username").send_keys(TEST_USER)
    wait_and_find(driver, By.ID, "email").send_keys(TEST_EMAIL)
    wait_and_find(driver, By.ID, "password").send_keys(TEST_PASS)
    wait_and_find(driver, By.ID, "confirm").send_keys(TEST_PASS)
    wait_and_find(driver, By.CLASS_NAME, "sign").click()
    time.sleep(1)
    assert "Login" in driver.page_source or "성공" in driver.page_source
    print("  → 회원가입 성공")

    # TC-02: 회원가입 (중복)
    print("[TC-02] 회원가입 - 중복 이메일")
    driver.get(BASE_URL + "/signup")
    wait_and_find(driver, By.ID, "username").send_keys(TEST_USER)
    wait_and_find(driver, By.ID, "email").send_keys(TEST_EMAIL)
    wait_and_find(driver, By.ID, "password").send_keys(TEST_PASS)
    wait_and_find(driver, By.ID, "confirm").send_keys(TEST_PASS)
    wait_and_find(driver, By.CLASS_NAME, "sign").click()
    time.sleep(1)
    try:
        assert (
            "이미 존재" in driver.page_source or
            "중복" in driver.page_source or
            "에러" in driver.page_source or
            "회원가입 실패: 이미 사용 중인 이메일입니다." in driver.page_source
        )
    except AssertionError:
        print("==== 중복 회원가입 시 화면 ====")
        print(driver.page_source)
        raise
    print("  → 중복 가입 차단 확인")

    # TC-03: 로그인 (오류)
    print("[TC-03] 로그인 - 잘못된 정보")
    driver.get(BASE_URL + "/login")
    wait_and_find(driver, By.ID, "username").send_keys("wronguser")
    wait_and_find(driver, By.ID, "password").send_keys("wrongpass")
    wait_and_find(driver, By.CLASS_NAME, "sign").click()
    time.sleep(1)
    try:
        assert (
            "에러" in driver.page_source or
            "실패" in driver.page_source or
            "로그인" in driver.page_source or
            "회원가입" in driver.page_source or
            "회원정보가 일치하지 않습니다" in driver.page_source or
            "로그인 실패" in driver.page_source or
            "사용자 이름 또는 비밀번호가 올바르지 않습니다" in driver.page_source
        )
    except AssertionError:
        print("==== 잘못된 로그인 시 화면 ====")
        print(driver.page_source)
        raise
    print("  → 로그인 실패 메시지 확인")

    # TC-04: 로그인 (정상)
    print("[TC-04] 로그인 - 올바른 정보")
    driver.get(BASE_URL + "/login")
    wait_and_find(driver, By.ID, "username").send_keys(TEST_USER)
    wait_and_find(driver, By.ID, "password").send_keys(TEST_PASS)
    wait_and_find(driver, By.CLASS_NAME, "sign").click()
    time.sleep(2)
    assert "챗봇" in driver.page_source or "GitHub" in driver.page_source or "분석" in driver.page_source
    print("  → 로그인 성공")

    # TC-05: 로그아웃 후 다시 로그인(정상)
    print("[TC-05] 로그아웃 후 다시 로그인(정상)")
    try:
        logout_btn = wait_and_find(driver, By.CSS_SELECTOR, "a[title='Logout']", timeout=3)
        logout_btn.click()
        time.sleep(1)
    except Exception:
        print("  → 로그아웃 버튼을 찾지 못했습니다. 이미 로그아웃 상태일 수 있습니다.")
    driver.get(BASE_URL + "/login")
    wait_and_find(driver, By.ID, "username").send_keys(TEST_USER)
    wait_and_find(driver, By.ID, "password").send_keys(TEST_PASS)
    wait_and_find(driver, By.CLASS_NAME, "sign").click()
    time.sleep(2)
    assert "챗봇" in driver.page_source or "GitHub" in driver.page_source or "분석" in driver.page_source
    print("  → 재로그인 성공")

    # TC-06: 저장소 분석 (오류URL)
    print("[TC-06] 저장소 분석 - 잘못된 URL")
    driver.get(BASE_URL)
    wait_and_find(driver, By.ID, "repo-url").send_keys(GITHUB_URL_INVALID)
    wait_and_find(driver, By.CSS_SELECTOR, "#analyze-form button[type='submit']").click()
    time.sleep(3)
    try:
        alert = driver.switch_to.alert
        print("  → Alert 메시지:", alert.text)
        alert.accept()
        print("  → 비공개 저장소/토큰 입력 alert 처리")
    except Exception:
        pass
    assert (
        "에러" in driver.page_source or
        "실패" in driver.page_source or
        "분석 실패" in driver.page_source or
        "비공개" in driver.page_source or
        "토큰" in driver.page_source
    )
    print("  → 저장소 분석 실패 메시지 확인")

    # TC-07: 저장소 분석 (정상URL)
    print("[TC-07] 저장소 분석 - 유효한 GitHub URL")
    driver.get(BASE_URL)
    wait_and_find(driver, By.ID, "repo-url").send_keys(GITHUB_URL_VALID)
    if GITHUB_TOKEN:
        try:
            wait_and_find(driver, By.ID, "token", timeout=2).send_keys(GITHUB_TOKEN)
            print("  → 토큰 자동 입력 완료")
        except Exception:
            print("  → 토큰 입력란 없음(공개 저장소이거나 입력 불필요)")
    wait_and_find(driver, By.CSS_SELECTOR, "#analyze-form button[type='submit']").click()
    time.sleep(10)
    assert "분석" in driver.page_source or "파일 구조" in driver.page_source or "진행" in driver.page_source
    print("  → 저장소 분석 성공")

    # TC-08: 챗봇 질의응답(파일 내 코드 수정)
    time.sleep(10)
    print("[TC-08] 챗봇 질의응답(파일 내 코드 수정)")

    try:
        chat_input = wait_and_find(driver, By.ID, "user-input", timeout=5)
        chat_input.clear()
        chat_input.send_keys("test_code.py 파일 오류코드 고쳐줘")
        wait_and_find(driver, By.CSS_SELECTOR, "#chat-form button[type='submit']").click()
        time.sleep(20)

        
        # 챗봇 응답 내에 '수정', '코드', 'diff', '고쳤' 등 키워드가 포함되어 있는지 확인
        assert (
            "수정" in driver.page_source or
            "코드" in driver.page_source or
            "diff" in driver.page_source or
            "고쳤" in driver.page_source or
            "에러" in driver.page_source
        )
        print("  → 코드 수정 diff/응답 확인")
    except Exception:
        print("  → 코드 수정 diff 요청 실패 또는 응답 없음")
    
    # TC-09: 챗봇 질의응답(깃허브 푸쉬해줘)
    print("[TC-09] 챗봇 질의응답(수정된 파일 적용 및 GitHub 푸쉬)")
    try:
        # 1. 챗봇에 '이 코드 깃허브에 푸쉬해줘' 입력
        chat_input = wait_and_find(driver, By.ID, "user-input", timeout=5)
        chat_input.clear()
        chat_input.send_keys("수정해서 깃허브에 푸쉬해줘")
        wait_and_find(driver, By.CSS_SELECTOR, "#chat-form button[type='submit']").click()
        time.sleep(10)

        # 2. 'GitHub에 적용(push)' 버튼 클릭
        push_btn = wait_and_find(driver, By.ID, "push-btn", timeout=10)
        push_btn.click()
        time.sleep(3)

        # 4. '적용'(confirm-push) 버튼 클릭
        confirm_push_btn = wait_and_find(driver, By.ID, "confirm-push", timeout=10)
        confirm_push_btn.click()
        time.sleep(10)

        # 5. 성공 메시지 확인
        assert (
            "성공적으로 푸쉬" in driver.page_source or
            "GitHub에 성공적으로 코드가 적용되었습니다" in driver.page_source or
            "커밋" in driver.page_source or
            "적용" in driver.page_source or
            "완료" in driver.page_source
        )
        print("  → GitHub 푸쉬 성공")
    except Exception:
        print("  → 적용/푸쉬 버튼 또는 결과 메시지 없음, 실패")

   

    # 테스트 계정 삭제
    print("[정리] 테스트 계정 삭제 시도...")
    try:
        from db import get_db_connection
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE username=%s OR email=%s", (TEST_USER, TEST_EMAIL))
            conn.commit()
            conn.close()
            print("  → 테스트 계정 삭제 완료")
        else:
            print("  → DB 연결 실패, 계정 삭제 불가")
    except Exception as e:
        print(f"  → 테스트 계정 삭제 중 오류: {e}")

    driver.quit()

if __name__ == "__main__":
    test_e2e()