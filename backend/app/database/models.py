import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, JSON
from pgvector.sqlalchemy import Vector
from app.database.db import Base


class VectorType(TypeDecorator):
    """
    Dialect-aware vector column:
    Uses pgvector Vector(dim) on PostgreSQL, and JSON fallback on SQLite/other dialects.
    """
    impl = Vector
    cache_ok = True

    def __init__(self, dim=384, *args, **kwargs):
        super().__init__(dim, *args, **kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())


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
    channel_id = Column(String, ForeignKey("channels.channel_id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    upload_date = Column(DateTime, nullable=True, index=True)
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
    video_id = Column(String, ForeignKey("videos.video_id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    start_time = Column(Float, nullable=False)  # in seconds
    duration = Column(Float, nullable=False)    # in seconds
    chroma_id = Column(String, unique=True, index=True, nullable=True)
    embedding = Column(VectorType(384), nullable=True)

    # Relationships
    video = relationship("Video", back_populates="chunks")


class Topic(Base):
    __tablename__ = "topics"

    topic_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, index=True, nullable=False)
    video_id = Column(String, ForeignKey("videos.video_id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(Float, nullable=False)  # in seconds

    # Relationships
    video = relationship("Video", back_populates="topics")
