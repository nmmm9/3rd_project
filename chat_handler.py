# chat_handler.py

import openai
import chromadb
from github_analyzer import chroma_client
from git_modifier import create_branch_and_commit
import re
import tiktoken
import db

# OpenAI 토큰 계산용 tokenizer 초기화
enc = tiktoken.get_encoding("cl100k_base")

# top-k 유사 청크 개수
TOP_K = 20

# 새로운 역할과 메타데이터를 활용한 시스템 프롬프트
SYSTEM_PROMPT_QA = """당신은 코드 분석과 이해에 특화된 전문적인 소프트웨어 엔지니어 AI입니다.

**답변 생성 전략:**
1.  **질문 의도 파악:** 사용자의 질문을 명확히 이해하고 핵심 요구사항을 식별합니다.
2.  **정보 수집 및 분석:** 제공된 코드 컨텍스트(메타데이터 포함), 프로젝트 디렉토리 구조, 이전 대화 기록을 종합적으로 분석하여 질문과 관련된 핵심 정보를 추출합니다. 특히, 다음 메타데이터를 적극 활용합니다:
    *   기본 정보: 파일명, 함수명, 클래스명, 시작/종료 라인
    *   코드 구조 정보: 청크 타입(class, method, function, code), 부모 엔티티
    *   코드 특성: 복잡도 점수, 상속 관계, 역할 태그
3.  **논리적 답변 구성:** 수집된 정보를 바탕으로 논리적인 흐름에 따라 답변을 구성합니다. 근거(파일명, 함수명, 클래스명, 라인, 청크 타입, 복잡도, 역할 등)를 명확히 제시하며 설명합니다.
4.  **맥락 유지 및 상세 설명:**
    *   계층적 코드 구조(부모-자식 관계, 상속 관계 등)를 고려하여 맥락을 유지합니다.
    *   복잡도 점수가 높은 코드 청크는 중요한 로직일 가능성이 높으므로 상세히 설명합니다.
    *   역할 태그를 활용하여 코드의 목적과 기능을 명확히 설명합니다.
    *   프로젝트 디렉토리 구조를 참고하여 관련 파일 간의 상호작용을 설명합니다.
5.  **가독성 높은 답변 작성:** 전문성과 가독성을 높이기 위해 아래 지침을 따릅니다.

**근거 기반의 정확한 답변 제공을 위해:**
1. 항상 근거(파일명, 함수명, 클래스명, 라인, 청크 타입, 복잡도, 역할 등)를 명시해서 설명하세요.
2. 계층적 코드 구조(부모-자식 관계, 상속 관계 등)를 고려하여 맥락을 유지하며 설명하세요.
3. 복잡도 점수가 높은 코드 청크는 중요한 비즈니스 로직이나 에러 처리에 해당할 가능성이 높으니 자세히 설명하세요.
4. 역할 태그를 활용하여 코드의 목적과 기능을 명확하게 설명하세요.
5. 프로젝트 디렉토리 구조를 활용하여 관련 파일간 상호 작용을 설명하세요.

**전문성과 가독성을 높이기 위해:**
- 한글 주석과 코드 예제를 적절히 활용하여 설명하세요.
- 중요한 코드 부분은 확인된 청크 타입(클래스, 메소드, 함수 등)을 활용하여 지적하세요.
- 복잡하거나 이해하기 어려운 코드는 단계별로 분해하여 설명하세요.
- 질문에 없는 정보는 추측하지 말고 '해당 정보는 제공된 코드에 없습니다'라고 명시하세요.
"""
SYSTEM_PROMPT_MODIFY = """당신은 코드 리팩터링, 버그 수정, 기능 추가에 특화된 전문 AI 개발자입니다.

**코드 수정 전략:**
1.  **요청 사항 명확히 이해:** 사용자의 코드 수정 요청 사항과 의도를 정확히 파악합니다.
2.  **관련 컨텍스트 심층 분석:** 제공된 코드 컨텍스트, 메타데이터, 프로젝트 구조, 이전 대화 기록을 면밀히 검토하여 수정 대상 코드와 주변 코드에 대한 깊이 있는 이해를 확보합니다. 다음 메타데이터를 적극 활용합니다:
    *   기본 정보: 파일명, 함수명, 클래스명, 시작/종료 라인
    *   코드 구조 정보: 청크 타입(class, method, function, code), 부모 엔티티
    *   코드 특성: 복잡도 점수, 상속 관계, 역할 태그
3.  **수정 계획 수립:** 분석된 정보를 바탕으로 구체적인 코드 수정 계획을 세웁니다. 기존 코드의 로직과 구조를 최대한 존중하면서 요청 사항을 반영할 수 있는 최적의 방법을 모색합니다.
4.  **정확하고 안전한 코드 생성:** 수립된 계획에 따라 코드를 수정합니다. 다음 원칙을 반드시 준수합니다.
5.  **자체 검토 및 개선:** 생성된 코드가 사용자의 모든 요구사항을 만족하는지, 잠재적인 오류는 없는지, 가독성은 뛰어난지 스스로 검토하고 필요한 경우 개선합니다.

**수정 시 지켜야 할 원칙:**
1. 계층적 코드 구조와 상속 관계를 파악하여 추가/수정해야 할 부분을 정확히 파악하세요.
2. 복잡도가 높은 코드 부분을 수정할 때는 특별히 주의하여 기존 로직을 유지하세요.
3. 역할 태그를 고려하여 코드의 목적과 기능이 유지되도록 하세요.
4. 수정이 다른 파일에 영향을 미칠 수 있는지 확인하고, 필요하다면 관련 변경 사항도 함께 제안하거나 명시하세요.

**수정된 코드 반환 형식:**
- 수정된 코드는 반드시 '// FILE: 파일명\n<전체 코드>' 형식으로 작성하세요.
- 주요 변경 사항을 한글 주석으로 표시하여 사용자가 변경을 쉽게 이해할 수 있게 하세요.
- 불필요한 변경은 하지 말고, 요청한 부분만 명확하게 반영하세요.
"""

# 확장된 메타데이터와 계층적 코드 구조를 활용한 프롬프트
PROMPT_TEMPLATE = """
아래는 사용자의 질문과 관련된 코드 컨텍스트, 프로젝트 구조, 이전 대화 기록 및 엔티티 관계입니다.

[프로젝트 디렉토리 구조]
{directory_structure}

[이전 대화 기록]
{conversation_history}

[코드 컨텍스트]
각 코드 청크는 다음 메타데이터를 포함할 수 있습니다:
- 기본 정보: 파일명, 함수명, 클래스명, 시작/종료 라인
- 구조 정보: 청크 타입(class, method, function, code), 부모 엔티티
- 추가 특성: 복잡도 점수, 상속 관계, 역할 태그

{context}

[질문]
{question}

**이 질문에 답변할 때, 다음 전략과 지침을 엄격히 따르세요:**

**1. 정보 종합 및 핵심 파악:**
   - 제공된 모든 정보([프로젝트 디렉토리 구조], [이전 대화 기록], [코드 컨텍스트], [질문])를 면밀히 검토합니다.
   - 질문의 핵심 의도와 가장 직접적으로 관련된 코드 청크, 메타데이터, 이전 대화 내용을 식별합니다.

**2. 컨텍스트 심층 분석 및 활용:**
   - 청크 타입(class, method, function, code)에 따라 코드의 목적과 역할을 정확히 파악하세요.
   - 부모-자식 관계와 상속 관계를 고려하여 코드의 구조적 맥락을 유지하세요.
   - 복잡도 점수가 높은 청크는 중요한 비즈니스 로직일 가능성이 높으니 특별히 주의하여 분석하고 설명에 반영하세요.
   - 역할 태그를 활용하여 코드의 기능적 의도를 파악하고, 이를 답변의 주요 근거로 활용하세요.
   - 프로젝트 디렉토리 구조를 참고하여 파일 간의 연관성이나 전체 시스템에서의 역할 등을 설명에 포함하세요.

**3. 논리적이고 명확한 답변 생성:**
   - 분석된 내용을 바탕으로, 단계별로 명확하고 논리적인 답변을 구성합니다.
   - 지나치게 긴 답변은 피하고, 핵심 내용을 중심으로 간결하게 설명하되, 필요시 코드 예시를 포함하여 이해를 돕습니다.

**4. 답변 형식 및 스타일 준수:**
   위 코드, 메타데이터, 프로젝트 구조, 이전 대화 기록, 질문을 참고하여, 반드시 한글로, 예시와 함께, 친절하게 답변해 주세요.
   - 답변에는 반드시 근거(예: `파일명`, `함수명`, `클래스명`, 라인 번호, 청크 타입, 복잡도, 역할 태그 등)를 명확히 포함하세요.
   - 이전 대화 내용과 일관성을 유지하면서 답변하세요.
   - 코드 예시는 반드시 **코드 블록(```)** 과 **한글 주석**을 적극적으로 활용하여 제공하세요.
   - 파일명, 함수명, 클래스명 등 코드 요소는 **백틱(` `)** 으로 감싸서 명확하게 표시하세요.
   - **중요한 정보는 굵게 표시**하거나, *기울임꼴*을 사용하여 강조하세요.
   - 여러 항목을 나열할 때는 **목록(순서 없는 목록 `-` 또는 순서 있는 목록 `1.`)** 을 적극적으로 활용하세요.
   - 단락 사이에 빈 줄을 넣어 시각적인 구분을 명확히 하세요.
   - 답변의 시작이나 끝에 **요약 또는 결론 섹션**을 추가하여 핵심 내용을 빠르게 파악할 수 있도록 하세요.
   - 단계별 설명, 표, 요약, 비교, 한계 등 다양한 마크다운 형식을 적극적으로 활용하여 가독성을 높이세요.
   - 프로젝트 구조와 코드의 역할(역할 태그)을 바탕으로, 전체 맥락과 흐름을 설명하세요.
   - 질문이 역할 기반일 경우, 역할 태그와 가장 관련 있는 코드 근거를 들어 설명하세요.
   - 모르는 부분이나 코드에 없는 정보는 추측하지 말고 "해당 정보는 코드에 없습니다"라고 답변하세요.
   - 답변의 신뢰도를 높이기 위해, 항상 답변의 출처(파일명, 함수명, 역할 등)를 함께 제시하세요.
"""

