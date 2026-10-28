import logging
import time
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.database.db import SessionLocal
from app.database.models import Channel, Video, TranscriptChunk, Topic
from app.ingest.youtube_client import YouTubeClient
from app.ingest.transcripter import Transcripter, TranscriptsDisabledError, NoTranscriptFoundError
from app.rag.vector_store import add_transcript_chunks, delete_video_vectors
from app.services.topic_extractor import TopicExtractor

logger = logging.getLogger(__name__)

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
    - Deletes old Chroma vectors
    - Deletes old SQLite chunks and topics
    - Embeds and stores in ChromaDB
    - Saves chunks and dynamically extracted topics in SQLite
    - Marks video as 'indexed' only after both writes succeed
    - If SQLite write fails after Chroma write, deletes added Chroma vectors
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

        # 1. Delete old Chroma vectors for this video
        try:
            delete_video_vectors(video_id)
        except Exception as exc:
            video.status = "failed"
            video.error_message = str(exc)
            db.commit()
            return False

        # 2. Delete old SQLite transcript chunks and topics
        db.query(TranscriptChunk).filter(TranscriptChunk.video_id == video_id).delete()
        db.query(Topic).filter(Topic.video_id == video_id).delete()
        db.commit()

        # 3. Add new Chroma documents
        upload_date_str = video.upload_date.isoformat() if video.upload_date else ""
        try:
            chroma_ids = add_transcript_chunks(
                video_id=video_id,
                channel_id=channel_id,
                title=video.title,
                upload_date=upload_date_str,
                chunks=chunks
            )
        except Exception as chroma_err:
            logger.error(f"Chroma vector insertion failed for video {video_id}: {chroma_err}")
            video.status = "failed"
            video.error_message = f"Chroma vector insertion failed: {str(chroma_err)}"
            db.commit()
            return False

        # 4. Add new SQLite transcript chunks and topics
        try:
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

            candidate_topics = TopicExtractor.extract_salient_topics_from_metadata(
                title=video.title or "",
                description=video.description or ""
            )
            
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

            # 5. Mark video as indexed only after both writes succeed
            video.status = "indexed"
            video.error_message = None
            db.commit()
            logger.info(f"Successfully indexed video: {video.title} ({len(chunks)} chunks, {len(topic_occurrences)} topics)")
            return True

        except Exception as sqlite_err:
            db.rollback()
            # If SQLite write fails after Chroma write, clean up newly added vectors
            delete_video_vectors(video_id)
            video.status = "failed"
            video.error_message = f"SQLite chunk write failed: {str(sqlite_err)}"
            db.commit()
            logger.error(f"Failed SQLite chunk write for video {video_id}: {sqlite_err}")
            return False

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


def run_single_video_reindex(video_id: str, custom_topics: Optional[List[str]] = None) -> None:
    """
    Re-indexes an individual video by ID using its own SQLite session.
    """
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.video_id == video_id).first()
        if not video:
            raise ValueError(f"Video {video_id} not found in database.")

        index_single_video_internal(video, db, custom_topics=custom_topics)
    finally:
        db.close()


def run_channel_indexing(
    channel_info: dict, 
    custom_topics: Optional[List[str]] = None,
    scope: str = "latest_20"
) -> None:
    """
    Orchestrates YouTube channel indexing in a background task with its own database session.
    Reads channel.indexing_status from SQLite before each video to detect cancellation.
    """
    channel_id = channel_info.get("channel_id")
    if not channel_id:
        logger.error("run_channel_indexing called without channel_id in channel_info.")
        return

    db = SessionLocal()
    try:
        channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
        if not channel:
            channel = Channel(
                channel_id=channel_id,
                channel_name=channel_info.get("channel_name", "Unknown Channel"),
                custom_url=channel_info.get("custom_url"),
                thumbnail_url=channel_info.get("thumbnail_url"),
                indexing_status="indexing"
            )
            db.add(channel)
            db.commit()
            db.refresh(channel)
        else:
            channel.indexing_status = "indexing"
            db.commit()

        # Fetch video metadata according to scope
        yt = YouTubeClient()
        playlist_id = channel_info.get("uploads_playlist_id")
        if not playlist_id:
            details = yt.get_channel_details(channel_id=channel_id)
            playlist_id = details.get("uploads_playlist_id")

        limit = None
        if scope == "latest_20":
            limit = 20
        elif scope == "latest_50":
            limit = 50
        # "entire_channel" leaves limit = None

        logger.info(f"Fetching video list for uploads playlist: {playlist_id} with scope '{scope}' (limit={limit})")
        videos_metadata = yt.get_all_videos_in_playlist(playlist_id, limit=limit)

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
        logger.info(f"Queued {len(pending_videos)} videos for channel {channel_id}.")

        for video in pending_videos:
            # Check SQLite indexing_status before each video
            channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
            if channel and channel.indexing_status == "cancel_requested":
                logger.info(f"Indexing cancelled by user for channel: {channel_id}. Stopping pipeline...")
                video.status = "pending"
                channel.indexing_status = "idle"
                db.commit()
                return

            index_single_video_internal(video, db, custom_topics=custom_topics, channel_id=channel_id)

            channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
            if channel and channel.indexing_status == "cancel_requested":
                logger.info(f"Indexing cancelled by user for channel: {channel_id}. Stopping pipeline...")
                channel.indexing_status = "idle"
                db.commit()
                return

            time.sleep(0.5)

        # Mark channel indexing completed
        channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
        if channel:
            channel.indexed_at = datetime.utcnow()
            channel.indexing_status = "idle"
            db.commit()
        logger.info(f"Completed channel indexing for channel ID: {channel_id}")

    except Exception as e:
        logger.error(f"Error during channel indexing pipeline: {e}")
        try:
            channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
            if channel:
                channel.indexing_status = "idle"
                db.commit()
        except Exception:
            pass
        raise e
    finally:
        db.close()
