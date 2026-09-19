import logging
import asyncio
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database.db import get_db, SessionLocal
from app.database.models import Channel, Video
from app.api.schemas import (
    IndexRequest, 
    CancelRequest, 
    ChatRequest, 
    ReindexVideoRequest,
    ExportFormat,
    ChannelSummary, 
    VideoSummary, 
    VideoDetailResponse, 
    TopicSummary, 
    SearchResultItem
)
from app.services.channel_service import ChannelService
from app.services.indexing_service import IndexingService
from app.rag.vector_store import get_vector_store
from app.rag.engine import query_rag
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# ─── Indexing Endpoints ──────────────────────────────────────────────────────

@router.post("/index-channel")
@limiter.limit("10/minute")
def index_channel(
    request: Request,
    payload: IndexRequest, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """
    Validates channel URL and starts background indexing.
    Optionally accepts a custom topic keywords list.
    """
    try:
        return IndexingService.start_channel_indexing(
            url=payload.url,
            background_tasks=background_tasks,
            db=db,
            custom_topics=payload.custom_topics
        )
    except Exception as e:
        logger.error(f"Failed to start channel indexing: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cancel-indexing")
def cancel_indexing(payload: CancelRequest, db: Session = Depends(get_db)):
    """
    Cancels in-progress background indexing for a channel.
    """
    try:
        return IndexingService.cancel_channel_indexing(payload.channel_id, db)
    except Exception as e:
        logger.error(f"Failed to cancel indexing: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reindex-video/{video_id}")
def reindex_video(
    video_id: str,
    payload: Optional[ReindexVideoRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """
    Re-indexes an individual video (downloads transcript, re-chunks, updates vectors and topics).
    """
    try:
        custom_topics = payload.custom_topics if payload else None
        return IndexingService.reindex_video(
            video_id=video_id,
            background_tasks=background_tasks,
            db=db,
            custom_topics=custom_topics
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to re-index video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Data & Export Endpoints ────────────────────────────────────────────────

@router.get("/channels", response_model=List[ChannelSummary])
def get_channels(db: Session = Depends(get_db)):
    """
    Returns all channels indexed in the system.
    """
    return ChannelService.get_all_channels(db)


@router.get("/videos", response_model=List[VideoSummary])
def get_videos(
    channel_id: Optional[str] = None, 
    status: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    """
    Returns indexed and pending videos, optionally filtered by channel_id and status.
    """
    return ChannelService.get_videos_by_channel(db, channel_id=channel_id, status=status)


@router.get("/video/{video_id}", response_model=VideoDetailResponse)
def get_video_detail(video_id: str, db: Session = Depends(get_db)):
    """
    Returns metadata and transcript segments for a single video.
    """
    detail = ChannelService.get_video_detail(db, video_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Video not found")
    return detail


@router.get("/topics", response_model=List[TopicSummary])
def get_topics(channel_id: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Returns auto-discovered topics and their video occurrences.
    """
    return ChannelService.get_topics_summary(db, channel_id=channel_id)


@router.get("/export/{channel_id}")
def export_channel_data(
    channel_id: str, 
    format: ExportFormat = ExportFormat.JSON, 
    db: Session = Depends(get_db)
):
    """
    Exports all channel video metadata and transcript chunks as downloadable JSON or CSV.
    """
    content, media_type, filename = ChannelService.export_channel_data(db, channel_id, format.value)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ─── Search & RAG Chat Endpoints ─────────────────────────────────────────────

@router.get("/search", response_model=List[SearchResultItem])
def search_chunks(query: str, channel_id: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Performs semantic vector search across all indexed transcripts.
    """
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query parameter is required")

    vector_store = get_vector_store()
    search_kwargs = {}
    if channel_id:
        search_kwargs["filter"] = {"channel_id": channel_id}

    docs = vector_store.similarity_search_with_relevance_scores(query, k=15, **search_kwargs)

    results = []
    for doc, score in docs:
        meta = doc.metadata
        video_id = meta.get("video_id")
        video = db.query(Video).filter(Video.video_id == video_id).first()

        results.append({
            "text": doc.page_content,
            "score": float(score),
            "video_id": video_id,
            "video_title": video.title if video else meta.get("title", ""),
            "start_time": float(meta.get("start_time", 0.0)),
            "upload_date": video.upload_date if video else meta.get("upload_date", "")
        })

    return results


@router.post("/chat")
@limiter.limit("30/minute")
def chat_rag(request: Request, payload: ChatRequest):
    """
    Streams a RAG generated response with citations using ChatGroq.
    Protected by rate limiter (30 requests/minute).
    """
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    try:
        generate_fn = query_rag(
            query_text=payload.message,
            channel_id=payload.channel_id,
            sort_by_date=payload.sort_by_date
        )
        return StreamingResponse(generate_fn(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index-progress/{channel_id}")
def index_progress(channel_id: str):
    """
    Server-Sent Events (SSE) endpoint to stream real-time indexing progress for a given channel.
    """
    async def progress_generator():
        last_indexed = -1
        last_total = -1

        while True:
            session = SessionLocal()
            try:
                channel = session.query(Channel).filter(Channel.channel_id == channel_id).first()
                if not channel:
                    yield f"data: {json.dumps({'error': 'Channel not found'})}\n\n"
                    break

                video_count = session.query(Video).filter(Video.channel_id == channel_id).count()
                indexed_count = session.query(Video).filter(
                    Video.channel_id == channel_id,
                    Video.status.in_(["indexed", "no_transcript", "failed"])
                ).count()

                if indexed_count != last_indexed or video_count != last_total:
                    last_indexed = indexed_count
                    last_total = video_count
                    yield f"data: {json.dumps({'indexed_videos': indexed_count, 'total_videos': video_count})}\n\n"

                from app.ingest.pipeline import ACTIVE_INDEXING_CHANNELS
                if video_count > 0 and indexed_count == video_count:
                    logger.info(f"SSE progress complete for channel {channel_id}.")
                    break

                if channel_id not in ACTIVE_INDEXING_CHANNELS:
                    logger.info(f"SSE progress stopped for channel {channel_id}.")
                    yield f"data: {json.dumps({'indexed_videos': indexed_count, 'total_videos': video_count})}\n\n"
                    break
            except Exception as loop_err:
                logger.error(f"Error in SSE progress stream: {loop_err}")
                yield f"data: {json.dumps({'error': str(loop_err)})}\n\n"
                break
            finally:
                session.close()

            await asyncio.sleep(2.0)

    return StreamingResponse(progress_generator(), media_type="text/event-stream")
