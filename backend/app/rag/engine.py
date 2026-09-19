import logging
import json
import re
from typing import List, Tuple, Optional, Callable
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.documents import Document
from app.rag.vector_store import get_vector_store
from app.config import settings
from app.database.db import SessionLocal
from app.database.models import TranscriptChunk, Video, Channel
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

def get_llm():
    """
    Initializes and returns the ChatGroq model instance.
    """
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not found in configuration.")
    return ChatGroq(
        groq_api_key=settings.GROQ_API_KEY,
        model_name=settings.GROQ_MODEL,
        temperature=0.2,
        streaming=True
    )

# ─── Query Intent Classification ─────────────────────────────────────────────

OVERVIEW_PATTERNS = [
    r"\b(what is|tell me about|summarize|overview of|summary of|describe)\b.*?\b(channel|content|videos|creator)\b",
    r"\b(main topics|what topics|what does (he|she|this channel) talk about)\b",
    r"\b(what kind of videos|what kind of content|all the videos|general overview)\b"
]

TIMELINE_PATTERNS = [
    r"\b(when did|when was|timeline|chronological|history|evolution|evolve|first time|how did .* start)\b",
    r"\b(over time|earliest|initial|progression)\b"
]

def is_overview_question(query: str) -> bool:
    """
    Detects if the user is asking a high-level summary/overview question about the entire channel library.
    """
    q = query.lower().strip()
    return any(re.search(pattern, q) for pattern in OVERVIEW_PATTERNS)

def is_timeline_question(query: str) -> bool:
    """
    Detects if the user is asking a chronological evolution or timeline question.
    """
    q = query.lower().strip()
    return any(re.search(pattern, q) for pattern in TIMELINE_PATTERNS)


def get_channel_overview_context(channel_id: str) -> Tuple[str, List[dict]]:
    """
    Builds a channel-level overview context by pulling:
    - All video titles, descriptions, and upload dates
    - The first (introductory) transcript chunk from each video
    Returns (context_str, citations_list).
    """
    session = SessionLocal()
    try:
        channel = session.query(Channel).filter(Channel.channel_id == channel_id).first()
        channel_name = channel.channel_name if channel else "Unknown Channel"

        videos = (
            session.query(Video)
            .filter(Video.channel_id == channel_id, Video.status == "indexed")
            .order_by(Video.upload_date.asc())
            .all()
        )

        context_parts = [
            f"Channel Name: {channel_name}\nTotal Indexed Videos: {len(videos)}\n---"
        ]
        citations = []

        for video in videos:
            first_chunk = (
                session.query(TranscriptChunk)
                .filter(TranscriptChunk.video_id == video.video_id)
                .order_by(TranscriptChunk.start_time.asc())
                .first()
            )

            intro_text = first_chunk.text[:600] if first_chunk else "(no transcript available)"
            upload_str = video.upload_date.strftime("%Y-%m-%d") if video.upload_date else "Unknown"
            desc_snippet = (video.description or "")[:200].strip()

            context_parts.append(
                f"Video Title: {video.title}\n"
                f"Video ID: {video.video_id}\n"
                f"Upload Date: {upload_str}\n"
                f"Description: {desc_snippet}\n"
                f"Opening Transcript: {intro_text}\n"
                f"---"
            )

            citations.append({
                "video_id": video.video_id,
                "title": video.title,
                "start_time": 0,
                "upload_date": upload_str
            })

        context_str = "\n\n".join(context_parts)
        return context_str, citations
    finally:
        session.close()


def get_hybrid_context(query_text: str, channel_id: Optional[str] = None, k: int = 8) -> List[Document]:
    """
    Retrieves transcript chunks by interleaving ChromaDB semantic vector search
    with BM25 keyword matching from SQLite for reciprocal rank fusion.
    """
    # 1. Semantic Vector Search (ChromaDB)
    vector_store = get_vector_store()
    search_kwargs = {}
    if channel_id:
        search_kwargs["filter"] = {"channel_id": channel_id}
        
    try:
        vector_docs = vector_store.similarity_search(query_text, k=k, **search_kwargs)
    except Exception as e:
        logger.error(f"Vector similarity search failed: {e}")
        vector_docs = []
        
    # 2. BM25 Lexical Search (SQLite chunks)
    bm25_docs = []
    session = SessionLocal()
    try:
        query = session.query(TranscriptChunk, Video.title, Video.upload_date).join(
            Video, TranscriptChunk.video_id == Video.video_id
        )
        if channel_id:
            query = query.filter(Video.channel_id == channel_id)
            
        chunks_data = query.all()
        if chunks_data:
            corpus = [re.findall(r'\w+', chunk[0].text.lower()) for chunk in chunks_data]
            bm25 = BM25Okapi(corpus)
            
            tokenized_query = re.findall(r'\w+', query_text.lower())
            if tokenized_query:
                scores = bm25.get_scores(tokenized_query)
                ranked_chunks = sorted(
                    zip(chunks_data, scores),
                    key=lambda x: x[1],
                    reverse=True
                )
                
                for (chunk, title, upload_date), score in ranked_chunks[:k]:
                    if score > 0.0:
                        doc = Document(
                            page_content=chunk.text,
                            metadata={
                                "video_id": chunk.video_id,
                                "title": title,
                                "start_time": chunk.start_time,
                                "upload_date": upload_date.isoformat() if upload_date else ""
                            }
                        )
                        bm25_docs.append(doc)
    except Exception as e:
        logger.error(f"BM25 keyword search failed: {e}")
    finally:
        session.close()
        
    # 3. Reciprocal Interleaving & Deduplication
    combined_docs = []
    seen = set()
    
    max_len = max(len(vector_docs), len(bm25_docs))
    for i in range(max_len):
        if i < len(vector_docs):
            v_doc = vector_docs[i]
            v_key = (v_doc.metadata.get("video_id"), v_doc.metadata.get("start_time"))
            if v_key not in seen:
                seen.add(v_key)
                combined_docs.append(v_doc)
                
        if i < len(bm25_docs):
            b_doc = bm25_docs[i]
            b_key = (b_doc.metadata.get("video_id"), b_doc.metadata.get("start_time"))
            if b_key not in seen:
                seen.add(b_key)
                combined_docs.append(b_doc)
                
    return combined_docs[:k]


