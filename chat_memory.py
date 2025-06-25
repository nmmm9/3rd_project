import os
from langchain.memory import ConversationBufferMemory
from dotenv import load_dotenv

load_dotenv()

# 세션별 ConversationBufferMemory 인스턴스를 저장할 딕셔너리
_session_memories = {}

def _get_memory_for_session(session_id: str) -> ConversationBufferMemory:
    """
    주어진 session_id에 대한 ConversationBufferMemory 인스턴스를 가져오거나 생성합니다.
    """
    if session_id not in _session_memories:
        _session_memories[session_id] = ConversationBufferMemory(return_messages=True)
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
        # LangChain의 save_context는 input과 output을 받습니다.
        memory.save_context({"input": question}, {"output": answer})
        print(f"[DEBUG] 대화 저장 완료 (세션 ID: {session_id})")
    except Exception as e:
        print(f"[ERROR] 대화 저장 중 오류 발생: {e}")
        # traceback.print_exc() # 필요시 주석 해제

def get_relevant_conversations(session_id: str, query: str, top_k: int = 3) -> str:
    """
    메모리에서 이전 대화 내용을 가져옵니다.
    ConversationBufferMemory는 모든 대화를 순서대로 저장하므로,
    top_k는 여기서 직접적으로 적용되지 않고, 전체 대화 히스토리를 반환합니다.
    """
    try:
        memory = _get_memory_for_session(session_id)
        # load_memory_variables는 {'history': [...]} 형태의 딕셔너리를 반환
        history_data = memory.load_memory_variables({})
        
        # history_data에서 실제 대화 내용을 문자열로 조합
        # MessagesPlaceholder를 사용하는 프롬프트 템플릿과 호환되도록 구성
        history_str_list = []
        for msg in history_data.get('history', []):
            if hasattr(msg, 'type') and msg.type == 'human':
                history_str_list.append(f"Human: {msg.content}")
            elif hasattr(msg, 'type') and msg.type == 'ai':
                history_str_list.append(f"AI: {msg.content}")
            else:
                history_str_list.append(str(msg)) # 기타 메시지 타입 처리

        # 가장 최근의 대화만 포함하도록 top_k를 적용 (옵션)
        # ConversationBufferMemory는 전체를 저장하므로, 필요에 따라 슬라이싱
        relevant_history = "\n".join(history_str_list[-top_k*2:]) # Q&A 쌍이므로 *2

        if not relevant_history:
            return "이전 대화 없음"
        return relevant_history
    except Exception as e:
        print(f"[ERROR] 관련 대화 검색 중 오류 발생: {e}")
        # traceback.print_exc() # 필요시 주석 해제
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

