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

def get_or_create_collection(session_id: str):
    """세션별 대화 기록 컬렉션을 가져오거나 생성합니다."""
    if not memory_client:
        print("[ERROR] 메모리 클라이언트가 초기화되지 않았습니다.")
        return None
    
    collection_name = f"chat_memory_{session_id}"
    try:
        # 컬렉션 존재 여부 확인
        collections = [col.name for col in memory_client.list_collections()]
        
        if collection_name not in collections:
            print(f"[DEBUG] 컬렉션 생성: {collection_name}")
            collection = memory_client.create_collection(
                name=collection_name,
                embedding_function=openai_ef,
                metadata={"description": f"대화 기록 - 세션 {session_id}"}
            )
        else:
            print(f"[DEBUG] 기존 컬렉션 사용: {collection_name}")
            collection = memory_client.get_collection(
                name=collection_name,
                embedding_function=openai_ef
            )
        
        return collection
    except Exception as e:
        print(f"[ERROR] 컬렉션 가져오기/생성 실패: {e}")
        traceback.print_exc()
        return None

def normalize_question(question: str) -> str:
    """질문을 정규화합니다."""
    # 앞뒤 공백 제거
    question = question.strip()
    # 연속된 공백을 하나로
    question = ' '.join(question.split())
    return question

def save_conversation(session_id, question, answer):
    """대화 내용을 저장하고 중복을 제거합니다."""
    try:
        # 1. 질문 정규화
        normalized_question = normalize_question(question)
        print(f"[DEBUG] 정규화된 질문: '{normalized_question}'")
        
        # 2. 현재 대화의 해시값 계산
        current_hash = compute_hash(normalized_question)
        print(f"[DEBUG] 현재 질문 해시: {current_hash}")
        
        # 3. 컬렉션 가져오기 또는 생성
        collection = get_or_create_collection(session_id)
        if not collection:
            print("[ERROR] 컬렉션을 가져오거나 생성할 수 없습니다.")
            return
        
        # 4. 현재 질문의 임베딩 생성
        embedding = openai_ef(normalized_question)
        # NumPy 배열을 Python 리스트로 변환
        if hasattr(embedding, 'tolist'):
            embedding = embedding.tolist()
        if not isinstance(embedding, list):
            embedding = [embedding]
        
        # 5. 유사한 이전 대화 검색
        results = collection.query(
            query_embeddings=embedding,
            n_results=5  # 상위 5개 결과만 확인
        )
        
        # 6. 유사도가 높은 이전 대화가 있는지 확인
        if results and 'documents' in results and results['documents'] and results['documents'][0]:
            # 유사도 점수 확인
            if 'distances' in results and results['distances'] and results['distances'][0]:
                distances = results['distances'][0]
                # 유사도가 0.2 이하인 경우 중복으로 간주 (임계값 상향 조정)
                if any(distance < 0.2 for distance in distances):
                    print("[DEBUG] 유사한 이전 질문이 발견되어 중복을 제거합니다.")
                    return
        
        # 7. 새로운 대화 저장
        collection.add(
            documents=[f"Q: {normalized_question}\nA: {answer}"],
            metadatas=[{
                "session_id": session_id,
                "question_hash": current_hash,
                "timestamp": datetime.now().isoformat(),
                "original_question": question  # 원본 질문도 저장
            }],
            ids=[f"{session_id}_{current_hash}"]
        )
        print(f"[DEBUG] 새로운 대화 저장 완료: {current_hash}")
        
    except Exception as e:
        print(f"[ERROR] 대화 저장 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

def get_relevant_conversations(session_id: str, query: str, top_k: int = 3) -> str:
    """현재 질문과 관련된 이전 대화를 검색합니다."""
    try:
        # 1. 질문 정규화
        normalized_query = normalize_question(query)
        print(f"[DEBUG] 정규화된 검색 질문: '{normalized_query}'")
        
        # 2. 컬렉션 가져오기 또는 생성
        collection = get_or_create_collection(session_id)
        if not collection:
            print("[ERROR] 컬렉션을 가져오거나 생성할 수 없습니다.")
            return "이전 대화 없음"
        
        # 3. 현재 질문의 임베딩 생성
        embedding = openai_ef(normalized_query)
        # NumPy 배열을 Python 리스트로 변환
        if hasattr(embedding, 'tolist'):
            embedding = embedding.tolist()
        if not isinstance(embedding, list):
            embedding = [embedding]
        
        # 4. 유사한 이전 대화 검색
        results = collection.query(
            query_embeddings=embedding,
            n_results=top_k
        )
        
        # 5. 검색 결과 처리
        if not results or 'documents' not in results or not results['documents'] or not results['documents'][0]:
            print("[DEBUG] 관련된 이전 대화가 없습니다.")
            return "이전 대화 없음"
        
        # 6. 대화 기록 포맷팅
        conversations = []
        for idx, doc in enumerate(results['documents'][0]):
            # 유사도 점수 계산 (거리를 유사도로 변환)
            distance = results['distances'][0][idx] if 'distances' in results and results['distances'] else 1.0
            similarity = 1 - distance
            
            # 유사도가 0.4 이상인 대화만 포함 (임계값 하향 조정)
            if similarity >= 0.4:
                # 원본 질문이 있으면 표시
                original_question = results['metadatas'][0][idx].get('original_question', '')
                if original_question and original_question != normalized_query:
                    conversations.append(f"[관련 대화 {idx+1} (유사도: {similarity:.2f}, 원본: '{original_question}')]\n{doc}")
                else:
                    conversations.append(f"[관련 대화 {idx+1} (유사도: {similarity:.2f})]\n{doc}")
        
        if not conversations:
            print("[DEBUG] 유사도가 충분히 높은 이전 대화가 없습니다.")
            return "이전 대화 없음"
        
        # 7. 대화 기록 반환
        return "\n\n".join(conversations)
        
    except Exception as e:
        print(f"[ERROR] 대화 검색 중 오류 발생: {e}")
        import traceback
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
