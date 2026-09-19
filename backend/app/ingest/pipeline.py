import logging
import time
from datetime import datetime
from typing import List, Optional, Set
from sqlalchemy.orm import Session
from app.database.models import Channel, Video, TranscriptChunk, Topic
from app.ingest.youtube_client import YouTubeClient
from app.ingest.transcripter import Transcripter, TranscriptsDisabledError, NoTranscriptFoundError
from app.rag.vector_store import add_transcript_chunks, get_vector_store
from app.services.topic_extractor import TopicExtractor

logger = logging.getLogger(__name__)

# Active indexing state registries
CANCELLED_CHANNELS: Set[str] = set()
ACTIVE_INDEXING_CHANNELS: Set[str] = set()

def index_single_video_internal(
    video: Video, 
    db: Session, 
    custom_topics: Optional[List[str]] = None,
    channel_id: Optional[str] = None
) -> bool:
    """
    Internal helper to process a single video:
    - Fetches transcript
    - Chunks transcript
    - Embeds and stores in ChromaDB
    - Dynamically extracts topics without hardcoding
    - Saves chunks and topics in SQLite
    """
    video_id = video.video_id
    channel_id = channel_id or video.channel_id
    logger.info(f"Processing transcript for video: {video.title} ({video_id})")

    video.status = "indexing"
    db.commit()

    try:
        # Fetch transcript
        transcript = Transcripter.get_transcript(video_id)
        if not transcript:
            raise NoTranscriptFoundError(f"Empty transcript returned for {video_id}")

        # Chunk transcript
        chunks = Transcripter.chunk_transcript(transcript)
        if not chunks:
            raise ValueError("No transcript segments could be processed into chunks.")

        # Clean existing chunks and topics for this video in DB if re-indexing
        db.query(TranscriptChunk).filter(TranscriptChunk.video_id == video_id).delete()
        db.query(Topic).filter(Topic.video_id == video_id).delete()
        db.commit()

        # Generate embeddings & save to ChromaDB
        upload_date_str = video.upload_date.isoformat() if video.upload_date else ""
        chroma_ids = add_transcript_chunks(
            video_id=video_id,
            channel_id=channel_id,
            title=video.title,
            upload_date=upload_date_str,
            chunks=chunks
        )

        # Save chunks to SQLite
        for i, chunk in enumerate(chunks):
            chroma_id = chroma_ids[i]
            db_chunk = TranscriptChunk(
                video_id=video_id,
                text=chunk["text"],
                start_time=chunk["start_time"],
                duration=chunk["duration"],
                chroma_id=chroma_id
            )
            db.add(db_chunk)

        # ── Dynamic Topic Discovery (Zero Hardcoding) ──
        # Extract candidate topics from video title and description
        candidate_topics = TopicExtractor.extract_salient_topics_from_metadata(
            title=video.title or "",
            description=video.description or ""
        )
        
        # Scan chunks for topic mentions with timestamp localization
        topic_occurrences = TopicExtractor.find_topic_occurrences_in_chunks(
            chunks=chunks,
            candidate_topics=candidate_topics,
            custom_topics=custom_topics
        )

        for occ in topic_occurrences:
            db_topic = Topic(
                name=occ["name"],
                video_id=video_id,
                timestamp=occ["timestamp"]
            )
            db.add(db_topic)

        video.status = "indexed"
        video.error_message = None
        db.commit()
        logger.info(f"Successfully indexed video: {video.title} ({len(chunks)} chunks, {len(topic_occurrences)} topics)")
        return True

    except (TranscriptsDisabledError, NoTranscriptFoundError) as e:
        db.rollback()
        video.status = "no_transcript"
        video.error_message = str(e)
        db.commit()
        logger.info(f"Video {video_id} has no transcripts: {str(e)}")
        return False
    except Exception as e:
        db.rollback()
        video.status = "failed"
        video.error_message = str(e)
        db.commit()
        logger.error(f"Failed to index video {video_id}: {str(e)}")
        return False


