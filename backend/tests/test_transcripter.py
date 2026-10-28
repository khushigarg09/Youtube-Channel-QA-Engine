import os
import pytest
from youtube_transcript_api import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    RequestBlocked,
    IpBlocked,
    YouTubeRequestFailed,
)
from app.ingest.transcripter import Transcripter, TRANSCRIPT_FALLBACK_ERRORS

def test_empty_transcript_returns_no_chunks():
    """Empty transcript returns no chunks."""
    assert Transcripter.chunk_transcript([]) == []
    assert Transcripter.chunk_transcript(None) == []

def test_first_timestamp_is_preserved():
    """First timestamp is preserved in first chunk."""
    transcript = [
        {"text": "Hello world welcome to the video.", "start": 12.5, "duration": 4.0},
        {"text": "Today we discuss database systems.", "start": 16.5, "duration": 5.0},
    ]
    chunks = Transcripter.chunk_transcript(transcript, target_chunk_size=100, overlap_chars=20)
    assert len(chunks) >= 1
    assert chunks[0]["start_time"] == 12.5

def test_overlap_exists_between_consecutive_chunks():
    """Overlap exists between consecutive chunks."""
    # Generate segments that exceed chunk size
    transcript = [
        {"text": f"Sentence number {i} with several extra words to increase length.", "start": float(i * 5), "duration": 4.5}
        for i in range(30)
    ]
    chunks = Transcripter.chunk_transcript(transcript, target_chunk_size=200, overlap_chars=50)
    assert len(chunks) > 1

    for i in range(len(chunks) - 1):
        chunk1 = chunks[i]["text"]
        chunk2 = chunks[i + 1]["text"]
        # There should be shared words between chunk1 and chunk2
        words1 = set(chunk1.split()[-10:])
        words2 = set(chunk2.split()[:10])
        common = words1 & words2
        assert len(common) > 0, f"Expected overlap between chunk {i} and chunk {i+1}"

def test_final_chunk_is_not_duplicated():
    """Final chunk is not duplicated."""
    transcript = [
        {"text": "Short introductory sentence.", "start": 0.0, "duration": 3.0},
        {"text": "Another sentence to fill some space.", "start": 3.0, "duration": 3.0},
    ]
    chunks = Transcripter.chunk_transcript(transcript, target_chunk_size=800, overlap_chars=150)
    assert len(chunks) == 1
    # Check with slightly longer transcript
    long_transcript = [
        {"text": f"Part {i} of detailed explanation.", "start": float(i * 3), "duration": 2.8}
        for i in range(40)
    ]
    long_chunks = Transcripter.chunk_transcript(long_transcript, target_chunk_size=300, overlap_chars=50)
    texts = [c["text"] for c in long_chunks]
    # Consecutive chunks must not have identical text
    for i in range(len(texts) - 1):
        assert texts[i] != texts[i + 1]

def test_chunk_duration_is_never_negative():
    """Chunk duration is never negative."""
    transcript = [
        {"text": "Start chunk.", "start": 10.0, "duration": 2.0},
        {"text": "Middle chunk.", "start": 12.0, "duration": 3.0},
        {"text": "End chunk.", "start": 15.0, "duration": 1.0},
    ]
    chunks = Transcripter.chunk_transcript(transcript)
    for c in chunks:
        assert c["duration"] >= 0.0
        assert isinstance(c["duration"], float)

def test_whisper_cleanup_on_failure(mocker, tmp_path):
    """Verify that temp audio cleanup removes files on Whisper failure."""
    fake_video_id = "test_cleanup_vid"

    mocker.patch(
        "app.ingest.transcripter.get_temp_audio_dir",
        return_value=tmp_path,
    )

    temp_file = tmp_path / f"{fake_video_id}.m4a"
    temp_file.write_text("mock audio data")
    part_file = tmp_path / f"{fake_video_id}_part0.m4a"
    part_file.write_text("mock audio part data")

    # Mock yt_dlp to not contact YouTube
    mocker.patch("yt_dlp.YoutubeDL")
    mocker.patch("app.ingest.transcripter.settings.GROQ_API_KEY", "mock_key_for_testing")
    # Mock Groq client to raise an exception
    mocker.patch("app.ingest.transcripter.Groq", side_effect=RuntimeError("Groq API error"))

    with pytest.raises(ValueError, match="Groq Whisper transcription failed"):
        Transcripter.transcribe_with_whisper(fake_video_id)

    # All test-created audio files must be cleaned up
    assert not temp_file.exists()
    assert not part_file.exists()


def test_whisper_cleanup_on_download_failure(mocker, tmp_path):
    """Verify that temp audio cleanup removes files when download fails."""
    fake_video_id = "test_download_fail_vid"

    mocker.patch(
        "app.ingest.transcripter.get_temp_audio_dir",
        return_value=tmp_path,
    )

    temp_file = tmp_path / f"{fake_video_id}.m4a"
    temp_file.write_text("partial download audio data")

    mock_ydl_instance = mocker.MagicMock()
    mock_ydl_instance.download.side_effect = RuntimeError("Network error downloading stream")
    mock_ydl_class = mocker.MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance
    mocker.patch("yt_dlp.YoutubeDL", mock_ydl_class)
    mocker.patch("app.ingest.transcripter.settings.GROQ_API_KEY", "mock_key_for_testing")

    with pytest.raises(ValueError, match="Groq Whisper transcription failed"):
        Transcripter.transcribe_with_whisper(fake_video_id)

    assert not temp_file.exists()


@pytest.mark.parametrize("error_instance", [
    TranscriptsDisabled("test_vid_fallback"),
    NoTranscriptFound("test_vid_fallback", ["en"], {}),
    VideoUnavailable("test_vid_fallback"),
    RequestBlocked("test_vid_fallback"),
    IpBlocked("test_vid_fallback"),
    YouTubeRequestFailed("Simulated error", "test_vid_fallback"),
])
def test_transcript_fallback_on_expected_errors(mocker, error_instance):
    """Each expected transcript exception triggers Groq Whisper fallback."""
    fake_video_id = "test_vid_fallback"

    mock_api = mocker.MagicMock()
    mock_api.list.side_effect = error_instance
    mocker.patch("app.ingest.transcripter.YouTubeTranscriptApi", return_value=mock_api)

    mock_whisper = mocker.patch(
        "app.ingest.transcripter.Transcripter.transcribe_with_whisper",
        return_value=[{"text": "Whisper transcript", "start": 0.0, "duration": 5.0}]
    )

    result = Transcripter.get_transcript(fake_video_id)
    assert result == [{"text": "Whisper transcript", "start": 0.0, "duration": 5.0}]
    mock_whisper.assert_called_once_with(fake_video_id)


def test_transcript_unexpected_error_fails_visibly(mocker):
    """Unexpected errors (e.g. TypeError, programming bugs) are not caught by transcript fallback."""
    fake_video_id = "test_vid_unexpected"

    mock_api = mocker.MagicMock()
    mock_api.list.side_effect = TypeError("Unexpected programming bug")
    mocker.patch("app.ingest.transcripter.YouTubeTranscriptApi", return_value=mock_api)

    mock_whisper = mocker.patch("app.ingest.transcripter.Transcripter.transcribe_with_whisper")

    with pytest.raises(TypeError, match="Unexpected programming bug"):
        Transcripter.get_transcript(fake_video_id)

    mock_whisper.assert_not_called()