def query_rag(query_text: str, channel_id: Optional[str] = None, sort_by_date: bool = False) -> Callable:
    """
    Synthesizes streaming responses using hybrid RAG context and Groq LLM.
    Automatically classifies query intent into Overview, Timeline, or Specific topic search.
    """
    # ── Route 1: Channel Overview Query ──
    if channel_id and is_overview_question(query_text):
        logger.info(f"Intent classified: CHANNEL_OVERVIEW for channel {channel_id}")
        context_str, citations = get_channel_overview_context(channel_id)

        system_prompt = (
            "You are an AI assistant with access to the full video library of a YouTube channel.\n"
            "Below you are given the title, description, upload date, and opening transcript excerpt for videos in this channel.\n\n"
            "Your task:\n"
            "- Provide a comprehensive, structured overview of what this channel covers.\n"
            "- Identify the main themes, key concepts, and content style across the videos.\n"
            "- Synthesize across the entire library with specific video titles as evidence.\n\n"
            "STRICT RULES:\n"
            "- Base your answer ONLY on the provided video metadata.\n"
            "- Cite videos using this markdown link format: [Video Title](https://youtube.com/watch?v={video_id})\n\n"
            f"Channel Video Library:\n{context_str}"
        )

        llm = get_llm()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query_text)
        ]

        def generate_stream():
            yield f"METADATA:{json.dumps(citations)}\n"
            for chunk in llm.stream(messages):
                yield chunk.content

        return generate_stream

    # ── Route 2 & 3: Timeline & Hybrid Factual Queries ──
    is_timeline = is_timeline_question(query_text) or sort_by_date
    k_limit = 12 if is_timeline else 8
    
    if is_timeline:
        logger.info(f"Intent classified: TIMELINE_QUERY (forcing chronological sort, k={k_limit})")

    docs = get_hybrid_context(query_text, channel_id=channel_id, k=k_limit)

    if is_timeline:
        docs = sorted(docs, key=lambda x: x.metadata.get("upload_date", ""))

    context_parts = []
    citations = []

    for doc in docs:
        meta = doc.metadata
        video_id = meta.get("video_id")
        title = meta.get("title")
        start_time = meta.get("start_time", 0.0)
        upload_date = meta.get("upload_date", "")

        citation = {
            "video_id": video_id,
            "title": title,
            "start_time": start_time,
            "upload_date": upload_date
        }
        if citation not in citations:
            citations.append(citation)

        context_parts.append(
            f"Video Title: {title}\n"
            f"Video ID: {video_id}\n"
            f"Upload Date: {upload_date}\n"
            f"Timestamp: {int(start_time)}s\n"
            f"Content: {doc.page_content}\n"
            f"---"
        )

    context_str = "\n\n".join(context_parts)

    timeline_inst = (
        "Note: The user is asking a chronological history or evolution question. "
        "The Context below is arranged chronologically from oldest to newest. "
        "Summarize the timeline step-by-step with clear dates and video transitions.\n\n"
        if is_timeline else ""
    )

    system_prompt = (
        "You are an AI assistant designed to answer questions using transcripts from a YouTube channel.\n"
        "Your task is to provide an accurate, clear response based ONLY on the transcript chunks provided in the Context below.\n"
        "If the answer cannot be determined from the Context, state that you do not have enough information.\n\n"
        f"{timeline_inst}"
        "Citations Policy:\n"
        "1. For every fact, assertion, or summary, cite the source video inline.\n"
        "2. Format each link as: [Video Title](https://youtube.com/watch?v={video_id}&t={seconds}) where {seconds} is the start time in seconds.\n"
        "3. Only use the video_id and start_time provided in the Context.\n\n"
        f"Context:\n{context_str}"
    )

    llm = get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query_text)
    ]

    def generate_stream():
        yield f"METADATA:{json.dumps(citations)}\n"
        for chunk in llm.stream(messages):
            yield chunk.content

    return generate_stream
