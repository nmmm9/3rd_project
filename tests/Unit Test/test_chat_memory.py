import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import chat_memory
import inspect

def test_module_import():
    assert chat_memory is not None

def test_save_and_load_conversation():
    session_id = 'unittest_session'
    message = '테스트 메시지'
    answer = '테스트 답변'
    chat_memory.save_conversation(session_id, message, answer)
    result = chat_memory.get_relevant_conversations(session_id, message)
    assert answer in str(result)

def test_load_nonexistent_conversation():
    result = chat_memory.get_relevant_conversations('no_such_session', '아무거나')
    assert result is None or result == [] or result == "" or "이전 대화 없음" in str(result)

@pytest.mark.parametrize("session_id,message", [
    ("", ""),  # 빈 세션/메시지
    (None, None),  # None 입력
    ("unittest_session", ""),  # 메시지 없음
    ("", "메시지만"),  # 세션 없음
])
def test_save_conversation_edge_cases(session_id, message):
    try:
        chat_memory.save_conversation(session_id, message, "dummy_answer")
    except Exception:
        pytest.fail("save_conversation에서 예외 발생")

def test_all_functions():
    for name, func in inspect.getmembers(chat_memory, inspect.isfunction):
        sig = inspect.signature(func)
        params = sig.parameters
        if len(params) == 0:
            try:
                func()
            except Exception as e:
                pytest.fail(f"{name}() 함수에서 예외 발생: {e}")
        else:
            # 인자가 필요한 함수도 임시 값으로 호출 시도
            args = []
            for p in params.values():
                if p.default is not inspect.Parameter.empty:
                    args.append(p.default)
                elif p.annotation == str:
                    args.append("test")
                else:
                    args.append(None)
            try:
                func(*args)
            except Exception:
                pass  # 예외 발생도 허용(테스트 목적)
