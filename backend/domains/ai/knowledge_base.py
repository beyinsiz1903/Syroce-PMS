import os
import logging
from typing import List, Dict, Any

from pydantic import BaseModel

try:
    import chromadb
    from chromadb.config import Settings
    from langchain_openai import OpenAIEmbeddings
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

logger = logging.getLogger(__name__)

class KnowledgeBaseService:
    def __init__(self):
        self.enabled = False
        if not _CHROMA_AVAILABLE:
            logger.warning("ChromaDB/Langchain not installed. Knowledge base disabled.")
            return
            
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set. Knowledge base disabled.")
            return

        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=api_key)
        
        # Use persistent storage for Chroma in backend directory
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.chroma_db"))
        os.makedirs(db_path, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=db_path)
        
        # We define an embedding function wrapper for Chroma
        class CustomEmbeddingFunction:
            def __init__(self, langchain_embeddings):
                self.embeddings = langchain_embeddings
            def __call__(self, input: List[str]) -> List[List[float]]:
                return self.embeddings.embed_documents(input)
                
        self.collection = self.client.get_or_create_collection(
            name="hotel_knowledge",
            embedding_function=CustomEmbeddingFunction(self.embeddings)
        )
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        self.enabled = True

    async def add_document(self, content: str, source_name: str, doc_type: str = "text") -> int:
        """
        Chunks the document and adds it to the vector database.
        Returns the number of chunks added.
        """
        if not self.enabled:
            return 0
            
        docs = [Document(page_content=content, metadata={"source": source_name, "type": doc_type})]
        chunks = self.text_splitter.split_documents(docs)
        
        if not chunks:
            return 0

        # Create unique IDs for chunks
        import uuid
        ids = [str(uuid.uuid4()) for _ in chunks]
        texts = [chunk.page_content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]

        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas
        )
        
        return len(chunks)
        
    async def get_documents(self) -> List[Dict[str, Any]]:
        """
        Return a summary of all unique documents currently stored.
        """
        if not self.enabled:
            return []
            
        result = self.collection.get(include=["metadatas"])
        metadatas = result.get("metadatas", [])
        
        # deduplicate by source
        docs_by_source = {}
        for m in metadatas:
            src = m.get("source", "unknown")
            if src not in docs_by_source:
                docs_by_source[src] = {"source": src, "type": m.get("type", "unknown"), "chunks": 0}
            docs_by_source[src]["chunks"] += 1
            
        return list(docs_by_source.values())

    async def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Search the vector DB for relevant chunks.
        """
        if not self.enabled:
            return []
            
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        matches = []
        if results and results.get("documents") and len(results["documents"]) > 0:
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            dists = results["distances"][0]
            
            for doc, meta, dist in zip(docs, metas, dists):
                matches.append({
                    "content": doc,
                    "metadata": meta,
                    "distance": dist
                })
                
        return matches

    async def delete_document(self, source_name: str) -> bool:
        if not self.enabled:
            return False
            
        self.collection.delete(where={"source": source_name})
        return True

# Singleton
_kb_service_instance = None

def get_knowledge_base():
    global _kb_service_instance
    if _kb_service_instance is None:
        _kb_service_instance = KnowledgeBaseService()
    return _kb_service_instance
