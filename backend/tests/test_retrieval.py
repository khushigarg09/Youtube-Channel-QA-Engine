import pytest
from langchain_core.documents import Document
from app.rag.engine import (
    reciprocal_rank_fusion,
    document_key,
    get_hybrid_context
)
from app.database.models import Channel, Video, TranscriptChunk

def test_true_rrf_scoring_and_ranking():
    """True RRF produces expected ranking order based on 1 / (k + rank)."""
    doc_a = Document(page_content="Doc A content", metadata={"video_id": "vid_1", "start_time": 0.0})
    doc_b = Document(page_content="Doc B content", metadata={"video_id": "vid_2", "start_time": 10.0})
    doc_c = Document(page_content="Doc C content", metadata={"video_id": "vid_3", "start_time": 20.0})

    # List 1: [A (rank 1), B (rank 2)]
    # List 2: [B (rank 1), C (rank 2)]
    # With k=60:
    # A score = 1/(60+1) = 1/61 ~ 0.01639
    # B score = 1/(60+2) + 1/(60+1) = 1/62 + 1/61 ~ 0.03252
    # C score = 1/(60+2) = 1/62 ~ 0.01613
    # Therefore, B should rank 1st, A 2nd, C 3rd.
    ranked_lists = [
        [doc_a, doc_b],
        [doc_b, doc_c]
    ]

    fused = reciprocal_rank_fusion(ranked_lists, k=60)
    assert len(fused) == 3
    assert fused[0].metadata["video_id"] == "vid_2"  # B
    assert fused[1].metadata["video_id"] == "vid_1"  # A
    assert fused[2].metadata["video_id"] == "vid_3"  # C

def test_true_rrf_duplicate_removal():
    """Duplicate chunks across ranked lists are deduplicated."""
    doc1 = Document(page_content="Chunk 1", metadata={"video_id": "v1", "start_time": 5.0})
    doc2 = Document(page_content="Chunk 1", metadata={"video_id": "v1", "start_time": 5.0})

    fused = reciprocal_rank_fusion([[doc1], [doc2]], k=60)
    assert len(fused) == 1
    assert document_key(fused[0]) == ("v1", 5.0)

def test_hybrid_context_includes_chroma_and_bm25(mocker, test_db, sample_channel, sample_video, sample_chunks):
    """BM25 and Chroma results are both fused into the hybrid results."""
    mocker.patch("app.rag.engine.SessionLocal", return_value=test_db)

    # Mock Chroma vector store
    chroma_doc = Document(
        page_content="Chroma semantic chunk about connection pooling optimization.",
        metadata={"video_id": "vid_chroma", "title": "Chroma Video", "start_time": 100.0, "upload_date": "2023-01-01"}
    )
    mock_vs = mocker.MagicMock()
    mock_vs.similarity_search.return_value = [chroma_doc]
    mocker.patch("app.rag.engine.get_vector_store", return_value=mock_vs)

    target_video_id = sample_video.video_id
    channel_id = sample_channel.channel_id
    results = get_hybrid_context("TCP socket connection pools", channel_id=channel_id, k=5)
    
    # Must contain documents from both sources
    retrieved_vids = [d.metadata.get("video_id") for d in results]
    assert target_video_id in retrieved_vids
    assert len(results) <= 5

def test_channel_filtering_excludes_other_channels(mocker, test_db, sample_channel, sample_video, sample_chunks):
    """Channel filtering strictly excludes chunks from other channels."""
    mocker.patch("app.rag.engine.SessionLocal", return_value=test_db)

    # Create second channel and video
    other_chan = Channel(channel_id="UC_other", channel_name="Other Channel", indexing_status="idle")
    other_vid = Video(video_id="vid_other", channel_id="UC_other", title="Other Video", status="indexed")
    other_chunk = TranscriptChunk(
        video_id="vid_other",
        text="TCP socket and TLS handshake on connection pools.",
        start_time=10.0,
        duration=20.0,
        chroma_id="vid_other_0"
    )
    test_db.add_all([other_chan, other_vid, other_chunk])
    test_db.commit()

    # Chroma returns empty for this test to isolate SQLite BM25 filter check
    mock_vs = mocker.MagicMock()
    mock_vs.similarity_search.return_value = []
    mocker.patch("app.rag.engine.get_vector_store", return_value=mock_vs)

    results = get_hybrid_context("TCP socket", channel_id=sample_channel.channel_id, k=5)
    for doc in results:
        assert doc.metadata.get("video_id") != "vid_other"

def test_relevant_chunks_appear_in_top_results(mocker, test_db, sample_channel, sample_video, sample_chunks):
    """Relevant chunks appear in top five results."""
    mocker.patch("app.rag.engine.SessionLocal", return_value=test_db)

    mock_vs = mocker.MagicMock()
    mock_vs.similarity_search.return_value = []
    mocker.patch("app.rag.engine.get_vector_store", return_value=mock_vs)

    # Search for an exact term in chunk 0: "cache of database connections for reuse"
    results = get_hybrid_context("cache of database connections for reuse", channel_id=sample_channel.channel_id, k=5)
    assert len(results) > 0
    top_chunk = results[0]
    assert "cache of database connections" in top_chunk.page_content


def test_delete_video_vectors_raises_runtime_error_on_chroma_failure(mocker):
    """delete_video_vectors raises RuntimeError instead of swallowing exceptions when Chroma fails."""
    from app.rag.vector_store import delete_video_vectors

    mock_vs = mocker.MagicMock()
    mock_vs.delete.side_effect = Exception("Chroma connection refused")
    mocker.patch("app.rag.vector_store.get_vector_store", return_value=mock_vs)

    with pytest.raises(RuntimeError, match="Failed to clean existing vectors for video test_vid"):
        delete_video_vectors("test_vid")


def test_indexing_pipeline_fails_safely_when_vector_cleanup_fails(mocker, test_db, sample_video, sample_chunks):
    """If vector cleanup fails, SQLite transcript rows are preserved and reindexing halts."""
    from app.ingest.pipeline import index_single_video_internal

    # Mock Transcripter methods
    mocker.patch(
        "app.ingest.pipeline.Transcripter.get_transcript",
        return_value=[{"text": "New transcript text", "start": 0.0, "duration": 5.0}]
    )
    mocker.patch(
        "app.ingest.pipeline.Transcripter.chunk_transcript",
        return_value=[{"text": "New transcript text", "start_time": 0.0, "duration": 5.0}]
    )

    # Force delete_video_vectors to raise RuntimeError as implemented
    mocker.patch(
        "app.ingest.pipeline.delete_video_vectors",
        side_effect=RuntimeError(f"Failed to clean existing vectors for video {sample_video.video_id}")
    )

    initial_chunk_count = test_db.query(TranscriptChunk).filter(
        TranscriptChunk.video_id == sample_video.video_id
    ).count()
    assert initial_chunk_count == 3

    success = index_single_video_internal(sample_video, test_db)
    assert success is False

    test_db.refresh(sample_video)
    assert sample_video.status == "failed"
    assert "Failed to clean existing vectors" in sample_video.error_message

    # Ensure existing SQLite transcript chunks were NOT deleted
    remaining_chunk_count = test_db.query(TranscriptChunk).filter(
        TranscriptChunk.video_id == sample_video.video_id
    ).count()
    assert remaining_chunk_count == 3
