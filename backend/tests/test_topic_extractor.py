import pytest
from app.services.topic_extractor import TopicExtractor

def test_expected_topics_found_from_metadata():
    """Expected topics are found from fixture metadata."""
    title = "Building Fast APIs with FastAPI and SQLite"
    description = "In this tutorial we dive into Machine Learning, RAG architecture, and database optimization."

    topics = TopicExtractor.extract_salient_topics_from_metadata(title, description)
    # Acronyms and capitalized phrases
    assert any("FastAPI" in t for t in topics)
    assert any("Machine Learning" in t for t in topics)
    assert any("RAG" in t for t in topics)

def test_duplicate_topics_normalized():
    """Duplicate topics are normalized across candidate extraction and custom topics."""
    chunks = [
        {"text": "We are studying SQLite and database design.", "start_time": 10.0, "duration": 5.0},
        {"text": "More discussion on SQLite database internals.", "start_time": 50.0, "duration": 5.0},
    ]
    candidate_topics = ["SQLite", "SQLite", "Database Design"]
    custom_topics = ["SQLite", "database design"]

    occurrences = TopicExtractor.find_topic_occurrences_in_chunks(
        chunks=chunks,
        candidate_topics=candidate_topics,
        custom_topics=custom_topics
    )
    
    # Each topic should only be tracked once per timestamp interval
    names_at_10 = [occ["name"].lower() for occ in occurrences if occ["timestamp"] == 10.0]
    assert names_at_10.count("sqlite") == 1

def test_topic_timestamps_match_correct_transcript_chunk():
    """Topic timestamps match the correct transcript chunk."""
    chunks = [
        {"text": "Welcome to the video. Today is a great day.", "start_time": 0.0, "duration": 10.0},
        {"text": "Now let us discuss Kubernetes cluster architecture.", "start_time": 45.0, "duration": 15.0},
        {"text": "Moving on to Docker container optimization.", "start_time": 120.0, "duration": 20.0},
    ]
    candidate_topics = ["Kubernetes", "Docker"]

    occurrences = TopicExtractor.find_topic_occurrences_in_chunks(
        chunks=chunks,
        candidate_topics=candidate_topics
    )

    k8s_occ = [o for o in occurrences if o["name"] == "Kubernetes"]
    docker_occ = [o for o in occurrences if o["name"] == "Docker"]

    assert len(k8s_occ) == 1
    assert k8s_occ[0]["timestamp"] == 45.0

    assert len(docker_occ) == 1
    assert docker_occ[0]["timestamp"] == 120.0
