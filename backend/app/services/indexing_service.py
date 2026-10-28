import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import BackgroundTasks, HTTPException
from app.database.models import Channel, Video
from app.ingest.youtube_client import YouTubeClient
from app.ingest.pipeline import run_channel_indexing, run_single_video_reindex

logger = logging.getLogger(__name__)

class IndexingService:
    @staticmethod
    def start_channel_indexing(
        url: str, 
        background_tasks: BackgroundTasks, 
        db: Session,
        custom_topics: Optional[List[str]] = None,
        scope: str = "latest_20"
    ) -> dict:
        """
        Validates channel URL, creates/updates channel record, sets indexing_status to 'indexing',
        and registers the background indexing task. Rejects with 409 Conflict if already indexing.
        """
        url = url.strip()
        logger.info(f"Resolving channel metadata for URL: {url}")
        yt = YouTubeClient()
        channel_info = yt.extract_channel_info_from_url(url)
        
        channel_id = channel_info["channel_id"]
        channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()

        if channel:
            if channel.indexing_status == "indexing":
                raise HTTPException(
                    status_code=409,
                    detail=f"Channel '{channel.channel_name}' is currently being indexed. Please wait for completion or cancel it."
                )
            channel.indexing_status = "indexing"
            db.commit()
            db.refresh(channel)
        else:
            channel = Channel(
                channel_id=channel_id,
                channel_name=channel_info["channel_name"],
                custom_url=channel_info.get("custom_url"),
                thumbnail_url=channel_info.get("thumbnail_url"),
                indexing_status="indexing"
            )
            db.add(channel)
            db.commit()
            db.refresh(channel)

        background_tasks.add_task(
            run_channel_indexing,
            channel_info,
            custom_topics,
            scope,
        )

        return {
            "message": f"Indexing started in the background (scope: {scope}).",
            "channel": {
                "channel_id": channel.channel_id,
                "channel_name": channel.channel_name,
                "custom_url": channel.custom_url,
                "thumbnail_url": channel.thumbnail_url,
                "indexing_status": channel.indexing_status
            }
        }

    @staticmethod
    def cancel_channel_indexing(channel_id: str, db: Session) -> dict:
        """
        Requests cancellation by setting indexing_status to 'cancel_requested' in SQLite
        and resetting any videos currently marked as 'indexing' back to 'pending'.
        """
        channel_id = channel_id.strip()
        channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
        if not channel:
            raise ValueError(f"Channel with ID '{channel_id}' not found.")

        channel.indexing_status = "cancel_requested"

        # Reset in-progress videos in DB
        db.query(Video).filter(
            Video.channel_id == channel_id,
            Video.status == "indexing"
        ).update({"status": "pending"})
        db.commit()

        logger.info(f"Cancellation registered in SQLite for channel: {channel_id}")
        return {"message": f"Indexing cancellation request submitted for channel {channel_id}."}

    @staticmethod
    def reindex_video(
        video_id: str, 
        background_tasks: BackgroundTasks, 
        db: Session,
        custom_topics: Optional[List[str]] = None
    ) -> dict:
        """
        Triggers re-indexing for a single video in the background.
        """
        video = db.query(Video).filter(Video.video_id == video_id).first()
        if not video:
            raise ValueError(f"Video with ID '{video_id}' not found.")

        video.status = "indexing"
        db.commit()

        background_tasks.add_task(run_single_video_reindex, video_id, custom_topics)

        return {
            "message": f"Re-indexing started for video: {video.title}",
            "video_id": video_id,
            "status": "indexing"
        }
