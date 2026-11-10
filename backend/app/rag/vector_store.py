import os
import logging
from typing import List, Optional, Dict, Any
from langchain_core.documents import Document
from app.rag.embeddings import get_embeddings
from app.config import settings
from app.database.db import engine, SessionLocal
from app.database.models import TranscriptChunk, Video

logger = logging.getLogger(__name__)

_vector_store = None


class PGVectorStore:
    """
    Native PostgreSQL + pgvector vector store implementation.
    Operates directly against the transcript_chunks table, eliminating dual-store drift.
    """
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory
        self._embeddings = None

    @property
    def embeddings(self):
        if self._embeddings is None:
            self._embeddings = get_embeddings()
        return self._embeddings

    def similarity_search(
        self, 
        query: str, 
        k: int = 8, 
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Document]:
        """
        Calculates cosine distance against transcript_chunks using pgvector <=> operator,
        with optional relational filtering (e.g. channel_id, video_id).
        """
        query_vector = self.embeddings.embed_query(query)
        session = self.session_factory()
        try:
            q = session.query(
                TranscriptChunk,
                Video.title,
                Video.upload_date,
                Video.channel_id
            ).join(Video, TranscriptChunk.video_id == Video.video_id)

            if filter:
                if "channel_id" in filter and filter["channel_id"]:
                    q = q.filter(Video.channel_id == filter["channel_id"])
                if "video_id" in filter and filter["video_id"]:
                    q = q.filter(TranscriptChunk.video_id == filter["video_id"])

            q = q.filter(TranscriptChunk.embedding.isnot(None))

            if engine.dialect.name == "postgresql":
                q = q.order_by(TranscriptChunk.embedding.cosine_distance(query_vector))
                records = q.limit(k).all()
            else:
                # In-memory cosine similarity fallback for SQLite/offline testing
                records_all = q.all()
                import numpy as np
                qv = np.array(query_vector, dtype=np.float32)
                norm_q = np.linalg.norm(qv)
                scored = []
                for chunk, title, upload_date, chan_id in records_all:
                    if chunk.embedding is not None:
                        cv = np.array(chunk.embedding, dtype=np.float32)
                        norm_c = np.linalg.norm(cv)
                        sim = float(np.dot(qv, cv) / (norm_q * norm_c)) if (norm_q > 0 and norm_c > 0) else 0.0
                        scored.append(((chunk, title, upload_date, chan_id), sim))
                scored.sort(key=lambda x: x[1], reverse=True)
                records = [item[0] for item in scored[:k]]

            documents = []
            for chunk, title, upload_date, chan_id in records:
                upload_str = upload_date.isoformat() if upload_date else ""
                documents.append(
                    Document(
                        page_content=chunk.text,
                        metadata={
                            "video_id": chunk.video_id,
                            "channel_id": chan_id,
                            "title": title or "",
                            "start_time": float(chunk.start_time),
                            "duration": float(chunk.duration),
                            "upload_date": upload_str
                        }
                    )
                )
            return documents
        except Exception as exc:
            logger.error("Vector similarity search encountered an error: %s", exc)
            return []
        finally:
            session.close()

    def delete(self, where: Dict[str, Any]) -> None:
        """
        Deletes vector records for the specified condition.
        """
        video_id = where.get("video_id")
        if not video_id:
            return
        session = self.session_factory()
        try:
            session.query(TranscriptChunk).filter(TranscriptChunk.video_id == video_id).delete()
            session.commit()
            logger.info("Deleted pgvector records for video_id: %s", video_id)
        except Exception as exc:
            session.rollback()
            logger.error("Failed to delete pgvector records for video_id %s: %s", video_id, exc)
            raise exc
        finally:
            session.close()


def get_vector_store():
    """
    Initializes and caches the active vector store (PGVectorStore by default).
    """
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    if getattr(settings, "VECTOR_STORE", "pgvector").lower() == "chroma":
        from langchain_community.vectorstores import Chroma
        os.makedirs(settings.CHROMA_DB_DIR, exist_ok=True)
        _vector_store = Chroma(
            collection_name="youtube_chunks",
            embedding_function=get_embeddings(),
            persist_directory=settings.CHROMA_DB_DIR
        )
    else:
        _vector_store = PGVectorStore()

    return _vector_store


def delete_video_vectors(video_id: str) -> None:
    vector_store = get_vector_store()
    try:
        vector_store.delete(where={"video_id": video_id})
        logger.info("Deleted vectors for video_id: %s", video_id)
    except Exception as exc:
        logger.error(
            "Failed to delete vectors for video_id %s",
            video_id,
            exc_info=True,
        )
        raise RuntimeError(
            f"Failed to clean existing vectors for video {video_id}"
        ) from exc


def add_transcript_chunks(video_id: str, channel_id: str, title: str, upload_date: str, chunks: list) -> list:
    """
    Computes dense vector embeddings for chunks and assigns clean chunk IDs.
    Attaches computed embeddings directly into chunk dicts: chunk['embedding'] = vector.
    Returns list of assigned chunk IDs.
    """
    texts = [c["text"] for c in chunks]
    embeddings_model = get_embeddings()
    vectors = embeddings_model.embed_documents(texts) if texts else []

    ids = []
    for i, chunk in enumerate(chunks):
        chunk_id = f"{video_id}_chunk_{i}"
        chunk["embedding"] = vectors[i] if i < len(vectors) else None
        ids.append(chunk_id)

    # Optional Chroma sync if Chroma is configured
    if getattr(settings, "VECTOR_STORE", "pgvector").lower() == "chroma":
        try:
            from langchain_community.vectorstores import Chroma
            os.makedirs(settings.CHROMA_DB_DIR, exist_ok=True)
            chroma = Chroma(
                collection_name="youtube_chunks",
                embedding_function=embeddings_model,
                persist_directory=settings.CHROMA_DB_DIR
            )
            documents = []
            for i, chunk in enumerate(chunks):
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
            chroma.add_documents(documents=documents, ids=ids)
        except Exception as e:
            logger.warning("Optional Chroma sync skipped: %s", e)

    return ids
