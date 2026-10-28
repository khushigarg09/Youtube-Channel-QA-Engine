import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.db import Base, get_db
from app.database.models import Channel, Video, TranscriptChunk, Topic
from app.main import create_app

# In-memory SQLite database specifically for automated test suite
TEST_DATABASE_URL = "sqlite:///:memory:"


@asynccontextmanager
async def test_lifespan(app: FastAPI):
    yield


test_app = create_app(lifespan_context=test_lifespan)

@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def test_db(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection, expire_on_commit=False)
    session = TestingSessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()

@pytest.fixture
def sample_channel(test_db):
    chan = Channel(
        channel_id="UC_test_chan_123",
        channel_name="Test Engineering Channel",
        custom_url="@testengineering",
        thumbnail_url="https://example.com/thumb.jpg",
        indexing_status="idle",
        indexed_at=datetime.utcnow()
    )
    test_db.add(chan)
    test_db.commit()
    test_db.refresh(chan)
    return chan

@pytest.fixture
def sample_video(test_db, sample_channel):
    vid = Video(
        video_id="vid_101",
        channel_id=sample_channel.channel_id,
        title="Understanding Connection Pools and Scaling",
        description="Comprehensive guide on database connection pools and connection limits.",
        upload_date=datetime(2023, 5, 1, 10, 0, 0),
        status="indexed",
        duration_seconds=600
    )
    test_db.add(vid)
    test_db.commit()
    test_db.refresh(vid)
    return vid

@pytest.fixture
def sample_chunks(test_db, sample_video):
    chunks = [
        TranscriptChunk(
            video_id=sample_video.video_id,
            text="Connection pools maintain a cache of database connections for reuse.",
            start_time=0.0,
            duration=30.0,
            chroma_id=f"{sample_video.video_id}_chunk_0"
        ),
        TranscriptChunk(
            video_id=sample_video.video_id,
            text="Creating a new TCP socket and TLS handshake on every query is very expensive.",
            start_time=25.0,
            duration=35.0,
            chroma_id=f"{sample_video.video_id}_chunk_1"
        ),
        TranscriptChunk(
            video_id=sample_video.video_id,
            text="By bounding connection pools, you protect backend databases from being overwhelmed.",
            start_time=55.0,
            duration=40.0,
            chroma_id=f"{sample_video.video_id}_chunk_2"
        )
    ]
    test_db.add_all(chunks)
    test_db.commit()
    return chunks