MODIFY_PROMPT_TEMPLATE = """
아래는 사용자의 코드 수정 요청과 관련된 코드 청크, 프로젝트 구조 및 이전 대화 기록입니다.

[프로젝트 디렉토리 구조]
{directory_structure}

[이전 관련 대화]
{conversation_history}

[코드 컨텍스트]
{context}

[수정 요청]
{request}

**요청된 코드를 수정할 때, 다음 전략과 지침을 엄격히 따르세요:**

**1. 정보 종합 및 핵심 파악:**
   - 제공된 모든 정보([프로젝트 디렉토리 구조], [이전 관련 대화], [코드 컨텍스트], [수정 요청])를 면밀히 검토합니다.
   - 수정 요청의 핵심 의도와 가장 직접적으로 관련된 코드 청크, 메타데이터, 이전 대화 내용을 식별합니다.

**2. 컨텍스트 심층 분석 및 반영:**
   - 코드 청크의 메타데이터(청크 타입, 부모 엔티티, 복잡도, 상속 관계, 역할 태그 등)를 심층적으로 분석하여 수정에 반영합니다.
   - 특히, 계층적 코드 구조와 상속 관계를 파악하여 영향을 받을 수 있는 모든 부분을 고려합니다.
   - 복잡도가 높은 코드를 수정할 때는 기존 로직이 손상되지 않도록 각별히 주의합니다.
   - 역할 태그를 참고하여 코드의 원래 목적과 기능이 유지되거나 개선되도록 합니다.
   - 프로젝트 디렉토리 구조를 고려하여, 수정 사항이 다른 파일이나 모듈에 미칠 수 있는 잠재적 영향을 평가합니다.

**3. 정확하고 완전한 코드 생성:**
   - 분석된 내용을 바탕으로, 아래 지정된 형식에 맞춰 수정된 **전체 코드**를 생성합니다.
   - 불필요한 변경은 최소화하고, 요청된 부분만 명확하게 반영합니다.
   - 이전 대화에서 논의된 수정 사항이 있다면 반드시 일관성을 유지합니다.

**4. 코드 반환 형식 및 추가 설명:**
   아래 형식으로 전체 코드를 수정해서 보여주세요.
   // FILE: 파일명
   <수정된 전체 코드>

   - 반드시 한글 주석을 주요 변경 사항 위주로 포함하여 사용자가 이해하기 쉽게 만드세요.
   - 코드 외에 추가적인 설명(예: 변경 이유, 잠재적 영향 등)이 필요하다고 판단되면, 코드 블록 아래에 명확하게 작성하세요.
"""

def parse_llm_code_response(llm_response):
    # // FILE: ... 또는 파일명: ... 패턴에서 파일명과 코드 추출
    m = re.search(r'// FILE: ([^\n]+)\n([\s\S]+)', llm_response)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m2 = re.search(r'파일명[:：]\s*([^\n]+)\n([\s\S]+)', llm_response)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip()
    return None, llm_response.strip()

