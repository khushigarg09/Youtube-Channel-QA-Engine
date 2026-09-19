import csv
import io
import json
import logging
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.models import Channel, Video, TranscriptChunk, Topic

logger = logging.getLogger(__name__)

class ChannelService:
    @staticmethod
    def get_all_channels(db: Session) -> List[Dict[str, Any]]:
        """
        Retrieves all channels with aggregated video and indexing statistics.
        """
        from app.ingest.pipeline import ACTIVE_INDEXING_CHANNELS
        channels = db.query(Channel).all()
        result = []
        for c in channels:
            video_count = db.query(Video).filter(Video.channel_id == c.channel_id).count()
            indexed_count = db.query(Video).filter(Video.channel_id == c.channel_id, Video.status == "indexed").count()
            is_indexing = c.channel_id in ACTIVE_INDEXING_CHANNELS
            result.append({
                "channel_id": c.channel_id,
                "channel_name": c.channel_name,
                "custom_url": c.custom_url,
                "thumbnail_url": c.thumbnail_url,
                "indexed_at": c.indexed_at,
                "is_indexing": is_indexing,
                "total_videos": video_count,
                "indexed_videos": indexed_count
            })
        return result

    @staticmethod
    def get_videos_by_channel(
        db: Session, 
        channel_id: Optional[str] = None, 
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves video records filtered by channel and/or indexing status.
        """
        query = db.query(Video)
        if channel_id:
            query = query.filter(Video.channel_id == channel_id)
        if status:
            query = query.filter(Video.status == status)

        videos = query.order_by(Video.upload_date.desc()).all()
        result = []
        for v in videos:
            chunk_count = db.query(TranscriptChunk).filter(TranscriptChunk.video_id == v.video_id).count()
            result.append({
                "video_id": v.video_id,
                "channel_id": v.channel_id,
                "title": v.title,
                "description": v.description,
                "upload_date": v.upload_date,
                "thumbnail_url": v.thumbnail_url,
                "duration_seconds": v.duration_seconds,
                "status": v.status,
                "error_message": v.error_message,
                "chunk_count": chunk_count
            })
        return result

    @staticmethod
    def get_video_detail(db: Session, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves full metadata and ordered transcript chunks for a single video.
        """
        video = db.query(Video).filter(Video.video_id == video_id).first()
        if not video:
            return None

        chunks = (
            db.query(TranscriptChunk)
            .filter(TranscriptChunk.video_id == video_id)
            .order_by(TranscriptChunk.start_time.asc())
            .all()
        )

        return {
            "video": {
                "video_id": video.video_id,
                "channel_id": video.channel_id,
                "title": video.title,
                "description": video.description,
                "upload_date": video.upload_date,
                "thumbnail_url": video.thumbnail_url,
                "duration_seconds": video.duration_seconds,
                "status": video.status,
                "error_message": video.error_message
            },
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "start_time": c.start_time,
                    "duration": c.duration
                } for c in chunks
            ]
        }

    @staticmethod
    def get_topics_summary(db: Session, channel_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Aggregates discovered topics by frequency and lists occurrences with video timestamps.
        """
        query = db.query(Topic.name, func.count(func.distinct(Topic.video_id))).group_by(Topic.name)
        if channel_id:
            query = query.join(Video).filter(Video.channel_id == channel_id)

        topics_summary = query.all()
        result = []

        for name, video_count in topics_summary:
            topic_instances = (
                db.query(Topic)
                .filter(Topic.name == name)
                .order_by(Topic.timestamp.asc())
                .all()
            )

            occurrences = []
            for inst in topic_instances:
                vid = db.query(Video).filter(Video.video_id == inst.video_id).first()
                if vid:
                    if channel_id and vid.channel_id != channel_id:
                        continue
                    occurrences.append({
                        "video_id": inst.video_id,
                        "video_title": vid.title,
                        "timestamp": inst.timestamp,
                        "upload_date": vid.upload_date
                    })

            if occurrences:
                result.append({
                    "topic": name,
                    "video_count": video_count,
                    "occurrences": occurrences[:30]
                })

        result.sort(key=lambda x: x["video_count"], reverse=True)
        return result

    @staticmethod
    def export_channel_data(db: Session, channel_id: str, format_type: str = "json") -> tuple[str, str, str]:
        """
        Exports all indexed videos, transcript chunks, and topics for a channel.
        Returns: (content_string, media_type, filename)
        """
        channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
        channel_name_safe = (channel.channel_name if channel else channel_id).replace(" ", "_").replace("/", "_")

        videos = db.query(Video).filter(Video.channel_id == channel_id).all()

        if format_type.lower() == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            # Header
            writer.writerow([
                "channel_id", "channel_name", "video_id", "video_title",
                "upload_date", "chunk_id", "start_time_sec", "duration_sec", "transcript_text"
            ])

            for video in videos:
                chunks = (
                    db.query(TranscriptChunk)
                    .filter(TranscriptChunk.video_id == video.video_id)
                    .order_by(TranscriptChunk.start_time.asc())
                    .all()
                )
                for chunk in chunks:
                    writer.writerow([
                        channel_id,
                        channel.channel_name if channel else "",
                        video.video_id,
                        video.title,
                        video.upload_date.isoformat() if video.upload_date else "",
                        chunk.chunk_id,
                        chunk.start_time,
                        chunk.duration,
                        chunk.text
                    ])

            return output.getvalue(), "text/csv", f"{channel_name_safe}_transcripts.csv"

        else: # JSON format
            export_payload = {
                "channel_id": channel_id,
                "channel_name": channel.channel_name if channel else "",
                "custom_url": channel.custom_url if channel else "",
                "indexed_at": channel.indexed_at.isoformat() if channel and channel.indexed_at else None,
                "videos": []
            }

            for video in videos:
                chunks = (
                    db.query(TranscriptChunk)
                    .filter(TranscriptChunk.video_id == video.video_id)
                    .order_by(TranscriptChunk.start_time.asc())
                    .all()
                )
                topics = db.query(Topic).filter(Topic.video_id == video.video_id).all()

                export_payload["videos"].append({
                    "video_id": video.video_id,
                    "title": video.title,
                    "description": video.description,
                    "upload_date": video.upload_date.isoformat() if video.upload_date else None,
                    "duration_seconds": video.duration_seconds,
                    "status": video.status,
                    "topics": [{"name": t.name, "timestamp": t.timestamp} for t in topics],
                    "chunks": [
                        {
                            "chunk_id": c.chunk_id,
                            "start_time": c.start_time,
                            "duration": c.duration,
                            "text": c.text
                        } for c in chunks
                    ]
                })

            return json.dumps(export_payload, indent=2), "application/json", f"{channel_name_safe}_transcripts.json"
