import logging
import asyncio
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Response, Query
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
from app.rag.engine import get_hybrid_context, query_rag
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
    Validates channel URL and starts background indexing with bounded scope.
    """
    try:
        return IndexingService.start_channel_indexing(
            url=payload.url,
            background_tasks=background_tasks,
            db=db,
            custom_topics=payload.custom_topics,
            scope=payload.scope
        )
    except HTTPException:
        raise
    except ValueError as ve:
        logger.warning(f"Invalid channel request: {ve}")
        raise HTTPException(status_code=400, detail="Invalid channel URL or handle provided.")
    except Exception as e:
        logger.error(f"Unexpected error starting channel indexing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start channel indexing. Please try again.")


@router.post("/cancel-indexing")
def cancel_indexing(payload: CancelRequest, db: Session = Depends(get_db)):
    """
    Cancels in-progress background indexing for a channel.
    """
    try:
        return IndexingService.cancel_channel_indexing(payload.channel_id, db)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail="Channel not found.")
    except Exception as e:
        logger.error(f"Failed to cancel indexing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to cancel channel indexing.")


@router.post("/reindex-video/{video_id}")
def reindex_video(
    video_id: str,
    payload: Optional[ReindexVideoRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """
    Re-indexes an individual video (re-chunks, updates vectors and topics).
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
        logger.warning(f"Video not found for re-indexing: {video_id}")
        raise HTTPException(status_code=404, detail="Video not found.")
    except Exception as e:
        logger.error(f"Failed to re-index video {video_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to re-index video.")


# ─── Data & Export Endpoints ────────────────────────────────────────────────

@router.get("/channels", response_model=List[ChannelSummary])
def get_channels(db: Session = Depends(get_db)):
    """
    Returns all channels indexed in the system.
    """
    try:
        return ChannelService.get_all_channels(db)
    except Exception as e:
        logger.error(f"Error fetching channels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve channels.")


@router.get("/videos", response_model=List[VideoSummary])
def get_videos(
    channel_id: Optional[str] = None, 
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Returns indexed and pending videos, optionally filtered by channel_id and status.
    """
    try:
        videos = ChannelService.get_videos_by_channel(db, channel_id=channel_id, status=status)
        return videos[offset:offset + limit]
    except Exception as e:
        logger.error(f"Error fetching videos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve videos.")


@router.get("/video/{video_id}", response_model=VideoDetailResponse)
def get_video_detail(video_id: str, db: Session = Depends(get_db)):
    """
    Returns metadata and transcript segments for a single video.
    """
    try:
        detail = ChannelService.get_video_detail(db, video_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Video not found.")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching video detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve video details.")


@router.get("/topics", response_model=List[TopicSummary])
def get_topics(channel_id: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Returns auto-discovered topics and their video occurrences.
    """
    try:
        return ChannelService.get_topics_summary(db, channel_id=channel_id)
    except Exception as e:
        logger.error(f"Error fetching topics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve topics.")


@router.get("/export/{channel_id}")
def export_channel_data(
    channel_id: str, 
    format: ExportFormat = ExportFormat.JSON, 
    db: Session = Depends(get_db)
):
    """
    Exports channel video metadata and transcript chunks as downloadable JSON or CSV.
    """
    try:
        content, media_type, filename = ChannelService.export_channel_data(db, channel_id, format.value)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Error exporting channel data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to export channel data.")


# ─── Search & RAG Chat Endpoints ─────────────────────────────────────────────

@router.get("/search", response_model=List[SearchResultItem])
@limiter.limit("60/minute")
def search_chunks(
    request: Request,
    query: str = Query(..., min_length=1, max_length=500),
    channel_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Performs hybrid retrieval (Chroma semantic vector search + BM25 lexical search with True RRF)
    across indexed transcripts with rate limiting.
    The returned score is an explicit rank-based relevance proxy (1.0 down toward 0.0), not a
    raw semantic similarity score, reflecting Reciprocal Rank Fusion ordering.
    """
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    try:
        docs = get_hybrid_context(
            query_text=clean_query,
            channel_id=channel_id,
        )

        results = []
        for index, doc in enumerate(docs):
            meta = doc.metadata if hasattr(doc, "metadata") and doc.metadata else {}
            video_id = meta.get("video_id")
            video = db.query(Video).filter(Video.video_id == video_id).first() if video_id else None

            # Rank-based relevance proxy score: derived from RRF position, not a semantic similarity score
            score = round(1.0 - (index / max(len(docs), 1)), 3)

            results.append({
                "text": doc.page_content,
                "score": float(score),
                "video_id": video_id or "",
                "video_title": video.title if video else meta.get("title", ""),
                "start_time": float(meta.get("start_time", 0.0)),
                "upload_date": video.upload_date if video else meta.get("upload_date", "")
            })

        return results
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Semantic search encountered an internal error.")


@router.post("/chat")
@limiter.limit("30/minute")
def chat_rag(request: Request, payload: ChatRequest):
    """
    Streams a RAG generated response with citations using ChatGroq.
    Protected by rate limiter (30 requests/minute).
    """
    try:
        generate_fn = query_rag(
            query_text=payload.message,
            channel_id=payload.channel_id,
            sort_by_date=payload.sort_by_date
        )
        return StreamingResponse(generate_fn(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating response from knowledge base.")


@router.get("/index-progress/{channel_id}")
def index_progress(channel_id: str):
    """
    Server-Sent Events (SSE) endpoint to stream real-time indexing progress for a given channel.
    Tracks indexing_status in SQLite.
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
                    yield f"data: {json.dumps({'indexed_videos': indexed_count, 'total_videos': video_count, 'indexing_status': channel.indexing_status})}\n\n"

                if video_count > 0 and indexed_count == video_count:
                    logger.info(f"SSE progress complete for channel {channel_id}.")
                    break

                if channel.indexing_status != "indexing":
                    logger.info(f"SSE progress stopped: channel {channel_id} status is '{channel.indexing_status}'.")
                    yield f"data: {json.dumps({'indexed_videos': indexed_count, 'total_videos': video_count, 'indexing_status': channel.indexing_status})}\n\n"
                    break
            except Exception as loop_err:
                logger.error(f"Error in SSE progress stream: {loop_err}")
                yield f"data: {json.dumps({'error': 'Error checking progress'})}\n\n"
                break
            finally:
                session.close()

            await asyncio.sleep(2.0)

    return StreamingResponse(progress_generator(), media_type="text/event-stream")
