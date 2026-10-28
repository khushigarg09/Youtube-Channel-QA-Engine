from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database.db import Base
import datetime

class Channel(Base):
    __tablename__ = "channels"

    channel_id = Column(String, primary_key=True, index=True)
    channel_name = Column(String, nullable=False)
    custom_url = Column(String, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    indexed_at = Column(DateTime, default=datetime.datetime.utcnow)
    indexing_status = Column(
        String,
        default="idle",
        nullable=False,
    )  # "idle", "indexing", "cancel_requested"

    # Relationships
    videos = relationship("Video", back_populates="channel", cascade="all, delete-orphan")

class Video(Base):
    __tablename__ = "videos"

    video_id = Column(String, primary_key=True, index=True)
    channel_id = Column(String, ForeignKey("channels.channel_id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    upload_date = Column(DateTime, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    status = Column(String, default="pending")  # "pending", "indexing", "indexed", "failed", "no_transcript"
    error_message = Column(Text, nullable=True)

    # Relationships
    channel = relationship("Channel", back_populates="videos")
    chunks = relationship("TranscriptChunk", back_populates="video", cascade="all, delete-orphan")
    topics = relationship("Topic", back_populates="video", cascade="all, delete-orphan")

class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"

    chunk_id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, ForeignKey("videos.video_id"), nullable=False)
    text = Column(Text, nullable=False)
    start_time = Column(Float, nullable=False)  # in seconds
    duration = Column(Float, nullable=False)    # in seconds
    chroma_id = Column(String, unique=True, index=True, nullable=False)

    # Relationships
    video = relationship("Video", back_populates="chunks")

class Topic(Base):
    __tablename__ = "topics"

    topic_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, index=True, nullable=False)
    video_id = Column(String, ForeignKey("videos.video_id"), nullable=False)
    timestamp = Column(Float, nullable=False)  # in seconds

    # Relationships
    video = relationship("Video", back_populates="topics")
