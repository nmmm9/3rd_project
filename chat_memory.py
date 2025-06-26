import os
from dotenv import load_dotenv

load_dotenv()

# 세션별 대화 기록을 저장할 딕셔너리
_session_memories = {}

def _get_memory_for_session(session_id: str) -> list:
    """
    주어진 session_id에 대한 대화 기록 리스트를 가져오거나 생성합니다.
    """
    if session_id not in _session_memories:
        _session_memories[session_id] = []
        print(f"[DEBUG] 새 메모리 인스턴스 생성: {session_id}")
    else:
        print(f"[DEBUG] 기존 메모리 인스턴스 사용: {session_id}")
    return _session_memories[session_id]

def save_conversation(session_id: str, question: str, answer: str):
    """
    대화 내용을 메모리에 저장합니다.
    """
    try:
        memory = _get_memory_for_session(session_id)
        # 대화 쌍을 메모리에 저장
        conversation = {
            "question": question,
            "answer": answer,
            "timestamp": os.environ.get("TZ", "UTC")
        }
        memory.append(conversation)
        
        # 메모리 크기 제한 (최대 50개 대화 유지)
        if len(memory) > 50:
            memory.pop(0)  # 가장 오래된 대화 제거
            
        print(f"[DEBUG] 대화 저장 완료 (세션 ID: {session_id}, 총 대화 수: {len(memory)})")
    except Exception as e:
        print(f"[ERROR] 대화 저장 중 오류 발생: {e}")

def get_relevant_conversations(session_id: str, query: str, top_k: int = 3) -> str:
    """
    메모리에서 이전 대화 내용을 가져옵니다.
    최근 대화를 우선으로 top_k 개의 대화를 반환합니다.
    """
    try:
        memory = _get_memory_for_session(session_id)
        
        if not memory:
            return "이전 대화 없음"
        
        # 최근 대화를 우선으로 top_k 개 선택
        recent_conversations = memory[-top_k:] if len(memory) >= top_k else memory
        
        # 대화 내용을 문자열로 조합
        history_str_list = []
        for conv in recent_conversations:
            question = conv.get("question", "")
            answer = conv.get("answer", "")
            
            if question and answer:
                history_str_list.append(f"사용자: {question}")
                history_str_list.append(f"AI: {answer}")
        
        if not history_str_list:
            return "이전 대화 없음"
            
        return "\n".join(history_str_list)
        
    except Exception as e:
        print(f"[ERROR] 관련 대화 검색 중 오류 발생: {e}")
        return "이전 대화 없음"

def reset_memory(session_id=None):
    """
    특정 세션의 대화 기록 또는 모든 대화 기록을 초기화합니다.
    """
    if session_id:
        if session_id in _session_memories:
            del _session_memories[session_id]
            print(f"[DEBUG] 메모리 초기화 완료: {session_id}")
        else:
            print(f"[DEBUG] 초기화할 메모리 없음: {session_id}")
    else:
        _session_memories.clear()
        print("[DEBUG] 모든 메모리 초기화 완료")

def get_memory_stats(session_id: str) -> dict:
    """
    세션의 메모리 통계를 반환합니다.
    """
    try:
        memory = _session_memories.get(session_id, [])
        return {
            "session_id": session_id,
            "conversation_count": len(memory),
            "memory_exists": session_id in _session_memories
        }
    except Exception as e:
        print(f"[ERROR] 메모리 통계 조회 중 오류 발생: {e}")
        return {
            "session_id": session_id,
            "conversation_count": 0,
            "memory_exists": False,
            "error": str(e)
        }