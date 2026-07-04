from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from core.security import get_current_user
from models.schemas import User
from domains.ai.knowledge_base import get_knowledge_base
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai/knowledge", tags=["AI Knowledge Base"])

@router.get("")
async def list_documents(current_user: User = Depends(get_current_user)):
    """List all documents currently in the knowledge base"""
    try:
        kb = get_knowledge_base()
        if not kb.enabled:
            raise HTTPException(status_code=503, detail="Knowledge Base (ChromaDB) is not enabled.")
        docs = await kb.get_documents()
        return {"documents": docs}
    except Exception as e:
        logger.error(f"Error listing KB documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to list documents")

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload a new document (PDF or text) to the knowledge base"""
    try:
        kb = get_knowledge_base()
        if not kb.enabled:
            raise HTTPException(status_code=503, detail="Knowledge Base (ChromaDB) is not enabled.")
            
        content = ""
        doc_type = "unknown"
        
        if file.filename.endswith(".pdf"):
            import pypdf
            pdf = pypdf.PdfReader(file.file)
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    content += text + "\n"
            doc_type = "pdf"
        elif file.filename.endswith(".txt") or file.filename.endswith(".md") or file.filename.endswith(".csv"):
            content = (await file.read()).decode("utf-8")
            doc_type = "text"
        else:
            raise HTTPException(status_code=400, detail="Only PDF and Text files are supported.")
            
        if not content.strip():
            raise HTTPException(status_code=400, detail="File is empty or text could not be extracted.")
            
        chunks_added = await kb.add_document(content=content, source_name=file.filename, doc_type=doc_type)
        return {"message": "Document processed successfully", "chunks_added": chunks_added, "source": file.filename}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading KB document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

@router.delete("/{source_name}")
async def delete_document(source_name: str, current_user: User = Depends(get_current_user)):
    """Delete a document from the knowledge base"""
    try:
        kb = get_knowledge_base()
        if not kb.enabled:
            raise HTTPException(status_code=503, detail="Knowledge Base (ChromaDB) is not enabled.")
            
        success = await kb.delete_document(source_name)
        if success:
            return {"message": f"Document {source_name} deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete document")
    except Exception as e:
        logger.error(f"Error deleting KB document: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document")