def handle_chat(session_id, message):
    # DB에서 세션 정보 확인
    session_data = db.get_session_data_from_db(session_id)
    if not session_data:
        print(f"[ERROR] 세션 {session_id}를 찾을 수 없습니다.")
        return {'answer': '세션을 찾을 수 없습니다. 새로운 분석을 시작해주세요.', 'error': 'session_not_found'}
    
    # DB에서 세션 데이터 조회
    session_data = db.get_session_data_from_db(session_id)
    repo_path = f"./repos/{session_id}"
    
    print(f"[DEBUG] 세션 데이터 키: {list(session_data.keys())}")
    
    context_chunks = []
    full_file_contexts = []
    directory_structure = ""
    
    # 1. 질문 임베딩 생성
    print(f"[DEBUG] 질문 임베딩 생성 시작: '{message[:50]}...'")
    try:
        # OpenAI API 키 확인
        api_key = openai.api_key
        if not api_key:
            print("[ERROR] OpenAI API 키가 설정되지 않았습니다.")
            return {
                'answer': "OpenAI API 키가 설정되지 않았습니다.",
                'error': "api_key_missing"
            }
        print(f"[DEBUG] OpenAI API 키 확인: {api_key[:4]}...{api_key[-4:]}")
        
        # 메시지 길이 체크 및 잘라내기 (text-embedding-3-large 모델 토큰 제한: 8192)
        message_tokens = len(enc.encode(message))
        print(f"[DEBUG] 메시지 토큰 수: {message_tokens}")
        
        embedding_input = message
        if message_tokens > 8000:  # 안전 마진을 두고 8000 토큰으로 제한
            print(f"[WARNING] 메시지가 너무 깁니다 ({message_tokens} 토큰). 8000 토큰으로 잘라냅니다.")
            # 토큰 단위로 잘라내기
            tokens = enc.encode(message)
            truncated_tokens = tokens[:8000]
            embedding_input = enc.decode(truncated_tokens)
            print(f"[DEBUG] 잘라낸 메시지 토큰 수: {len(enc.encode(embedding_input))}")
        
        # 임베딩 생성 시도
        print(f"[DEBUG] OpenAI 임베딩 API 호출 시도")
        embedding_response = openai.embeddings.create(
            input=embedding_input,
            model="text-embedding-3-large"
        )
        
        # 임베딩 결과 처리
        if not embedding_response or not embedding_response.data or not embedding_response.data[0].embedding:
            print(f"[ERROR] 임베딩 결과가 비어 있습니다: {embedding_response}")
            return {
                'answer': "임베딩 생성 중 오류가 발생했습니다: 임베딩 결과가 비어 있습니다.",
                'error': "empty_embedding"
            }
            
        embedding = embedding_response.data[0].embedding
        print(f"[DEBUG] 질문 임베딩 생성 성공 (차원: {len(embedding)})")
    except Exception as e:
        import traceback
        print(f"[ERROR] 질문 임베딩 생성 실패: {e}")
        traceback.print_exc()
        return {
            'answer': f"임베딩 생성 중 오류가 발생했습니다: {str(e)}",
            'error': "embedding_error"
        }

    # 2. ChromaDB에서 유사 코드 청크 검색
    try:
        # ChromaDB 클라이언트 상태 확인
        if not chroma_client:
            print("[ERROR] ChromaDB 클라이언트가 초기화되지 않았습니다.")
            return {
                'answer': "저장소 분석 데이터에 접근할 수 없습니다. 서버를 재시작하고 저장소를 다시 분석해주세요.",
                'error': "chroma_client_not_initialized"
            }
        
        # 컬렉션 이름 생성 및 조회 시도
        collection_name = f"repo_{session_id}"
        print(f"[DEBUG] ChromaDB 컬렉션 조회 시도: {collection_name}")
        
        # 컬렉션 목록 확인
        try:
            collections = chroma_client.list_collections()
            collection_names = [col.name for col in collections]
            print(f"[DEBUG] 사용 가능한 컬렉션 목록: {collection_names}")
        except Exception as e:
            import traceback
            print(f"[ERROR] ChromaDB 컬렉션 목록 조회 실패: {e}")
            traceback.print_exc()
            return {
                'answer': f"저장소 분석 데이터 접근 중 오류가 발생했습니다: {str(e)}",
                'error': "collection_list_error"
            }
        
        # 컬렉션 존재 여부 확인
        if collection_name not in collection_names:
            print(f"[ERROR] 컬렉션을 찾을 수 없음: {collection_name}")
            return {
                'answer': f"저장소 분석 데이터를 찾을 수 없습니다. 저장소를 다시 분석해주세요.",
                'error': "collection_not_found"
            }
        
        # 컬렉션 가져오기
        try:    
            collection = chroma_client.get_collection(name=collection_name)
            print(f"[DEBUG] 컬렉션 조회 성공: {collection_name}")
        except Exception as e:
            import traceback
            print(f"[ERROR] 컬렉션 가져오기 실패: {e}")
            traceback.print_exc()
            return {
                'answer': f"저장소 분석 데이터 접근 중 오류가 발생했습니다: {str(e)}",
                'error': "collection_access_error"
            }
        
        # 컬렉션 내 문서 수 확인
        try:
            collection_count = collection.count()
            print(f"[DEBUG] 컬렉션 내 문서 수: {collection_count}")
            if collection_count == 0:
                print(f"[WARNING] 컬렉션이 비어 있습니다: {collection_name}")
                # 디렉토리 구조만으로 답변 생성
                directory_structure = session_data.get('directory_structure', '')
                if directory_structure:
                    answer = f"이 저장소는 분석 가능한 코드 파일이 없지만, 디렉토리 구조를 확인할 수 있습니다:\n\n{directory_structure}\n\n저장소에 대한 구체적인 질문이 있으시면 말씀해 주세요."
                    return {'answer': answer}
                else:
                    return {
                        'answer': "저장소 분석 데이터가 비어 있습니다. 저장소를 다시 분석해주세요.",
                        'error': "empty_collection"
                    }
        except Exception as e:
            import traceback
            print(f"[WARNING] 컬렉션 문서 수 확인 실패: {e}")
            traceback.print_exc()
            # 문서 수 확인 실패는 치명적이지 않을 수 있으므로 계속 진행
        
        # 유사 코드 청크 검색
        print(f"[DEBUG] 유사 코드 청크 검색 시작 (TOP_K={TOP_K})")
        try:
            results = collection.query(
                query_embeddings=[embedding],
                n_results=TOP_K
            )
            print(f"[DEBUG] 검색 결과 구조: {list(results.keys())}")
        except Exception as e:
            import traceback
            print(f"[ERROR] 유사 코드 청크 검색 실패: {e}")
            traceback.print_exc()
            return {
                'answer': f"코드 검색 중 오류가 발생했습니다: {str(e)}",
                'error': "query_error"
            }
        
        # 1. 질문 의도 태깅 (LLM)
        try:
            tag_prompt = f"아래 질문의 의도(원하는 코드 역할/기능)를 한글로 간단히 요약해줘.\n\n질문:\n{message}"
            tag_resp = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": tag_prompt}],
                temperature=0.0,
                max_tokens=64
            )
            question_role_tag = tag_resp.choices[0].message.content.strip()
            print(f"[DEBUG] 질문 의도 태그: {question_role_tag}")
        except Exception as e:
            print(f"[WARNING] 질문 의도 태깅 실패: {e}")
            question_role_tag = ''
        # 스코프 키워드 추출
        scope = extract_scope_from_question(message)
        
        # 동적 토큰 버젯 계산 (질문 복잡도에 따라 조정)
        question_tokens = len(enc.encode(message))
        max_context_tokens = 8192 - question_tokens - 1000  # 응답 공간 확보
        
        # 정규화된 질문 의도 키워드 추출
        question_keywords = []
        if question_role_tag:
            question_keywords = [k.strip() for k in re.split(r'[,:\s]+', question_role_tag) if k.strip()]
        print(f"[DEBUG] 질문 키워드: {question_keywords}")
        
        # 청크 스코어링 및 선택 함수
        def score_chunk(doc, meta, distance):
            score = 0
            
            # 1. 유사도 점수 (거리가 작을수록 높은 점수)
            similarity_score = 1 - min(distance, 1.0)  # 0~1 범위 정규화
            score += similarity_score * 10  # 기본 가중치 10
            
            # 2. 역할 태그 매칭 점수
            role_tag = meta.get('role_tag', '')
            if question_role_tag and role_tag:
                # 완전 일치 또는 포함 관계 점수
                if question_role_tag == role_tag:
                    score += 5
                elif question_role_tag in role_tag:
                    score += 3
                elif role_tag in question_role_tag:
                    score += 2
                
                # 키워드 일치 점수
                for keyword in question_keywords:
                    if keyword and len(keyword) > 1 and keyword in role_tag:
                        score += 1
            
            # 3. 스코프 매칭 점수
            file_name = meta.get('file_name', '')
            func_name = meta.get('function_name', '')
            class_name = meta.get('class_name', '')
            
            if scope['file'] and any(f in file_name for f in scope['file']):
                score += 3
            if scope['class'] and any(c in class_name for c in scope['class']):
                score += 3
            if scope['function'] and any(f in func_name for f in scope['function']):
                score += 3
            
            # 4. 청크 타입 및 복잡도 점수
            chunk_type = meta.get('chunk_type', 'code')
            complexity = meta.get('complexity', 1)
            
            # 클래스/함수 정의에 높은 점수 부여
            if chunk_type == 'class':
                score += 2
            elif chunk_type == 'function':
                score += 1.5
            elif chunk_type == 'method':
                score += 1
            
            # 복잡도가 높은 청크에 약간 더 높은 점수 (중요한 로직일 가능성)
            score += min(complexity / 10, 1)  # 최대 1점 추가
            
            # 5. 중복 필터링을 위한 식별자
            identity = f"{meta.get('path', '')}:{meta.get('function_name', '')}:{meta.get('class_name', '')}"
            
            return {
                'doc': doc,
                'meta': meta,
                'score': score,
                'identity': identity,
                'tokens': len(enc.encode(doc)),
                'distance': distance
            }
        
        # 청크 스코어링 및 정렬
        scored_chunks = []
        if 'documents' in results and 'metadatas' in results and 'distances' in results:
            if results['documents'][0] and results['metadatas'][0] and results['distances'][0]:
                for doc, meta, distance in zip(results['documents'][0], results['metadatas'][0], results['distances'][0]):
                    scored_chunks.append(score_chunk(doc, meta, distance))
                
                # 점수 기준 내림차순 정렬
                scored_chunks.sort(key=lambda x: x['score'], reverse=True)
                
                # 스코어링 결과 로깅
                for i, chunk in enumerate(scored_chunks[:10]):  # 상위 10개만 로깅
                    print(f"[DEBUG] 청크 {i}: 점수={chunk['score']:.2f}, 파일={chunk['meta'].get('file_name')}, " +
                          f"함수={chunk['meta'].get('function_name')}, 클래스={chunk['meta'].get('class_name')}, " +
                          f"유사도={1-chunk['distance']:.3f}")
        
        # 토큰 버젯 내에서 중복 제거하며 청크 선택
        context_chunks = []
        token_count = 0
        seen_identities = set()
        
        for chunk in scored_chunks:
            # 이미 동일 파일/함수/클래스의 청크가 포함되었는지 확인
            if chunk['identity'] in seen_identities:
                continue
            
            # 토큰 버젯 확인
            if token_count + chunk['tokens'] > max_context_tokens:
                # 버젯 초과 시 중요도가 낮은 청크는 스킵
                if chunk['score'] < 5:  # 임계점 이하면 스킵
                    continue
                # 너무 큰 청크는 스킵 (토큰 버젯의 30% 초과)
                if chunk['tokens'] > max_context_tokens * 0.3:
                    continue
            
            # 메타데이터 정보 구성
            meta = chunk['meta']
            meta_info = []
            if meta.get('file_name'): meta_info.append(f"파일명: {meta['file_name']}")
            if meta.get('function_name'): meta_info.append(f"함수: {meta['function_name']}")
            if meta.get('class_name'): meta_info.append(f"클래스: {meta['class_name']}")
            if meta.get('start_line') and meta.get('end_line'):
                meta_info.append(f"라인: {meta['start_line']}~{meta['end_line']}")
            if meta.get('chunk_type'): meta_info.append(f"타입: {meta['chunk_type']}")
            if meta.get('role_tag'): meta_info.append(f"역할: {meta['role_tag']}")
            
            # 청크 컨텍스트에 추가
            chunk_str = f"[{'/'.join(meta_info)}]\n{chunk['doc']}"
            context_chunks.append(chunk_str)
            token_count += chunk['tokens']
            seen_identities.add(chunk['identity'])
            
            # 충분한 컨텍스트를 모았으면 중단
            if len(context_chunks) >= 10 or token_count >= max_context_tokens * 0.9:
                break
        
        # 컨텍스트가 너무 적으면 스코어가 낮은 청크도 추가
        if len(context_chunks) < 3 and scored_chunks:
            for chunk in scored_chunks:
                if chunk['identity'] not in seen_identities:
                    meta = chunk['meta']
                    meta_info = []
                    if meta.get('file_name'): meta_info.append(f"파일명: {meta['file_name']}")
                    if meta.get('function_name'): meta_info.append(f"함수: {meta['function_name']}")
                    if meta.get('class_name'): meta_info.append(f"클래스: {meta['class_name']}")
                    if meta.get('start_line') and meta.get('end_line'):
                        meta_info.append(f"라인: {meta['start_line']}~{meta['end_line']}")
                    if meta.get('role_tag'): meta_info.append(f"역할: {meta['role_tag']}")
                    
                    chunk_str = f"[{'/'.join(meta_info)}]\n{chunk['doc']}"
                    context_chunks.append(chunk_str)
                    token_count += chunk['tokens']
                    seen_identities.add(chunk['identity'])
                    
                    if len(context_chunks) >= 5 or token_count >= max_context_tokens * 0.9:
                        break
        # 4. 프롬프트에 컨텍스트 범위 안내
        context = '\n\n'.join(context_chunks)
        context = f"아래는 [파일/함수/클래스/라인/역할] 단위로 추출된 컨텍스트입니다.\n{context}"
        print(f"[DEBUG] 유사 코드 청크 {len(context_chunks)}개 찾음 (총 {len(context)} 문자)")
        print("[DEBUG] 컨텍스트 구성 요약:")
        if full_file_contexts: # 컨텍스트가 전체 파일 내용으로 구성된 경우
            print("  컨텍스트는 다음 전체 파일 내용으로 구성됩니다:")
            for i, file_context_str in enumerate(full_file_contexts):
                file_header = file_context_str.partition('\n')[0] # "// FILE: ..." 부분 추출
                print(f"    {i+1}. {file_header}")
        elif context_chunks: # 컨텍스트가 코드 청크로 구성된 경우
            print("  컨텍스트는 다음 코드 청크의 메타데이터로 구성됩니다:")
            for i, chunk_str in enumerate(context_chunks):
                metadata_header = chunk_str.partition('\n')[0] # "[메타데이터...]" 부분 추출
                print(f"    {i+1}. {metadata_header}")
        else: # 컨텍스트 내용이 없는 경우
            print("  컨텍스트에 포함된 내용이 없습니다.")
        
        # 검색된 파일 경로 로깅
        if 'metadatas' in results and results['metadatas'] and results['metadatas'][0]:
            paths = [meta.get('path', 'unknown') for meta in results['metadatas'][0]]
            print(f"[DEBUG] 검색된 파일 경로: {paths}")
            # 유사도 점수 로깅 (있는 경우)
            if 'distances' in results and results['distances'] and results['distances'][0]:
                distances = results['distances'][0]
                print(f"[DEBUG] 검색 유사도 점수: {distances}")
                # 파일 경로와 유사도 점수 매핑
                path_scores = list(zip(paths, distances))
                print(f"[DEBUG] 파일별 유사도 점수: {path_scores}")
        else:
            print("[WARNING] 검색 결과에 메타데이터가 없습니다.")

    except Exception as e:
        print(f"[ERROR] 코드 청크 검색 오류: {e}")
        return {
            'answer': f"코드 검색 중 오류가 발생했습니다: {str(e)}",
            'error': "search_error"
        }
    
    # 디렉토리 구조 확인
    directory_structure = session_data.get('directory_structure')
    
    if directory_structure:
        print(f"[DEBUG] 디렉토리 구조 정보 제공 (길이: {len(directory_structure)} 문자)")
    else:
        print("[DEBUG] 디렉토리 구조 정보가 없습니다.")
        directory_structure = "프로젝트 구조 정보가 없습니다. 파일 내용만 참고하여 응답하겠습니다."

    # 파일 전체 코드 요구 패턴 감지
    file_full_keywords = ["전체", "전체 코드", "전체내용", "전체 보여", "전체 출력"]
    is_full_file_request = any(kw in message for kw in file_full_keywords)
    scope = extract_scope_from_question(message)
    full_file_contexts = []
    if is_full_file_request and scope['file']:
        for fname in scope['file']:
            # 세션 데이터에서 파일 경로 찾기
            file_path = None
            for f in session_data.get('files', []):
                if f.get('file_name') and fname in f['file_name']:
                    file_path = f['path']
                    break
            if file_path:
                try:
                    with open(f"{repo_path}/{file_path}", 'r', encoding='utf-8') as f:
                        code = f.read()
                    full_file_contexts.append(f"// FILE: {file_path}\n{code}")
                except Exception as e:
                    print(f"[WARNING] 파일 전체 코드 로드 실패: {file_path}, {e}")

    # 청크 검색 결과와 파일 전체 내용 합치기
    if full_file_contexts:
        context = '\n\n'.join(full_file_contexts)
    else:
        # 기존 방식
        context = '\n\n'.join(context_chunks)
    context = f"아래는 [파일/함수/클래스/라인/역할] 단위로 추출된 컨텍스트입니다.\n{context}"
    
    # 검색된 파일 경로 로깅
    if 'metadatas' in results and results['metadatas'] and results['metadatas'][0]:
        paths = [meta.get('path', 'unknown') for meta in results['metadatas'][0]]
        print(f"[DEBUG] 검색된 파일 경로: {paths}")
        # 유사도 점수 로깅 (있는 경우)
        if 'distances' in results and results['distances'] and results['distances'][0]:
            distances = results['distances'][0]
            print(f"[DEBUG] 검색 유사도 점수: {distances}")
            # 파일 경로와 유사도 점수 매핑
            path_scores = list(zip(paths, distances))
            print(f"[DEBUG] 파일별 유사도 점수: {path_scores}")
    else:
        print("[WARNING] 검색 결과에 메타데이터가 없습니다.")

    # 3. LLM에 컨텍스트와 함께 전달하여 답변 생성
    try:
        # 이전 대화 기록 가져오기 (DB에서)
        print(f"[CHAT_HANDLER] 이전 대화 기록 가져오기 시작 - 세션: {session_id}")
        chat_history = db.get_chat_history(session_id)
        
        # 대화 기록을 문자열로 포맷팅
        conversation_history = ""
        if chat_history:
            for chat in chat_history[-6:]:  # 최근 6개 대화만 사용
                role = "사용자" if chat['role'] == 'user' else "AI"
                message_content = chat.get('content') or chat.get('message', '')
                conversation_history += f"[{role}] {message_content}\n\n"
        
        if not conversation_history:
            conversation_history = "이전 대화 없음"
            print(f"[CHAT_HANDLER] 관련 대화 기록이 없습니다.")
        else:
            print(f"[CHAT_HANDLER] 가져온 대화 기록 수: {len(chat_history)} 개")
        
        # 프롬프트 생성 (대화 기록 포함)
        prompt = PROMPT_TEMPLATE.format(
            context=context, 
            question=message,
            directory_structure=directory_structure,
            conversation_history=conversation_history
        )
        print("\n[LLM 프롬프트]\n" + prompt + "\n")  # 프롬프트 확인용 출력

        # 대화 기록이 최종 프롬프트에 포함되었는지 확인
        if conversation_history and conversation_history != '이전 대화 없음':
            if conversation_history in prompt:
                print(f"[INFO] 성공: 이전 대화 기록 (길이: {len(conversation_history)})이 최종 프롬프트에 포함되었습니다.")
            else:
                print(f"[WARNING] 실패: 이전 대화 기록이 최종 프롬프트에 포함되지 않았습니다. 기록 앞부분: {conversation_history[:200]}...")
        elif conversation_history == '이전 대화 없음':
            print(f"[INFO] '이전 대화 없음' 상태이므로 프롬프트 포함 여부를 확인하지 않습니다.")
        else: # This case implies conversation_history is an empty string or None, if not '이전 대화 없음'
            print(f"[INFO] conversation_history가 비어있거나 (None or '') 예상치 못한 상태이므로 프롬프트 포함 여부를 확인하지 않습니다: '{conversation_history}'")
        print(f"[DEBUG] 프롬프트 길이: {len(prompt)} 문자")
        
        # 프롬프트 길이 제한 확인
        if len(prompt) > 100000:  # OpenAI API의 토큰 제한을 고려한 값
            print(f"[WARNING] 프롬프트가 너무 깁니다. 컨텍스트 일부를 잘라냅니다.")
            # 컨텍스트 길이 제한
            max_context_length = 80000  # 적절한 길이로 조정
            truncated_context = context[:max_context_length] + "\n... (컨텍스트 길이 제한으로 인해 일부 내용이 생략되었습니다) ..."
            prompt = PROMPT_TEMPLATE.format(
                context=truncated_context, 
                question=message,
                directory_structure=directory_structure
            )
            print(f"[DEBUG] 수정된 프롬프트 길이: {len(prompt)} 문자")
        
        # LLM 호출
        print(f"[DEBUG] OpenAI API 호출 시작 (model=gpt-4o, temperature=0.2)")
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": SYSTEM_PROMPT_QA},
                      {"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=4096
        )
        
        # 응답 처리
        if not response or not response.choices or not response.choices[0].message:
            print(f"[ERROR] LLM 응답이 비어 있습니다: {response}")
            return {
                'answer': "응답 생성 중 오류가 발생했습니다. 다시 시도해주세요.",
                'error': "empty_response"
            }
        
        answer = response.choices[0].message.content.strip()
        print(f"[DEBUG] LLM 응답 성공 (길이: {len(answer)} 문자)")
        
        # 대화 기록 저장 (DB에만)
        try:
            print(f"[CHAT_HANDLER] 대화 기록 저장 시작 - 세션: {session_id}")
            
            # 컨텍스트 정보가 포함된 사용자 메시지 생성 (파일명만 저장)
            user_message_with_context = message
            
            # 메시지에서 컨텍스트 정보 추출하여 파일명만 저장
            if '[선택된 파일 컨텍스트]' in message:
                # 메시지를 질문 부분과 컨텍스트 부분으로 분리
                parts = message.split('\n\n[선택된 파일 컨텍스트]\n')
                if len(parts) > 1:
                    user_message_with_context = parts[0]  # 질문 부분만
                    
                    # 컨텍스트에서 파일명만 추출
                    context_part = parts[1]
                    context_files = []
                    
                    # "--- 파일명 (브랜치: 브랜치명) ---" 패턴에서 파일명 추출
                    file_patterns = re.findall(r'--- (.+?) \(브랜치: .+?\) ---', context_part)
                    for file_path in file_patterns:
                        # 파일명에서 경로 부분만 추출 (디렉토리 구조 포함)
                        clean_file_name = file_path.strip()
                        if clean_file_name not in context_files:
                            context_files.append(clean_file_name)
                    
                    # 파일명만 저장 (내용은 저장하지 않음)
                    if context_files:
                        user_message_with_context += f"\n\n[선택된 파일: {', '.join(context_files)}]"
            elif context_chunks:
                # 새로운 방식으로 선택된 파일이 있는 경우
                context_files = []
                for chunk in context_chunks:
                    # 메타데이터에서 파일명 추출
                    if '[' in chunk and ']' in chunk:
                        meta_part = chunk.split('\n')[0]
                        if '파일명:' in meta_part:
                            file_name = meta_part.split('파일명:')[1].split(',')[0].strip()
                            if file_name not in context_files:
                                context_files.append(file_name)
                
                # 파일명만 저장
                if context_files:
                    user_message_with_context += f"\n\n[선택된 파일: {', '.join(context_files)}]"
            
            # 추가 보안: 메시지에서 파일 내용이 포함된 경우 제거
            # 파일 내용 패턴 제거 (코드 블록, 긴 텍스트 등)
            lines = user_message_with_context.split('\n')
            filtered_lines = []
            skip_content = False
            
            for line in lines:
                # 파일 내용 시작 패턴 감지
                if line.strip().startswith('---') and '브랜치:' in line:
                    skip_content = True
                    continue
                elif skip_content and (line.strip() == '' or line.startswith('---')):
                    # 파일 내용 끝 감지
                    if line.startswith('---') and '브랜치:' in line:
                        continue
                    skip_content = False
                    if line.strip() == '':
                        continue
                
                # 파일 내용이 아닌 경우만 포함
                if not skip_content:
                    filtered_lines.append(line)
            
            user_message_with_context = '\n'.join(filtered_lines).strip()
            
            # DB에 채팅 기록 저장 (컨텍스트 정보 포함)
            db.add_chat_history(session_id, 'user', user_message_with_context)
            db.add_chat_history(session_id, 'assistant', answer)
            print(f"[CHAT_HANDLER] DB에 대화 기록 저장 성공: session_id={session_id}")
        except Exception as e:
            print(f"[CHAT_HANDLER] DB에 대화 기록 저장 실패: {str(e)}")
        
        # 응답이 비어있는지 확인
        if not answer:
            print("[WARNING] LLM이 비어있는 응답을 리턴했습니다.")
            return {
                'answer': "질문에 대한 답변을 생성하지 못했습니다. 다른 질문을 시도해주세요.",
                'error': "empty_answer"
            }
        
        # 성공적인 응답 반환
        return {'answer': answer}
    except Exception as e:
        import traceback
        print(f"[ERROR] LLM 호출 오류: {e}")
        traceback.print_exc()
        return {
            'answer': f"응답 생성 중 오류가 발생했습니다: {str(e)}",
            'error': "llm_error"
        }

