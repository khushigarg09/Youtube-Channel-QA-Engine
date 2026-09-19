from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime
from enum import Enum

class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"

# --- Request Schemas ---

class IndexRequest(BaseModel):
    url: str = Field(..., description="YouTube channel URL or handle (e.g., @channel_name)")
    custom_topics: Optional[List[str]] = Field(
        default=None, 
        description="Optional custom list of topics to track for this channel in addition to auto-discovered topics."
    )

class CancelRequest(BaseModel):
    channel_id: str = Field(..., description="YouTube channel ID to cancel indexing for")

class ReindexVideoRequest(BaseModel):
    custom_topics: Optional[List[str]] = Field(
        default=None,
        description="Optional custom topic keywords to look for during re-indexing"
    )

class ChatRequest(BaseModel):
    message: str = Field(..., description="Natural language question to ask the knowledge base")
    channel_id: Optional[str] = Field(default=None, description="Optional channel ID to scope the RAG query")
    sort_by_date: Optional[bool] = Field(default=False, description="Whether to sort retrieved context chronologically")

# --- Response Schemas ---

class ChannelSummary(BaseModel):
    channel_id: str
    channel_name: str
    custom_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    indexed_at: Optional[datetime] = None
    is_indexing: bool = False
    total_videos: int = 0
    indexed_videos: int = 0

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
