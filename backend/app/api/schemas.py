import re
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Any, Literal
from datetime import datetime
from enum import Enum

class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"

# --- Request Schemas ---

class IndexRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=300, description="YouTube channel URL or handle")
    custom_topics: Optional[List[str]] = Field(
        default=None, 
        description="Optional custom list of topics to track (max 20, max 80 chars each)."
    )
    scope: Literal["latest_20", "latest_50", "entire_channel"] = Field(
        default="latest_20",
        description="Bounded indexing scope: latest_20, latest_50, or entire_channel"
    )

    @field_validator("url")
    def validate_youtube_url(cls, v: str) -> str:
        url = v.strip()
        if not (1 <= len(url) <= 300):
            raise ValueError("Channel URL or handle must be between 1 and 300 characters.")
        if url.startswith("@"):
            if re.match(r"^@[a-zA-Z0-9._-]{1,60}$", url):
                return url
            raise ValueError("Invalid YouTube handle format.")
        
        youtube_pattern = r"^(https?:\/\/)?(www\.)?(youtube\.com\/(channel\/UC[a-zA-Z0-9_-]{22}|@[a-zA-Z0-9._-]+|c\/[a-zA-Z0-9._-]+|user\/[a-zA-Z0-9._-]+)|youtu\.be\/[a-zA-Z0-9_-]+)"
        if not re.search(youtube_pattern, url):
            if re.match(r"^UC[a-zA-Z0-9_-]{22}$", url):
                return url
            raise ValueError("Invalid YouTube channel URL or handle format.")
        return url

    @field_validator("custom_topics")
    def check_custom_topics(cls, v):
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("Maximum 20 custom topics allowed.")
        validated = []
        for topic in v:
            t = topic.strip()
            if not t or len(t) > 80:
                raise ValueError("Each custom topic must be between 1 and 80 characters.")
            validated.append(t)
        return validated


class CancelRequest(BaseModel):
    channel_id: str = Field(..., min_length=1, max_length=100, description="YouTube channel ID to cancel indexing for")


class ReindexVideoRequest(BaseModel):
    custom_topics: Optional[List[str]] = Field(
        default=None,
        description="Optional custom topic keywords (max 20, max 80 chars each)"
    )

    @field_validator("custom_topics")
    def check_custom_topics(cls, v):
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("Maximum 20 custom topics allowed.")
        validated = []
        for topic in v:
            t = topic.strip()
            if not t or len(t) > 80:
                raise ValueError("Each custom topic must be between 1 and 80 characters.")
            validated.append(t)
        return validated


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1500, description="Natural language question to ask the knowledge base")
    channel_id: Optional[str] = Field(default=None, max_length=100, description="Optional channel ID to scope the RAG query")
    sort_by_date: Optional[bool] = Field(default=False, description="Whether to sort retrieved context chronologically")

    @field_validator("message")
    def check_not_blank(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Message content cannot be empty.")
        return clean


# --- Response Schemas ---

class ChannelSummary(BaseModel):
    channel_id: str
    channel_name: str
    custom_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    indexed_at: Optional[datetime] = None
    indexing_status: str = "idle"
    is_indexing: bool = False
    total_videos: int = 0
    indexed_videos: int = 0
    failed_videos: int = 0

class VideoSummary(BaseModel):
    video_id: str
    channel_id: str
    title: str
    description: Optional[str] = None
    upload_date: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    chunk_count: int = 0

class TranscriptChunkDetail(BaseModel):
    chunk_id: int
    text: str
    start_time: float
    duration: float

class VideoDetailResponse(BaseModel):
    video: dict
    chunks: List[TranscriptChunkDetail]

class TopicOccurrence(BaseModel):
    video_id: str
    video_title: str
    timestamp: float
    upload_date: Optional[datetime] = None

class TopicSummary(BaseModel):
    topic: str
    video_count: int
    occurrences: List[TopicOccurrence]

class SearchResultItem(BaseModel):
    text: str
    score: float
    video_id: str
    video_title: str
    start_time: float
    upload_date: Optional[Any] = ""