def run_single_video_reindex(video_id: str, db: Session, custom_topics: Optional[List[str]] = None) -> Video:
    """
    Re-indexes an individual video by ID.
    """
    video = db.query(Video).filter(Video.video_id == video_id).first()
    if not video:
        raise ValueError(f"Video {video_id} not found in database.")

    index_single_video_internal(video, db, custom_topics=custom_topics)
    db.refresh(video)
    return video


def run_channel_indexing(channel_url: str, db: Session, custom_topics: Optional[List[str]] = None):
    """
    Orchestrates the YouTube channel indexing flow in the background.
    """
    channel_id = None
    try:
        logger.info(f"Resolving YouTube channel from URL: {channel_url}")
        yt = YouTubeClient()
        channel_info = yt.extract_channel_info_from_url(channel_url)
        
        channel_id = channel_info["channel_id"]
        ACTIVE_INDEXING_CHANNELS.add(channel_id)
        
        channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
        if not channel:
            channel = Channel(
                channel_id=channel_id,
                channel_name=channel_info["channel_name"],
                custom_url=channel_info["custom_url"],
                thumbnail_url=channel_info["thumbnail_url"]
            )
            db.add(channel)
            db.commit()
            db.refresh(channel)
        
        # Fetch all video metadata from uploads playlist
        logger.info(f"Fetching video list for uploads playlist: {channel_info['uploads_playlist_id']}")
        videos_metadata = yt.get_all_videos_in_playlist(channel_info["uploads_playlist_id"])
        
        pending_videos = []
        for metadata in videos_metadata:
            vid = metadata["video_id"]
            video = db.query(Video).filter(Video.video_id == vid).first()
            
            pub_date = None
            if metadata.get("upload_date"):
                try:
                    pub_date = datetime.strptime(metadata["upload_date"], "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    pub_date = datetime.utcnow()

            if not video:
                video = Video(
                    video_id=vid,
                    channel_id=channel_id,
                    title=metadata["title"],
                    description=metadata.get("description", ""),
                    upload_date=pub_date,
                    thumbnail_url=metadata.get("thumbnail_url"),
                    duration_seconds=metadata.get("duration_seconds"),
                    status="pending"
                )
                db.add(video)
                pending_videos.append(video)
            else:
                # If already indexed, skip. If failed/pending, retry.
                if video.status != "indexed":
                    video.title = metadata["title"]
                    video.description = metadata.get("description", "")
                    video.upload_date = pub_date
                    video.thumbnail_url = metadata.get("thumbnail_url")
                    video.duration_seconds = metadata.get("duration_seconds")
                    video.status = "pending"
                    video.error_message = None
                    pending_videos.append(video)
                    
        db.commit()
        logger.info(f"Added/Updated {len(pending_videos)} videos in indexing queue.")

        # Ingest transcripts for pending videos
        for video in pending_videos:
            if channel_id in CANCELLED_CHANNELS:
                logger.info(f"Indexing cancelled by user for channel: {channel_id}. Stopping pipeline...")
                CANCELLED_CHANNELS.discard(channel_id)
                video.status = "pending"
                db.commit()
                break
                
            index_single_video_internal(video, db, custom_topics=custom_topics, channel_id=channel_id)

            if channel_id in CANCELLED_CHANNELS:
                logger.info(f"Indexing cancelled by user for channel: {channel_id}. Stopping pipeline...")
                CANCELLED_CHANNELS.discard(channel_id)
                break

            # Rate throttling to respect API usage
            time.sleep(1.0)

        # Update channel indexed timestamp
        channel.indexed_at = datetime.utcnow()
        db.commit()
        logger.info(f"Completed channel indexing for channel ID: {channel_id}")

    except Exception as e:
        logger.error(f"Error during channel indexing pipeline: {str(e)}")
        raise e
    finally:
        if channel_id:
            ACTIVE_INDEXING_CHANNELS.discard(channel_id)
