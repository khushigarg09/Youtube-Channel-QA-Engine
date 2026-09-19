import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import BackgroundTasks
from app.database.models import Channel, Video
from app.ingest.youtube_client import YouTubeClient
from app.ingest.pipeline import (
    run_channel_indexing, 
    run_single_video_reindex, 
    CANCELLED_CHANNELS, 
    ACTIVE_INDEXING_CHANNELS
)

logger = logging.getLogger(__name__)

class IndexingService:
    @staticmethod
    def start_channel_indexing(
        url: str, 
        background_tasks: BackgroundTasks, 
        db: Session,
        custom_topics: Optional[List[str]] = None
    ) -> dict:
        """
        Validates channel URL, creates/updates channel record, and registers background job.
        """
        url = url.strip()
        logger.info(f"Resolving channel metadata for URL: {url}")
        yt = YouTubeClient()
        channel_info = yt.extract_channel_info_from_url(url)
        
        channel_id = channel_info["channel_id"]
        channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
        if not channel:
            channel = Channel(
                channel_id=channel_id,
                channel_name=channel_info["channel_name"],
                custom_url=channel_info.get("custom_url"),
                thumbnail_url=channel_info.get("thumbnail_url")
            )
            db.add(channel)
            db.commit()
            db.refresh(channel)

        ACTIVE_INDEXING_CHANNELS.add(channel_id)
        background_tasks.add_task(run_channel_indexing, url, db, custom_topics)

        return {
            "message": "Indexing started in the background.",
            "channel": {
                "channel_id": channel.channel_id,
                "channel_name": channel.channel_name,
                "custom_url": channel.custom_url,
                "thumbnail_url": channel.thumbnail_url
            }
        }

    @staticmethod
    def cancel_channel_indexing(channel_id: str, db: Session) -> dict:
        """
        Cancels background indexing and resets any in-progress videos back to pending.
        """
        channel_id = channel_id.strip()
        CANCELLED_CHANNELS.add(channel_id)
        ACTIVE_INDEXING_CHANNELS.discard(channel_id)

        # Reset in-progress videos in DB
        db.query(Video).filter(
            Video.channel_id == channel_id,
            Video.status == "indexing"
        ).update({"status": "pending"})
        db.commit()

        logger.info(f"Cancellation registered for channel: {channel_id}")
        return {"message": f"Indexing cancellation request submitted for channel {channel_id}."}

    @staticmethod
    def reindex_video(
        video_id: str, 
        background_tasks: BackgroundTasks, 
        db: Session,
        custom_topics: Optional[List[str]] = None
    ) -> dict:
        """
        Triggers re-indexing for a single video.
        """
        video = db.query(Video).filter(Video.video_id == video_id).first()
        if not video:
            raise ValueError(f"Video with ID '{video_id}' not found.")

        video.status = "indexing"
        db.commit()

        background_tasks.add_task(run_single_video_reindex, video_id, db, custom_topics)

        return {
            "message": f"Re-indexing started for video: {video.title}",
            "video_id": video_id,
            "status": "indexing"
        }