def handle_modify_request(session_id, message):
    print(f"[DEBUG] 현재 세션 ID: {session_id}")
    
    # DB에서 세션 데이터 조회
    session_data = db.get_session_data_from_db(session_id)
    repo_path = f"./repos/{session_id}"
    
    # GitHub 푸시 의도 감지 및 로깅
    has_push_intent = detect_github_push_intent(message)
    token_exists = bool(session_data.get('token') if session_data else False)
    requires_confirmation = has_push_intent
    push_intent_message = '깃허브에 적용하려면 확인이 필요합니다.' if has_push_intent else ''
    print(f"[DEBUG] GitHub 푸시 의도 감지 결과: {has_push_intent}, 토큰 존재: {token_exists}")
    
    # 세션 데이터가 없으면 오류 반환
    if not session_data:
        return {
            'answer': "세션 데이터가 없습니다. 새로운 레포지토리를 분석해주세요.",
            'error': "session_not_found",
            'modified_code': "",
            'file_name': "",
            'has_push_intent': has_push_intent,
            'token_exists': token_exists,
            'requires_confirmation': requires_confirmation,
            'push_intent_message': push_intent_message
        }
    
    print(f"[DEBUG] 세션 데이터 키: {list(session_data.keys())}")
    
    # 1단계: 청크 검색으로 관련 파일 식별
    try:
        # OpenAI API 키 확인
        api_key = openai.api_key
        if not api_key:
            print("[ERROR] OpenAI API 키가 설정되지 않았습니다.")
            return {
                'answer': "OpenAI API 키가 설정되지 않았습니다.",
                'error': "api_key_missing",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        print(f"[DEBUG] OpenAI API 키 확인: {api_key[:4]}...{api_key[-4:]}")
        
        # 임베딩 생성
        print(f"[DEBUG] 수정 요청 임베딩 생성 시작: '{message[:50]}...'")
        embedding_response = openai.embeddings.create(
            input=message,
                            model="text-embedding-3-large"
        )
        
        # 임베딩 결과 처리
        if not embedding_response or not embedding_response.data or not embedding_response.data[0].embedding:
            print(f"[ERROR] 임베딩 결과가 비어 있습니다: {embedding_response}")
            return {
                'answer': "임베딩 생성 중 오류가 발생했습니다: 임베딩 결과가 비어 있습니다.",
                'error': "empty_embedding",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
            
        embedding = embedding_response.data[0].embedding
        print(f"[DEBUG] 수정 요청 임베딩 생성 성공 (차원: {len(embedding)})")
        
        # ChromaDB 클라이언트 상태 확인
        if not chroma_client:
            print("[ERROR] ChromaDB 클라이언트가 초기화되지 않았습니다.")
            return {
                'answer': "저장소 분석 데이터에 접근할 수 없습니다. 서버를 재시작하고 저장소를 다시 분석해주세요.",
                'error': "chroma_client_not_initialized",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        
        # 컬렉션 이름 생성 및 조회 시도
        collection_name = f"repo_{session_id}"
        print(f"[DEBUG] ChromaDB 컬렉션 조회 시도: {collection_name}")
        
        # 컬렉션 존재 확인
        try:
            collections = chroma_client.list_collections()
            collection_names = [col.name for col in collections]
            print(f"[DEBUG] 사용 가능한 컬렉션 목록: {collection_names}")
            
            if collection_name not in collection_names:
                print(f"[ERROR] 컬렉션을 찾을 수 없음: {collection_name}")
                return {
                    'answer': "저장소 분석 데이터를 찾을 수 없습니다. 저장소를 다시 분석해주세요.",
                    'error': "collection_not_found",
                    'modified_code': "",
                    'file_name': "",
                    'has_push_intent': has_push_intent,
                    'token_exists': token_exists,
                    'requires_confirmation': requires_confirmation,
                    'push_intent_message': push_intent_message
                }
        except Exception as e:
            import traceback
            print(f"[ERROR] ChromaDB 컬렉션 목록 조회 실패: {e}")
            traceback.print_exc()
            return {
                'answer': f"저장소 분석 데이터 접근 중 오류가 발생했습니다: {str(e)}",
                'error': "collection_list_error",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        
        # 컬렉션 가져오기
        try:
            collection = chroma_client.get_collection(name=collection_name)
            print(f"[DEBUG] 컬렉션 조회 성공: {collection_name}")
            
            # 컬렉션 내 문서 수 확인
            try:
                collection_count = collection.count()
                print(f"[DEBUG] 컬렉션 내 문서 수: {collection_count}")
                if collection_count == 0:
                    print(f"[WARNING] 컬렉션이 비어 있습니다: {collection_name}")
                    return {
                        'answer': "저장소 분석 데이터가 비어 있습니다. 저장소를 다시 분석해주세요.",
                        'error': "empty_collection",
                        'modified_code': "",
                        'file_name': "",
                        'has_push_intent': has_push_intent,
                        'token_exists': token_exists,
                        'requires_confirmation': requires_confirmation,
                        'push_intent_message': push_intent_message
                    }
            except Exception as e:
                print(f"[WARNING] 컬렉션 문서 수 확인 실패: {e}")
                # 문서 수 확인 실패는 치명적이지 않을 수 있으므로 계속 진행
        except Exception as e:
            import traceback
            print(f"[ERROR] 컬렉션 가져오기 실패: {e}")
            traceback.print_exc()
            return {
                'answer': f"저장소 분석 데이터 접근 중 오류가 발생했습니다: {str(e)}",
                'error': "collection_access_error",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        
        # 유사 코드 청크 검색
        print(f"[DEBUG] 유사 코드 청크 검색 시작 (TOP_K={TOP_K})")
        try:
            results = collection.query(
                query_embeddings=[embedding],
                n_results=TOP_K
            )
            print(f"[DEBUG] 검색 결과 구조: {list(results.keys())}")
        except Exception as e:
            import traceback
            print(f"[ERROR] 유사 코드 청크 검색 실패: {e}")
            traceback.print_exc()
            return {
                'answer': f"코드 검색 중 오류가 발생했습니다: {str(e)}",
                'error': "query_error",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        
        # 검색 결과 유효성 검증
        if not results or 'metadatas' not in results or not results['metadatas'] or not results['metadatas'][0]:
            print(f"[WARNING] 검색 결과가 비어 있습니다")
            return {
                'answer': "질문과 관련된 코드를 찾을 수 없습니다. 다른 질문을 시도해보세요.",
                'error': "no_results",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        
        # 관련 파일 경로 추출
        related_files = set()
        for metadata in results['metadatas'][0]:
            if 'path' in metadata:
                related_files.add(metadata['path'])
            else:
                print(f"[WARNING] 메타데이터에 'path' 키가 없습니다: {metadata}")
        
        if not related_files:
            print("[WARNING] 관련 파일을 찾을 수 없습니다.")
            return {
                'answer': "질문과 관련된 코드 파일을 찾을 수 없습니다. 다른 질문을 시도해보세요.",
                'error': "no_related_files",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        
        print(f"[DEBUG] 관련 파일 경로: {related_files}")
        
        # 유사도 점수 로깅 (있는 경우)
        if 'distances' in results and results['distances'] and results['distances'][0]:
            distances = results['distances'][0]
            print(f"[DEBUG] 검색 유사도 점수: {distances}")
            
            # 파일 경로와 유사도 점수 매핑
            path_scores = []
            for i, metadata in enumerate(results['metadatas'][0]):
                if 'path' in metadata and i < len(distances):
                    path_scores.append((metadata['path'], distances[i]))
            
            if path_scores:
                print(f"[DEBUG] 파일별 유사도 점수: {path_scores}")

    except Exception as e:
        print(f"[ERROR] 코드 청크 검색 오류: {e}")
        return {
            'answer': "코드 검색 중 오류가 발생했습니다. 새로운 레포지토리를 분석해주세요.",
            'error': "search_error",
            'modified_code': "",
            'file_name': "",
            'has_push_intent': has_push_intent,
            'token_exists': token_exists,
            'requires_confirmation': requires_confirmation,
            'push_intent_message': push_intent_message
        }
    
    # 관련 파일들의 전체 내용 로드
    print(f"[DEBUG] 관련 파일 {len(related_files)}개의 전체 내용 로드 시작")
    full_file_contents = []
    failed_files = []
    
    for file_path in related_files:
        print(f"[DEBUG] 파일 로드 시도: {file_path}")
        try:
            # 로컬 저장소 경로 확인
            local_file_path = f"{repo_path}/{file_path}"
            print(f"[DEBUG] 로컬 파일 경로: {local_file_path}")
            
            # 파일 존재 확인
            import os
            if not os.path.exists(local_file_path):
                print(f"[WARNING] 파일이 로컬에 존재하지 않음: {local_file_path}")
                raise FileNotFoundError(f"파일을 찾을 수 없습니다: {local_file_path}")
                
            # 로컬 저장소에서 파일 읽기
            with open(local_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"[DEBUG] 파일 로드 성공: {file_path} (길이: {len(content)} 문자)")
                full_file_contents.append(f"// FILE: {file_path}\n{content}")
        except UnicodeDecodeError as ude:
            print(f"[WARNING] 파일 인코딩 오류 ({file_path}): {ude}")
            try:
                # 다른 인코딩으로 시도
                with open(f"{repo_path}/{file_path}", 'r', encoding='latin-1') as f:
                    content = f.read()
                    print(f"[DEBUG] 파일 latin-1 인코딩으로 로드 성공: {file_path}")
                    full_file_contents.append(f"// FILE: {file_path}\n{content}")
            except Exception as e_inner:
                print(f"[ERROR] 다른 인코딩으로도 파일 읽기 실패 ({file_path}): {e_inner}")
                failed_files.append(file_path)
        except Exception as e:
            import traceback
            print(f"[ERROR] 파일 읽기 오류 ({file_path}): {e}")
            traceback.print_exc()
            
            # 읽기 실패 시 GitHub에서 직접 가져오기 시도
            try:
                print(f"[DEBUG] GitHub에서 파일 가져오기 시도: {file_path}")
                from github_analyzer import GitHubAnalyzer
                
                # 저장소 URL 확인
                repo_url = session_data.get('repo_url')
                if not repo_url:
                    print(f"[ERROR] 저장소 URL이 없습니다.")
                    failed_files.append(file_path)
                    continue
                    
                analyzer = GitHubAnalyzer(repo_url, session_data.get('token'), session_id)
                content = analyzer.fetch_file_content(file_path)
                
                if content:
                    print(f"[DEBUG] GitHub에서 파일 가져오기 성공: {file_path} (길이: {len(content)} 문자)")
                    full_file_contents.append(f"// FILE: {file_path}\n{content}")
                else:
                    print(f"[WARNING] GitHub에서 파일 가져오기 실패 (내용 없음): {file_path}")
                    failed_files.append(file_path)
            except Exception as e2:
                import traceback
                print(f"[ERROR] GitHub에서 파일 가져오기 오류 ({file_path}): {e2}")
                traceback.print_exc()
                failed_files.append(file_path)
    
    # 파일 로드 결과 요약
    print(f"[DEBUG] 총 {len(related_files)}개 파일 중 {len(full_file_contents)}개 로드 성공, {len(failed_files)}개 실패")
    if failed_files:
        print(f"[WARNING] 로드 실패한 파일들: {failed_files}")
        
    # 로드된 파일이 없는 경우 처리
    if not full_file_contents:
        print(f"[ERROR] 파일을 하나도 로드하지 못했습니다.")
        return {
            'answer': "관련 코드 파일을 로드하지 못했습니다. 저장소를 다시 분석해주세요.",
            'error': "file_load_error",
            'modified_code': "",
            'file_name': "",
            'has_push_intent': has_push_intent,
            'token_exists': token_exists,
            'requires_confirmation': requires_confirmation,
            'push_intent_message': push_intent_message
        }
    
    # 청크 검색 결과도 함께 컨텍스트로 사용
    context_chunks = [doc for doc in results['documents'][0]]
    
    # 청크 검색 결과와 파일 전체 내용 합치기
    if full_file_contents:
        context = "\n\n=== 관련 파일 전체 내용 ===\n\n" + "\n\n---\n\n".join(full_file_contents)
        context += "\n\n=== 관련 코드 청크 ===\n\n" + "\n---\n".join(context_chunks)
    else:
        # 파일 전체 내용을 가져오지 못한 경우 청크만 사용
        context = "\n---\n".join(context_chunks)
    
    # 디렉토리 구조 가져오기
    directory_structure = session_data.get('directory_structure')
    
    if directory_structure:
        print(f"[DEBUG] 디렉토리 구조 정보 제공 (길이: {len(directory_structure)} 문자)")
    else:
        print("[DEBUG] 디렉토리 구조 정보가 없습니다.")
        directory_structure = "프로젝트 구조 정보가 없습니다. 파일 내용만 참고하여 응답하겠습니다."
    
    # 프롬프트 생성 및 LLM 호출
    try:
        # 이전 대화 기록 가져오기 (DB에서)
        print(f"[CHAT_HANDLER] 이전 대화 기록 가져오기 시작 - 세션: {session_id}")
        chat_history = db.get_chat_history(session_id)
        
        # 대화 기록을 문자열로 포맷팅
        conversation_history = ""
        if chat_history:
            for chat in chat_history[-6:]:  # 최근 6개 대화만 사용
                role = "사용자" if chat['role'] == 'user' else "AI"
                message_content = chat.get('content') or chat.get('message', '')
                conversation_history += f"[{role}] {message_content}\n\n"
        
        if not conversation_history:
            conversation_history = "이전 대화 없음"
            print(f"[CHAT_HANDLER] 관련 대화 기록이 없습니다.")
        else:
            print(f"[CHAT_HANDLER] 가져온 대화 기록 수: {len(chat_history)} 개")
        
        # 프롬프트 생성 (대화 기록 포함)
        prompt = MODIFY_PROMPT_TEMPLATE.format(
            context=context, 
            request=message,
            directory_structure=directory_structure,
            conversation_history=conversation_history
        )
        print("\n[LLM 프롬프트 - 코드수정]\n" + prompt + "\n")  # 프롬프트 확인용 출력
        print(f"[DEBUG] 코드수정 프롬프트 길이: {len(prompt)} 문자")
        
        # 프롬프트 길이 제한 확인 
        # OpenAI API의 토큰 제한(예: gpt-4o TPM 30000)을 고려하여 프롬프트 크기를 관리합니다.
        # 1 토큰은 대략 4문자에 해당한다고 가정하고, 안전 마진을 적용합니다.
        # 목표: 요청 토큰 < 28000 (약 112,000 문자) 이내가 되도록 관리.

        MAX_PROMPT_CHARS = 95000  # 전체 프롬프트에 대한 안전한 문자 제한 (약 23750 토큰)
        MAX_CONTEXT_ONLY_CHARS = 50000  # 순수 context 변수 (코드) 에 대한 제한 (약 12500 토큰)
        MAX_HISTORY_CHARS = 15000  # 대화 기록에 대한 제한 (약 3750 토큰)

        if len(prompt) > MAX_PROMPT_CHARS:
            print(f"[WARNING] 코드수정 프롬프트가 너무 깁니다 (현재: {len(prompt)}자, 최종 제한: {MAX_PROMPT_CHARS}자). 컨텍스트와 대화 기록을 줄입니다.")

            # 원본 context와 history 복사 (길이 변경 로깅용)
            original_context_for_truncation = str(context)
            original_history_for_truncation = str(conversation_history)

            # 1. context 줄이기
            if len(context) > MAX_CONTEXT_ONLY_CHARS:
                context = context[:MAX_CONTEXT_ONLY_CHARS] + "\n... (코드 컨텍스트가 축소되었습니다) ..."
                print(f"[DEBUG] 코드 컨텍스트 축소: 원본 {len(original_context_for_truncation)}자 -> 현재 {len(context)}자 (제한: {MAX_CONTEXT_ONLY_CHARS}자)")

            # 2. conversation_history 줄이기
            if conversation_history != "이전 대화 없음" and len(conversation_history) > MAX_HISTORY_CHARS:
                conversation_history = conversation_history[:MAX_HISTORY_CHARS] + "\n... (대화 기록이 축소되었습니다) ..."
                print(f"[DEBUG] 대화 기록 축소: 원본 {len(original_history_for_truncation)}자 -> 현재 {len(conversation_history)}자 (제한: {MAX_HISTORY_CHARS}자)")
            
            # 3. 프롬프트 재구성 및 최종 길이 확인
            prompt = MODIFY_PROMPT_TEMPLATE.format(
                context=context,
                request=message,
                directory_structure=directory_structure, # 디렉토리 구조는 보통 크지 않으므로 일단 유지
                conversation_history=conversation_history
            )
            print(f"[DEBUG] 1차 축소 후 코드수정 프롬프트 길이: {len(prompt)} 문자")

            # 그래도 길면, 최후의 수단으로 context를 더 공격적으로 줄임
            if len(prompt) > MAX_PROMPT_CHARS:
                print(f"[WARNING] 추가 축소 후에도 프롬프트가 너무 깁니다 (현재: {len(prompt)}자). 코드 컨텍스트를 더 줄입니다.")
                # 필요한 추가 축소량 계산 (프롬프트 템플릿 자체의 길이도 고려해야 함)
                # MODIFY_PROMPT_TEMPLATE에서 context, request, directory_structure, conversation_history를 제외한 순수 템플릿 문자열 길이 추정
                placeholder_values = {'context':'', 'request':'', 'directory_structure':'', 'conversation_history':''}
                template_base_len = len(MODIFY_PROMPT_TEMPLATE.format(**placeholder_values))
                
                # 현재 주요 변수들의 길이
                len_req = len(message)
                len_dir = len(directory_structure)
                len_hist = len(conversation_history if conversation_history != "이전 대화 없음" else "")
                
                # context에 할당 가능한 최대 길이
                allowed_len_for_context = MAX_PROMPT_CHARS - (template_base_len + len_req + len_dir + len_hist)
                
                # context가 할당 가능한 길이를 초과하는 경우, 해당 길이로 자름 (최소 100자 보장)
                if len(context) > allowed_len_for_context and allowed_len_for_context > 100:
                    context = context[:allowed_len_for_context] + "\n... (코드 컨텍스트가 추가로 축소되었습니다) ..."
                    print(f"[DEBUG] 코드 컨텍스트 추가 축소: {len(context)}자 (할당 가능량: {allowed_len_for_context}자)")
                elif len(context) > 100: # 할당 가능량이 너무 작으면 최소한으로 줄임
                    context = context[:100] + "\n... (코드 컨텍스트가 최소한으로 축소되었습니다) ..."
                    print(f"[DEBUG] 코드 컨텍스트 최소 축소: {len(context)}자")
                else: # context가 이미 매우 짧은 경우
                    print(f"[DEBUG] 코드 컨텍스트가 이미 매우 짧아 추가 축소하지 않음: {len(context)}자")

                prompt = MODIFY_PROMPT_TEMPLATE.format(
                    context=context,
                    request=message,
                    directory_structure=directory_structure,
                    conversation_history=conversation_history
                )
                print(f"[DEBUG] 최후 수단 적용 후 프롬프트 길이: {len(prompt)} 문자")
            
            # 최종적으로 프롬프트가 여전히 너무 길면 경고만 남김 (API 호출은 진행)
            if len(prompt) > MAX_PROMPT_CHARS:
                print(f"[CRITICAL WARNING] 모든 축소 노력에도 불구하고 프롬프트가 여전히 설정된 제한({MAX_PROMPT_CHARS}자)을 초과합니다: {len(prompt)}자. API 오류 가능성이 있습니다.")
        
        # LLM 호출
        print(f"[DEBUG] 코드수정용 OpenAI API 호출 시작 (model=gpt-4o, temperature=0.2, max_tokens=4096)")
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": SYSTEM_PROMPT_MODIFY},
                      {"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=4096
        )
        
        # 응답 처리
        if not response or not response.choices or not response.choices[0].message:
            print(f"[ERROR] 코드수정 LLM 응답이 비어 있습니다: {response}")
            return {
                'answer': "코드 수정 중 오류가 발생했습니다. 다시 시도해주세요.",
                'error': "empty_response",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        
        llm_code = response.choices[0].message.content.strip()
        print(f"[DEBUG] 코드수정 LLM 응답 성공 (길이: {len(llm_code)} 문자)")
        
        # 대화 기록 저장 (DB에만)
        try:
            print(f"[CHAT_HANDLER] 코드 수정 대화 기록 저장 시작 - 세션: {session_id}")
            summary_answer = f"코드 수정 요청: {message}\n\n수정 작업 완료"
            
            # 컨텍스트 정보가 포함된 사용자 메시지 처리 (파일명만 저장)
            user_message_with_context = message
            
            # 메시지에서 컨텍스트 정보 추출하여 파일명만 저장
            if '[선택된 파일 컨텍스트]' in message:
                # 메시지를 질문 부분과 컨텍스트 부분으로 분리
                parts = message.split('\n\n[선택된 파일 컨텍스트]\n')
                if len(parts) > 1:
                    user_message_with_context = parts[0]  # 질문 부분만
                    
                    # 컨텍스트에서 파일명만 추출
                    context_part = parts[1]
                    context_files = []
                    
                    # "--- 파일명 (브랜치: 브랜치명) ---" 패턴에서 파일명 추출
                    file_patterns = re.findall(r'--- (.+?) \(브랜치: .+?\) ---', context_part)
                    for file_path in file_patterns:
                        # 파일명에서 경로 부분만 추출 (디렉토리 구조 포함)
                        clean_file_name = file_path.strip()
                        if clean_file_name not in context_files:
                            context_files.append(clean_file_name)
                    
                    # 파일명만 저장 (내용은 저장하지 않음)
                    if context_files:
                        user_message_with_context += f"\n\n[선택된 파일: {', '.join(context_files)}]"
            
            # 추가 보안: 메시지에서 파일 내용이 포함된 경우 제거
            lines = user_message_with_context.split('\n')
            filtered_lines = []
            skip_content = False
            
            for line in lines:
                # 파일 내용 시작 패턴 감지
                if line.strip().startswith('---') and '브랜치:' in line:
                    skip_content = True
                    continue
                elif skip_content and (line.strip() == '' or line.startswith('---')):
                    # 파일 내용 끝 감지
                    if line.startswith('---') and '브랜치:' in line:
                        continue
                    skip_content = False
                    if line.strip() == '':
                        continue
                
                # 파일 내용이 아닌 경우만 포함
                if not skip_content:
                    filtered_lines.append(line)
            
            user_message_with_context = '\n'.join(filtered_lines).strip()
            
            # DB에 채팅 기록 저장
            db.add_chat_history(session_id, 'user', user_message_with_context)
            db.add_chat_history(session_id, 'assistant', summary_answer)
            print(f"[CHAT_HANDLER] 코드 수정 대화 기록 저장 성공: session_id={session_id}")
        except Exception as e:
            import traceback
            print(f"[CHAT_HANDLER] 코드 수정 대화 기록 저장 실패: {str(e)}")
            traceback.print_exc()
        
        # 응답이 비어있는지 확인
        if not llm_code:
            print("[WARNING] 코드수정 LLM이 비어있는 응답을 리턴했습니다.")
            return {
                'answer': "코드 수정을 생성하지 못했습니다. 다른 수정 요청을 시도해주세요.",
                'error': "empty_code",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        
        # 파일명과 코드 분리
        file_name, code = parse_llm_code_response(llm_code)
        print(f"[DEBUG] 파싱된 파일명: '{file_name or '(none)'}', 코드 길이: {len(code)} 문자")
        
        # 코드가 비어있는지 확인
        if not code:
            print("[WARNING] 파싱된 코드가 비어 있습니다.")
            return {
                'answer': "코드 수정을 생성하지 못했습니다. 다른 수정 요청을 시도해주세요.",
                'error': "empty_parsed_code",
                'modified_code': "",
                'file_name': "",
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message
            }
        
        # 성공적인 응답 반환
        return {'modified_code': code, 'file_name': file_name or '',
                'has_push_intent': has_push_intent,
                'token_exists': token_exists,
                'requires_confirmation': requires_confirmation,
                'push_intent_message': push_intent_message}
    except Exception as e:
        import traceback
        print(f"[ERROR] 코드수정 LLM 호출 오류: {e}")
        traceback.print_exc()
        return {
            'answer': f"코드 수정 중 오류가 발생했습니다: {str(e)}",
            'error': "llm_error",
            'modified_code': "",
            'file_name': "",
            'has_push_intent': has_push_intent,
            'token_exists': token_exists,
            'requires_confirmation': requires_confirmation,
            'push_intent_message': push_intent_message
        }

def detect_github_push_intent(message):
    """사용자 메시지에서 GitHub 푸시 의도를 감지 (정규식 + LLM 보조)"""
    import re
    import openai
    print(f"[DEBUG] GitHub 푸시 의도 감지 시작: '{message}'")
    
    # 다양한 자연어 패턴을 포괄하는 정규식 패턴
    push_keywords = [
        r'깃허브(에|로)?\s*(적용|반영|올려|업로드|푸시|push|commit|커밋|업데이트|동기화|sync|적용시켜|반영해|올려줘|업로드해|push해|commit해|커밋해|업데이트해|동기화해|pr|pull request|풀리퀘|풀 리퀘|풀리퀘스트|풀 리퀘스트)',
        r'github(에|로)?\s*(적용|반영|올려|업로드|푸시|push|commit|커밋|업데이트|동기화|sync|pr|pull request)',
        r'깃(에|로)?\s*(적용|반영|올려|업로드|푸시|push|commit|커밋|업데이트|동기화|sync)',
        r'적용(해|시켜|해줘|시켜줘|해주세요|시켜주세요)',
        r'반영(해|시켜|해줘|시켜줘|해주세요|시켜주세요)',
        r'올려(줘|주세요|달라|달라고|달라요|달라구|달라구요|달라줘|달라주세요)',
        r'업로드(해|시켜|해줘|시켜줘|해주세요|시켜주세요)',
        r'푸시(해|시켜|해줘|시켜줘|해주세요|시켜주세요)',
        r'commit(해|시켜|해줘|시켜줘|해주세요|시켜주세요)',
        r'커밋(해|시켜|해줘|시켜줘|해주세요|시켜주세요)',
        r'업데이트(해|시켜|해줘|시켜줘|해주세요|시켜주세요)',
        r'동기화(해|시켜|해줘|시켜줘|해주세요|시켜주세요)',
        r'pr(생성|만들|올려|해|해주세요|해줘|시켜|시켜줘|시켜주세요)',
        r'풀\s*리퀘(스트)?',
        r'pull\s*request',
        r'push',
        r'commit',
        r'pr',
        r'pull request',
    ]
    
    message_lower = message.lower()
    for pattern in push_keywords:
        if re.search(pattern, message_lower):
            print(f"[INFO] GitHub 푸시 의도 감지 성공: 패턴 '{pattern}' 매칭")
            return True
    
    # LLM 보조 검사 (정규식에 안 걸릴 때만)
    try:
        prompt = (
            "다음 사용자의 요청이 '코드를 깃허브에 반영/적용/푸시/업로드/커밋/PR 생성' 등 "
            "깃허브 원격 저장소에 실제로 변경사항을 적용하려는 의도인지 '네/아니오'로만 답해줘.\n"
            f"요청: {message}\n"
            "답변:"
        )
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2
        )
        answer = response.choices[0].message.content.strip()
        print(f"[DEBUG] LLM 의도 감지 답변: {answer}")
        if answer.startswith("네"):
            return True
    except Exception as e:
        print(f"[WARNING] LLM 의도 감지 실패: {e}")
    print("[INFO] GitHub 푸시 의도 감지 실패: 정규식/LLM 모두 불일치")
    return False
    
    # 대소문자 무시하고 검색
    message_lower = message.lower()
    
    print(f"[DEBUG] 소문자 변환된 메시지: '{message_lower}'")
    
    # 패턴 매칭
    for pattern in push_keywords:
        if re.search(pattern, message_lower):
            print(f"[INFO] GitHub 푸시 의도 감지 성공: 패턴 '{pattern}' 매칭")
            return True
    
    print("[INFO] GitHub 푸시 의도 감지 실패: 일치하는 패턴 없음")
    return False

def apply_changes(session_id, file_name, new_content, push_to_github=False, commit_msg=None):
    """코드 변경사항을 저장소에 적용하는 함수"""
    print(f"[INFO] 코드 변경사항 적용 시작 (session_id: {session_id}, file_name: {file_name}, push_to_github: {push_to_github})")
    
    # GitHub 푸시 유무에 따른 로그 추가
    if push_to_github:
        print(f"[INFO] GitHub 푸시 요청됨. 커밋 메시지: '{commit_msg or 'AI 코드 수정'}'")
    else:
        print("[INFO] 로컬 저장소에만 적용 (푸시 없음)")
    
    # 입력값 검증
    if not session_id:
        print("[ERROR] 세션 ID가 제공되지 않았습니다.")
        return {'result': '에러: 세션 ID가 제공되지 않았습니다.', 'success': False}
        
    if not file_name:
        print("[ERROR] 파일명이 제공되지 않았습니다.")
        return {'result': '에러: 파일명이 제공되지 않았습니다.', 'success': False}
        
    if not new_content:
        print("[ERROR] 새 코드 내용이 비어 있습니다.")
        return {'result': '에러: 적용할 코드 내용이 비어 있습니다.', 'success': False}
    
    # 저장소 경로 확인
    repo_path = f"./repos/{session_id}"
    print(f"[DEBUG] 저장소 경로: {repo_path}")
    
    import os
    if not os.path.exists(repo_path):
        print(f"[ERROR] 저장소 경로가 존재하지 않습니다: {repo_path}")
        return {'result': f'에러: 저장소 경로가 존재하지 않습니다: {repo_path}', 'success': False}
    
    # DB에서 세션 데이터 조회하여 토큰 가져오기
    session_data = db.get_session_data_from_db(session_id)
    token = session_data.get('token') if session_data else None
    
    # GitHub 푸시 여부 확인
    can_push = push_to_github and token
    if push_to_github and not token:
        print("[WARNING] GitHub 토큰이 없어 푸시를 수행할 수 없습니다.")
    
    # 코드 변경 적용
    if not commit_msg:
        commit_msg = "AI 코드 자동 수정"
    
    try:
        print(f"[DEBUG] create_branch_and_commit 호출 시작 (branch: test, file: {file_name}, push: {can_push})")
        result = create_branch_and_commit(repo_path, "test", file_name, new_content, commit_msg, token if can_push else None)
        print(f"[DEBUG] 코드 변경사항 적용 성공")
        
        response = {
            'result': '코드가 성공적으로 적용되었습니다.',
            'success': True,
            'file_name': file_name,
            'branch': 'test',
            'pushed_to_github': result.get('pushed', False)
        }
        
        if result.get('pushed', False):
            response['result'] = 'GitHub 저장소에 코드가 성공적으로 푸시되었습니다.'
        else:
            if push_to_github and not token:
                response['result'] = '코드가 로컬에 적용되었지만, GitHub 토큰이 없어 푸시되지 않았습니다. GitHub 푸시 기능을 사용하려면 토큰을 입력해주세요.'
            elif push_to_github:
                response['result'] = '코드가 로컬에 적용되었지만, GitHub 푸시 중 문제가 발생했습니다.'
        
        return response
    except Exception as e:
        import traceback
        print(f"[ERROR] 코드 변경사항 적용 실패: {e}")
        traceback.print_exc()
        return {'result': f'에러: {str(e)}', 'success': False}

def extract_scope_from_question(question: str):
    """
    질문에서 파일명, 함수명, 클래스명, 디렉토리명 등 범위 키워드 추출
    """
    file_match = re.findall(r'([\w_\-/]+\.\w+)', question)
    func_match = re.findall(r'(\w+) ?함수', question)
    class_match = re.findall(r'(\w+) ?클래스', question)
    dir_match = re.findall(r'([\w_\-/]+)/', question)
    return {
        'file': file_match,
        'function': func_match,
        'class': class_match,
        'directory': dir_match
    } 