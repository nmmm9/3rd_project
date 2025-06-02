"""
대화 기록 관리 모듈.
이전 대화를 저장하고 검색하는 기능을 제공합니다.
"""

import chromadb
from chromadb.utils import embedding_functions
import os
import hashlib
import time
from datetime import datetime
import traceback
import openai

# ChromaDB를 위한 디렉토리
MEMORY_DB_PATH = "./chat_memory_db"

# 해시 생성 함수
def compute_hash(text: str) -> str:
    """입력 텍스트의 해시값을 생성합니다."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

# ChromaDB 클라이언트 초기화
def init_memory_client():
    """ChromaDB 클라이언트를 초기화합니다."""
    try:
        os.makedirs(MEMORY_DB_PATH, exist_ok=True)
        client = chromadb.PersistentClient(path=MEMORY_DB_PATH)
        print(f"[DEBUG] 대화 기록 DB 클라이언트 초기화 완료: {MEMORY_DB_PATH}")
        return client
    except Exception as e:
        print(f"[ERROR] 대화 기록 DB 클라이언트 초기화 실패: {e}")
        traceback.print_exc()
        return None

# OpenAI 임베딩 함수 생성
openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name="text-embedding-3-small"
)

# 메모리 클라이언트 초기화
memory_client = init_memory_client()

def init_memory_collection(session_id):
    """세션별 대화 기록 컬렉션을 초기화합니다."""
    if not memory_client:
        print("[ERROR] 메모리 클라이언트가 초기화되지 않았습니다.")
        return None
    
    collection_name = f"memory_{session_id}"
    try:
        # 컬렉션 존재 여부 확인
        collections = [col.name for col in memory_client.list_collections()]
        
        if collection_name not in collections:
            collection = memory_client.create_collection(
                name=collection_name,
                embedding_function=openai_ef,
                metadata={"description": f"대화 기록 - 세션 {session_id}"}
            )
        else:
            collection = memory_client.get_collection(
                name=collection_name,
                embedding_function=openai_ef
            )
        
        print(f"[DEBUG] 대화 기록 컬렉션 초기화 완료: {collection_name}")
        return collection
    except Exception as e:
        print(f"[ERROR] 대화 기록 컬렉션 초기화 실패: {e}")
        traceback.print_exc()
        return None

def save_conversation(session_id: str, query: str, answer: str, similarity_threshold: float = 0.91) -> None:
    """
    세션별 대화 내용을 저장합니다. 유사한 질문이 있으면 중복 제거합니다.
    """
    print(f"[CHAT_MEMORY] 대화 저장 시작 - 세션: {session_id}")
    print(f"[CHAT_MEMORY] 질문: {query[:100]}{'...' if len(query) > 100 else ''}")
    print(f"[CHAT_MEMORY] 답변: {answer[:100]}{'...' if len(answer) > 100 else ''}")
    
    # 세션별 컬렉션 초기화
    memory_collection = init_memory_collection(session_id)
    
    # 질문 해시 생성
    query_hash = compute_hash(query)
    print(f"[CHAT_MEMORY] 생성된 질문 해시: {query_hash}")
    
    deleted_similar = False
    try:
        # 유사한 질문이 있는지 확인하고 중복 제거
        print(f"[CHAT_MEMORY] 유사 질문 검색 시작 (threshold: {similarity_threshold})")
        collection = init_memory_collection(session_id)
        results = collection.query(
            query_texts=[query],
            n_results=5
        )
        
        if results and 'ids' in results and len(results['ids']) > 0 and len(results['ids'][0]) > 0:
            for idx, item_id in enumerate(results['ids'][0]):
                # 거리를 유사도로 변환 (1 - 거리)
                distance = results['distances'][0][idx] if 'distances' in results and len(results['distances']) > 0 else 1.0
                similarity = 1 - distance
                
                if similarity > similarity_threshold:
                    print(f"[CHAT_MEMORY] 유사 질문 발견 (유사도: {similarity:.4f}), 삭제: {item_id}")
                    collection.delete(ids=[item_id])
                    deleted_similar = True
    except Exception as e:
        print(f"[CHAT_MEMORY] 유사 질문 검색 중 오류 발생: {e}")
    
    if not deleted_similar:
        print(f"[CHAT_MEMORY] 유사한 기존 질문이 없어 중복 제거 없이 저장합니다.")
    
    # 새 대화 저장
    try:
        conversation_text = f"Q: {query}\nA: {answer}"
        timestamp = datetime.now().isoformat()
        collection.add(
            documents=[conversation_text],
            metadatas=[{
                "session_id": session_id,
                "timestamp": timestamp,
                "question_hash": query_hash,
                "type": "conversation"
            }],
            ids=[query_hash]
        )
        print(f"[DEBUG] 대화 저장 완료: {query_hash[:8]}")
        return True
    except Exception as e:
        print(f"[ERROR] 대화 저장 실패: {e}")
        traceback.print_exc()
        return False

def get_relevant_conversations(session_id: str, query: str, top_k: int = 3) -> str:
    """
    현재 질문과 관련된 이전 대화를 가져옵니다.
    """
    print(f"[CHAT_MEMORY] 관련 대화 검색 시작 - 세션: {session_id}")
    print(f"[CHAT_MEMORY] 현재 질문: {query[:100]}{'...' if len(query) > 100 else ''}")
    
    # 세션별 컬렉션 초기화
    memory_collection = init_memory_collection(session_id)
    
    try:
        # 컬렉션 상태 확인
        try:
            doc_count = memory_collection._collection.count()
            print(f"[CHAT_MEMORY] 컬렉션 '{session_id}' 내 총 문서 수: {doc_count}")
            if doc_count == 0:
                print(f"[CHAT_MEMORY] 컬렉션이 비어 있어 관련 대화가 없습니다.")
                return "이전 대화 없음"
        except Exception as e:
            print(f"[CHAT_MEMORY] 컬렉션 문서 수 확인 중 오류: {e}")
        
        # 질문 임베딩 생성
        query_vector = embedding_model.embed_query(query)
        print(f"[CHAT_MEMORY] 질문 임베딩 생성 완료 (차원: {len(query_vector)})")

        
        # 질문과 관련된 이전 대화 검색
        print(f"[CHAT_MEMORY] 유사 대화 검색 시작 (top_k={top_k})")
        results = memory_collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        if results and 'documents' in results and len(results['documents']) > 0 and len(results['documents'][0]) > 0:
            conversations = results['documents'][0]
            print(f"[CHAT_MEMORY] 검색된 관련 대화 수: {len(conversations)}")
            
            # 관련 대화 형식화
            formatted_conversations = []
            for i, doc in enumerate(conversations):
                # 개행 문자를 처리하기 위해 변수로 선출해서 사용
                newline = "\n"
                doc_parts = doc.split(f"A: ")
                if len(doc_parts) > 0:
                    q_text = doc_parts[0].replace("Q: ", "")
                    q_preview = q_text[:50] + ('...' if len(q_text) > 50 else '')
                    print(f"[CHAT_MEMORY] 관련 대화 {i+1} - 질문: {q_preview}")
                formatted_conversations.append(doc)
            
            result = "\n\n".join(formatted_conversations)
            print(f"[CHAT_MEMORY] 관련 대화 {len(formatted_conversations)}개 가져오기 성공 (길이: {len(result)} 문자)")
            
            # 관련 대화 문자열 반환
            return result
        else:
            print(f"[CHAT_MEMORY] 관련 대화 검색 결과 없음")
            return "이전 대화 없음"
    except Exception as e:
        import traceback
        print(f"[CHAT_MEMORY] 관련 대화 검색 중 오류 발생: {e}")
        print(f"[ERROR] 관련 대화 검색 실패: {e}")
        traceback.print_exc()
        return "이전 대화 없음"

def reset_memory(session_id=None):
    """대화 기록을 초기화합니다. session_id가 None이면 모든 세션의 기록을 삭제합니다."""
    if not memory_client:
        print("[ERROR] 메모리 클라이언트가 초기화되지 않았습니다.")
        return False
    
    try:
        if session_id:
            collection_name = f"memory_{session_id}"
            try:
                memory_client.delete_collection(collection_name)
                print(f"[DEBUG] 세션 {session_id}의 대화 기록 삭제 완료")
            except Exception:
                print(f"[WARNING] 세션 {session_id}의 컬렉션이 존재하지 않거나 삭제할 수 없습니다.")
        else:
            # 모든 메모리 컬렉션 삭제
            collections = memory_client.list_collections()
            for collection in collections:
                if collection.name.startswith("memory_"):
                    memory_client.delete_collection(collection.name)
                    print(f"[DEBUG] 컬렉션 {collection.name} 삭제 완료")
        return True
    except Exception as e:
        print(f"[ERROR] 대화 기록 초기화 실패: {e}")
        traceback.print_exc()
        return False
