import pytest
import json
from langchain_core.documents import Document
from app.rag.engine import query_rag

def test_only_retrieved_context_placed_in_llm_prompt(mocker):
    """Only retrieved context chunks are placed in the LLM system prompt."""
    mock_doc = Document(
        page_content="Unique context sentence XYZ123.",
        metadata={"video_id": "vid_xyz", "title": "XYZ Video", "start_time": 50.0, "upload_date": "2023-01-01"}
    )
    mocker.patch("app.rag.engine.get_hybrid_context", return_value=[mock_doc])

    captured_messages = []
    mock_llm = mocker.MagicMock()
    def mock_stream(messages):
        captured_messages.extend(messages)
        yield mocker.MagicMock(content="Mocked answer referencing XYZ123.")
    mock_llm.stream.side_effect = mock_stream
    mocker.patch("app.rag.engine.get_llm", return_value=mock_llm)

    stream_gen = query_rag("Tell me about XYZ", channel_id="UC_test")
    chunks = list(stream_gen())

    assert len(captured_messages) == 2
    system_prompt = captured_messages[0].content
    assert "Unique context sentence XYZ123." in system_prompt
    assert "XYZ Video" in system_prompt

def test_citation_instructions_included_in_prompt(mocker):
    """Citation instructions are included in the LLM system prompt."""
    mock_doc = Document(
        page_content="Some content",
        metadata={"video_id": "vid_1", "title": "Vid 1", "start_time": 10.0}
    )
    mocker.patch("app.rag.engine.get_hybrid_context", return_value=[mock_doc])

    captured_messages = []
    mock_llm = mocker.MagicMock()
    mock_llm.stream.side_effect = lambda msgs: (captured_messages.extend(msgs) or [mocker.MagicMock(content="Answer")])
    mocker.patch("app.rag.engine.get_llm", return_value=mock_llm)

    stream_gen = query_rag("General question", channel_id="UC_test")
    list(stream_gen())

    system_prompt = captured_messages[0].content
    assert "Citations Policy" in system_prompt
    assert "https://youtube.com/watch?v={video_id}&t={seconds}" in system_prompt

def test_returned_source_metadata_contains_video_ids_and_timestamps(mocker):
    """First streamed chunk is METADATA with video IDs and timestamps."""
    mock_doc = Document(
        page_content="Sample content for metadata test.",
        metadata={"video_id": "vid_metadata_test", "title": "Metadata Video", "start_time": 125.0, "upload_date": "2023-03-15"}
    )
    mocker.patch("app.rag.engine.get_hybrid_context", return_value=[mock_doc])

    mock_llm = mocker.MagicMock()
    mock_llm.stream.return_value = [mocker.MagicMock(content="Mocked LLM token")]
    mocker.patch("app.rag.engine.get_llm", return_value=mock_llm)

    stream_gen = query_rag("How does metadata work?", channel_id="UC_test")
    first_chunk = next(stream_gen())

    assert first_chunk.startswith("METADATA:")
    metadata_json = first_chunk.replace("METADATA:", "").strip()
    sources = json.loads(metadata_json)
    assert len(sources) == 1
    assert sources[0]["video_id"] == "vid_metadata_test"
    assert sources[0]["start_time"] == 125.0
    assert sources[0]["title"] == "Metadata Video"

def test_empty_retrieval_leads_to_insufficient_information(mocker):
    """Empty retrieval leads to an 'insufficient information' response without calling LLM."""
    mocker.patch("app.rag.engine.get_hybrid_context", return_value=[])

    mock_llm = mocker.MagicMock()
    mocker.patch("app.rag.engine.get_llm", return_value=mock_llm)

    stream_gen = query_rag("Unknown topic that does not exist", channel_id="UC_test")
    chunks = list(stream_gen())

    full_output = "".join(chunks)
    assert "do not have enough information" in full_output
    # The LLM should not even have been called
    mock_llm.stream.assert_not_called()
