from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from sklearn.metrics.pairwise import cosine_similarity
from openai import OpenAI
import gc 
import shutil
import os
import hashlib
import time




llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.3,
    api_key=os.getenv("OPENAI_API_KEY")
)
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


DOCUMENT_DB_PATH = "/Users/cpldxx/GitHub/3rd_project/han/chroma_db"
MEMORY_DB_PATH = "/Users/cpldxx/GitHub/3rd_project/sangwon/chroma_db"


def compute_hash(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()


# chroma db 리셋
def reset_chroma_db():
    if os.path.exists(MEMORY_DB_PATH):
        shutil.rmtree(MEMORY_DB_PATH, ignore_errors=True)
    while os.path.exists(MEMORY_DB_PATH):
        time.sleep(0.1)
    gc.collect()




def update_history(query: str, answer: str, chroma_db, similarity_threshold: float = 0.91):
    query_hash = compute_hash(query) #질문의 해시 생성
    query_vector = embedding_model.embed_query(query) #질문 문장 임베딩

    #유사 질문 검색
    try:
        similar_docs = chroma_db.similarity_search(query, k=5) #similarity search 질문 내용 기준으로 유사 질문 삭제
        for doc in similar_docs:
            if doc.metadata.get("type") == "question":
                doc_vector = embedding_model.embed_query(doc.page_content)
                similarity = cosine_similarity([query_vector], [doc_vector])[0][0]
                # 만약 0.91 이상 넘을시 제거
                if similarity > similarity_threshold:
                    doc_id = doc.metadata.get("question_hash")
                    if doc_id:
                        chroma_db._collection.delete(ids=[doc_id])
    except Exception as e:
        print(f"ERROR: {e}")

    # 새 질문+답변 저장
    try:
        doc = Document(
            page_content=f"Q: {query}\nA: {answer}",
            metadata={
                "type": "question",
                "question_hash": query_hash
            }
        )
        # 저장
        chroma_db.add_documents([doc], ids=[query_hash])
        chroma_db.persist()
    except Exception as e:
        print(f"ERROR: {e}")

#RAG 코드--------------------------------------------------------------------------------------------------------
from langchain.text_splitter import RecursiveCharacterTextSplitter
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
def make_chroma_db(documents, persist_path: str) -> Chroma:
    # Chunking
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    docs = splitter.split_documents(documents)

    # 벡터 저장소 만들기
    db = Chroma.from_documents(
        docs,
        embedding_model,
        persist_directory=persist_path
    )
    return db


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔍 GPT를 사용해 요약 생성
def summarize_with_gpt(content: str, file_path: str, max_chars: int = 1500) -> str:
    prompt = f"""
    다음은 '{file_path}'라는 파일의 코드입니다. 
    이 파일의 목적이 무엇인지, 어떤 기능이 있고 어떤 문제를 해결하는지 간단히 요약해 주세요. 
    \n\n```python\n{content[:max_chars]}\n```\n\n요약:"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # 또는 gpt-3.5-turbo
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ GPT 요약 실패 ({file_path}): {e}")
        return "요약 실패"

import sys
sys.path.append(r"/Users/cpldxx/GitHub/3rd_project")  # chahae 폴더의 상위 폴더

from chahae.github_repo_viewer import main
from dotenv import load_dotenv
import os

load_dotenv()
documents = main(os.environ.get("GITHUB_TOKEN"))


#--------------------------------------------------------------------------------------------------------
# Chroma DB 로딩
document_db = make_chroma_db(documents, persist_path=DOCUMENT_DB_PATH)
memory_db = Chroma(persist_directory=MEMORY_DB_PATH, embedding_function=embedding_model)
# context 생성
def build_context(query: str, document_db, memory_db):
    retriever = document_db.as_retriever(search_kwargs={"k":5})
    relevant_docs = retriever.get_relevant_documents(query)
    document_context = "\n\n".join([doc.page_content for doc in relevant_docs])
    
    memory_context = "\n\n".join([doc.page_content for doc in memory_db.similarity_search(query, k=3)]) or "이전 대화 없음"
    return f"-이전 대화:\n{memory_context}\n\n-관련 코드(필수적으로 참고해야 할 코드):\n{document_context}"

# 최종 응답 생성
def generate_combined_answer(query: str, document_db, memory_db, llm) -> str:
    context = build_context(query, document_db, memory_db)


    prompt = (
        "너는 전문적인 GitHub 코드 분석 어시스턴트야. 사용자의 질문에 대해 주어진 코드 문서들을 분석해서, 작동 구조, 핵심 역할, 구성 요소, 흐름, 예외 처리까지 매우 정교하고 깊이 있게 설명해줘야 해.\n"

        "형식은 아래 예시처럼 작성해. 반드시 구조적으로, 포인트별로 정리해서 설명해. 설명은 최대한 길고 상세하게 해줘.\n\n"
        
        "### 예시 1\n"
        "질문: 이 모델 클래스가 무슨 역할을 하고 내부 구조는 어떻게 되나요?\n\n"
        "코드 컨텍스트 (요약):\n"
        "```python\n"
        "# 이미지 캡셔닝을 위한 모델 정의\n"
        "class ImageCaptionModel(nn.Module):\n"
        "    def __init__(self, encoder, decoder):\n"
        "        ...\n"
        "    def forward(self, images, captions):\n"
        "        ...\n"
        "```\n\n"
        "답변:\n"
        "1. 코드 개요: 이미지에서 특징을 추출한 후 캡션을 생성하는 딥러닝 모델입니다.\n"
        "2. 구성 요소: CNN 기반 encoder + RNN 기반 decoder 구조로 되어 있습니다.\n"
        "3. 작동 방식: 이미지를 입력받아 encoder로 특성을 추출하고, decoder가 이를 바탕으로 문장을 만듭니다.\n"
        "4. 주의점: encoder/decoder는 외부에서 주입되며, 학습 시 별도로 정의되어야 합니다.\n"
        "5. 요약: 이미지 설명 텍스트를 생성하는 end-to-end 네트워크입니다.\n\n"
        
        "### 예시 2\n"
        " 질문: 이 인코더는 어떤 방식으로 이미지 임베딩을 만들어요?\n\n"
        " 코드 컨텍스트 (요약):\n"
        "```python\n"
        "class EncoderCNN(nn.Module):\n"
        "    def __init__(self, embed_size):\n"
        "        ...\n"
        "    def forward(self, images):\n"
        "        ...\n"
        "```\n\n"
        " 답변:\n"
        "1.  코드 개요: 이미지 특징을 추출하고 임베딩 벡터로 변환하는 인코더입니다.\n"
        "2.  구성 요소: 사전학습된 ResNet-50 + 선형 변환 레이어입니다.\n"
        "3.  작동 방식: ResNet으로 특징 추출 → 임베딩 차원으로 선형 변환 → 출력 반환\n"
        "4.  주의점: ResNet은 `requires_grad=False`로 고정되어 학습되지 않습니다.\n"
        "5.  요약: 고정된 CNN 백본을 통해 이미지 특징을 임베딩으로 변환하는 모듈입니다.\n\n"

        "------------------------------\n\n"
        "아래 내용을 포함해서 **최대한 자세히**, 코드 구조와 작동 방식, 구성 요소의 역할, 작동 흐름, 예외 상황 등도 함께 설명해줘."
        f" 질문: {query}\n\n"
        f" 코드 컨텍스트:\n{context}\n\n"
        f" 답변:"
    )

    answer = llm.invoke(prompt).content
    update_history(query, answer, memory_db)
    return answer

if __name__ == "__main__":
    print("LLM 시작 (종료하려면 'exit' 입력)\n")

    while True:
        query = input("질문을 입력하세요: ")
        
        if query.lower() in ("exit", "quit"):
            print("종료합니다.")
            break

        elif query.lower() in ("delete", "restart"):
            print("데이터베이스 초기화 중")
            reset_chroma_db()
            print("데이터베이스 삭제 완료")
            print("종료합니다.")
            break
        
        try:
            answer = generate_combined_answer(query, document_db, memory_db, llm)
            print("\n최종 답변:\n", answer)
            print(f"memory_db: {memory_db._collection.count()}")
            print(f"document_db: {document_db._collection.count()}")      
        except Exception as e:
            print("[오류 발생]", e)
        
        





