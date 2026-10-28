import os
import logging
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from app.rag.embeddings import get_embeddings
from app.config import settings

logger = logging.getLogger(__name__)

_vector_store = None

def get_vector_store() -> Chroma:
    """
    Initializes and caches the LangChain Chroma vector store.
    """
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    embeddings = get_embeddings()
    
    # Ensure persistence directory exists
    os.makedirs(settings.CHROMA_DB_DIR, exist_ok=True)
    
    _vector_store = Chroma(
        collection_name="youtube_chunks",
        embedding_function=embeddings,
        persist_directory=settings.CHROMA_DB_DIR
    )
    
    return _vector_store

def delete_video_vectors(video_id: str) -> None:
    vector_store = get_vector_store()
    try:
        vector_store.delete(where={"video_id": video_id})
        logger.info("Deleted ChromaDB vectors for video_id: %s", video_id)
    except Exception as exc:
        logger.error(
            "Failed to delete ChromaDB vectors for video_id %s",
            video_id,
            exc_info=True,
        )
        raise RuntimeError(
            f"Failed to clean existing vectors for video {video_id}"
        ) from exc

def add_transcript_chunks(video_id: str, channel_id: str, title: str, upload_date: str, chunks: list) -> list:
    """
    Adds transcript chunks to ChromaDB and returns a list of assigned chroma_ids.
    chunks: list of dicts with keys: text, start_time, duration
    """
    db = get_vector_store()
    
    documents = []
    ids = []
    
    for i, chunk in enumerate(chunks):
        # Generate clean ID
        chroma_id = f"{video_id}_chunk_{i}"
        
        doc = Document(
            page_content=chunk["text"],
            metadata={
                "video_id": video_id,
                "channel_id": channel_id,
                "title": title,
                "upload_date": upload_date,
                "start_time": float(chunk["start_time"]),
                "duration": float(chunk["duration"])
            }
        )
        documents.append(doc)
        ids.append(chroma_id)

    db.add_documents(documents=documents, ids=ids)
    return ids
