import pytest
from app.database.models import Channel, Video

def test_blank_chat_message_is_rejected(client):
    """Blank or whitespace-only messages are rejected with 422."""
    res = client.post("/api/chat", json={"message": "   "})
    assert res.status_code == 422

def test_oversized_chat_message_is_rejected(client):
    """Oversized messages (> 1500 chars) are rejected with 422."""
    huge_message = "A" * 1501
    res = client.post("/api/chat", json={"message": huge_message})
    assert res.status_code == 422

def test_invalid_youtube_urls_rejected(client):
    """Invalid YouTube URLs or arbitrary text strings are rejected with 422."""
    invalid_payloads = [
        {"url": "ftp://not-youtube.com/invalid"},
        {"url": "not_a_valid_youtube_channel_at_all!!"},
        {"url": "@invalid handle with spaces"},
    ]
    for p in invalid_payloads:
        res = client.post("/api/index-channel", json=p)
        assert res.status_code in [400, 422]

def test_unknown_video_returns_404(client):
    """Unknown video returns 404."""
    res = client.get("/api/video/unknown_video_id_999999")
    assert res.status_code == 404
    data = res.json()
    assert data["detail"] == "Video not found."

def test_duplicate_active_indexing_returns_409(client, test_db, mocker):
    """Duplicate active indexing request returns 409 Conflict."""
    chan = Channel(
        channel_id="UC_already_indexing",
        channel_name="Already Indexing Channel",
        custom_url="@alreadyindexing",
        indexing_status="indexing"
    )
    test_db.add(chan)
    test_db.commit()

    # Mock YouTubeClient to resolve to this channel_id
    mock_yt = mocker.MagicMock()
    mock_yt.extract_channel_info_from_url.return_value = {
        "channel_id": "UC_already_indexing",
        "channel_name": "Already Indexing Channel",
        "custom_url": "@alreadyindexing",
        "thumbnail_url": None,
        "uploads_playlist_id": "UU_already_indexing"
    }
    mocker.patch("app.services.indexing_service.YouTubeClient", return_value=mock_yt)

    res = client.post("/api/index-channel", json={"url": "https://youtube.com/@alreadyindexing"})
    assert res.status_code == 409
    assert "currently being indexed" in res.json()["detail"]

def test_search_response_has_documented_fields(client, mocker):
    """Search response returns documented schema fields."""
    mock_doc = mocker.MagicMock()
    mock_doc.page_content = "Sample transcript chunk about database indexes."
    mock_doc.metadata = {
        "video_id": "vid_sample",
        "title": "Index Tutorial",
        "start_time": 42.0,
        "upload_date": "2023-01-01"
    }
    mocker.patch("app.api.router.get_hybrid_context", return_value=[mock_doc])

    res = client.get("/api/search?query=database+indexes")
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    item = results[0]
    for field in ["text", "score", "video_id", "video_title", "start_time", "upload_date"]:
        assert field in item
    assert item["score"] == 1.0

def test_internal_errors_do_not_expose_raw_exception(client, mocker):
    """Internal server errors return safe client messages instead of raw stack traces."""
    # Force get_hybrid_context to raise an internal database or connection exception
    mocker.patch("app.api.router.get_hybrid_context", side_effect=RuntimeError("SQLITE_CORRUPT: disk I/O error 0xdeadbeef"))

    res = client.get("/api/search?query=fail_test")
    assert res.status_code == 500
    detail = res.json()["detail"]
    # The response must not leak the raw error message or stack trace
    assert "0xdeadbeef" not in detail
    assert "SQLITE_CORRUPT" not in detail
    assert detail == "Semantic search encountered an internal error."
