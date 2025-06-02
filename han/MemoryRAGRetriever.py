from langchain.chains import RetrievalQA
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.prompts import PromptTemplate
from langchain.vectorstores.chroma import Chroma
from langchain.chat_models import ChatOpenAI
from langchain.memory import ChatMessageHistory
from langchain_core.documents import Document
from langchain.embeddings import OpenAIEmbeddings
from langchain.schema.runnable import Runnable

class MemoryRAGRetriever:
    def __init__(self, collection: Chroma):
        self.vectorstore = collection
        self.retriever = self.vectorstore.as_retriever()
        self.llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.0)

        self.retriever_with_memory = create_history_aware_retriever(
            llm=self.llm,
            retriever=self.retriever,
            prompt=PromptTemplate.from_template("""
다음은 사용자와의 최근 대화 일부입니다:
{chat_history}

사용자의 질문: {input}

위 질문에 가장 관련된 내용을 찾기 위한 쿼리를 만들어주세요.
""")
        )

        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            retriever=self.retriever_with_memory,
            return_source_documents=True
        )
        self.chat_history = ChatMessageHistory()

    def query(self, user_query: str) -> str:
        # 최근 3쌍만 유지 (user + ai = 6개)
        recent_history = self.chat_history.messages[-6:]
        
        result = self.qa_chain.invoke({
            "input": user_query,
            "chat_history": recent_history
        })

        self.chat_history.add_user_message(user_query)
        self.chat_history.add_ai_message(result["result"])
        return result["result"]
