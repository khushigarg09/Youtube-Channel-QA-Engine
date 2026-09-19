import re
from typing import List, Dict, Set, Optional
from collections import Counter
import logging

logger = logging.getLogger(__name__)

# Standard stop words to filter out trivial single tokens
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such", "than",
    "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't",
    "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's",
    "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom",
    "why", "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll",
    "you're", "you've", "your", "yours", "yourself", "yourselves", "today", "video",
    "like", "subscribe", "channel", "welcome", "guys", "going", "really", "actually",
    "something", "everything", "anything", "nothing", "someone", "everyone", "look",
    "make", "know", "see", "think", "want", "take", "come", "give", "talk"
}

class TopicExtractor:
    """
    Dynamic topic and keyphrase extractor.
    Extracts key domain concepts dynamically from video titles, descriptions, and transcripts
    without relying on any hardcoded domain list.
    """

    @classmethod
    def extract_salient_topics_from_metadata(cls, title: str, description: str = "") -> List[str]:
        """
        Extracts prominent candidate topic phrases from a video's title and description.
        Captures camelCase terms, capitalized multi-word phrases, hyphenated terms, and acronyms.
        """
        candidates: Set[str] = set()
        combined = f"{title}. {description[:500]}"
        
        # 1. Capitalized multi-word phrases (e.g. "Machine Learning", "FastAPI Tutorial", "Sourdough Bread")
        multi_word_caps = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', combined)
        for term in multi_word_caps:
            cleaned = term.strip()
            if len(cleaned) > 3 and not all(w.lower() in STOP_WORDS for w in cleaned.split()):
                candidates.add(cleaned)

        # 2. Acronyms & technical abbreviations (e.g. "RAG", "LLM", "API", "CUDA", "SEO", "ETF", "GPU")
        acronyms = re.findall(r'\b([A-Z0-9]{2,6})\b', combined)
        for term in acronyms:
            if term.lower() not in {"THE", "AND", "FOR", "YOU", "NOT", "CAN", "OUT", "ALL", "HOW", "NEW"}:
                candidates.add(term)

        # 3. CamelCase or MixedCase technical tokens (e.g. "LangChain", "ChromaDB", "PyTorch", "NextJS", "TypeScript")
        camel_tokens = re.findall(r'\b([A-Z][a-z]+[A-Z0-9][A-Za-z0-9]*)\b', combined)
        for token in camel_tokens:
            candidates.add(token)

        # 4. Filter and clean candidate list
        filtered = [
            cand for cand in candidates 
            if len(cand) >= 2 and cand.lower() not in STOP_WORDS
        ]
        return list(filtered)[:15]

    @classmethod
    def find_topic_occurrences_in_chunks(
        cls, 
        chunks: List[Dict], 
        candidate_topics: List[str],
        custom_topics: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Scans transcript chunks for topic occurrences and returns timestamped topic records.
        """
        # Combine candidate topics with any custom user-provided topics
        all_topics = set(candidate_topics)
        if custom_topics:
            for t in custom_topics:
                if t and t.strip():
                    all_topics.add(t.strip())

        if not all_topics:
            return []

        occurrences = []
        # Pre-compile regex for each topic for fast boundary-aware matching
        compiled_patterns = {}
        for topic in all_topics:
            escaped = re.escape(topic)
            # Match word boundary or token
            compiled_patterns[topic] = re.compile(rf'(?:\b|_){escaped}(?:\b|_)', re.IGNORECASE)

        last_seen_per_topic: Dict[str, float] = {}

        for chunk in chunks:
            text = chunk.get("text", "")
            start_time = float(chunk.get("start_time", 0.0))

            for topic, pattern in compiled_patterns.items():
                if pattern.search(text):
                    # Debounce: avoid duplicate topic mentions within 30 seconds in the same video
                    last_seen = last_seen_per_topic.get(topic, -999.0)
                    if start_time - last_seen >= 30.0:
                        occurrences.append({
                            "name": topic,
                            "timestamp": start_time
                        })
                        last_seen_per_topic[topic] = start_time

        return occurrences
