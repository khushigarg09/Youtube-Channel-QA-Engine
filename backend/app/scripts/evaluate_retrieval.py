"""
Retrieval evaluation script for YouTube Channel QA Engine.
Measures Recall@5, Recall@10, Mean Reciprocal Rank (MRR), and average retrieval latency.
Usage:
    python -m app.scripts.evaluate_retrieval
    python -m app.scripts.evaluate_retrieval --show-results
"""
import os
import sys
import json
import time
import argparse
import logging
from typing import List, Dict, Any
from app.rag.engine import get_hybrid_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_retrieval")

DEFAULT_EVAL_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "evaluation", "hussein_nasser_questions.json")
)

def evaluate(questions_file: str = DEFAULT_EVAL_FILE, show_results: bool = False, k_max: int = 10) -> Dict[str, Any]:
    if not os.path.exists(questions_file):
        print(f"Evaluation benchmark file not found: {questions_file}")
        sys.exit(1)

    with open(questions_file, "r", encoding="utf-8") as f:
        benchmarks = json.load(f)

    print(f"\n=======================================================")
    print(f"  Retrieval Evaluation Benchmark ({len(benchmarks)} questions)")
    print(f"  Benchmark file: {questions_file}")
    print(f"=======================================================\n")

    hits_at_5 = 0
    hits_at_10 = 0
    reciprocal_ranks = []
    latencies_ms = []

    for idx, item in enumerate(benchmarks, 1):
        q_id = item.get("id", f"q_{idx}")
        question = item["question"]
        expected_vids = set(item.get("expected_video_ids", []))

        # Measure retrieval latency
        start_time = time.perf_counter()
        retrieved_docs = get_hybrid_context(query_text=question, k=k_max)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        latencies_ms.append(elapsed_ms)

        retrieved_vids = [doc.metadata.get("video_id") for doc in retrieved_docs]

        # Calculate Recall@5 & Recall@10
        top_5_vids = set(retrieved_vids[:5])
        top_10_vids = set(retrieved_vids[:10])

        hit_5 = 1 if (expected_vids & top_5_vids) else 0
        hit_10 = 1 if (expected_vids & top_10_vids) else 0

        hits_at_5 += hit_5
        hits_at_10 += hit_10

        # Calculate Reciprocal Rank
        rr = 0.0
        for rank_0, vid in enumerate(retrieved_vids):
            if vid in expected_vids:
                rr = 1.0 / (rank_0 + 1)
                break
        reciprocal_ranks.append(rr)

        if show_results:
            print(f"[{idx}/{len(benchmarks)}] {q_id}: \"{question}\"")
            print(f"   Expected Video IDs: {list(expected_vids)}")
            print(f"   Retrieved {len(retrieved_docs)} chunks in {elapsed_ms:.2f}ms (MRR: {rr:.3f}, Hit@5: {hit_5}, Hit@10: {hit_10})")
            for r_idx, doc in enumerate(retrieved_docs[:5], 1):
                meta = doc.metadata
                print(f"     Rank {r_idx}: [{meta.get('video_id')}] t={meta.get('start_time')}s - {meta.get('title')}")
                snippet = doc.page_content.replace('\n', ' ')[:100]
                print(f"             \"{snippet}...\"")
            print()

    total_queries = len(benchmarks)
    recall_at_5 = (hits_at_5 / total_queries) if total_queries > 0 else 0.0
    recall_at_10 = (hits_at_10 / total_queries) if total_queries > 0 else 0.0
    mrr = (sum(reciprocal_ranks) / total_queries) if total_queries > 0 else 0.0
    avg_latency = (sum(latencies_ms) / total_queries) if total_queries > 0 else 0.0

    print("-------------------------------------------------------")
    print("                     RESULTS SUMMARY")
    print("-------------------------------------------------------")
    print(f"  Total Questions Tested  : {total_queries}")
    print(f"  Recall@5                : {recall_at_5:.4f} ({hits_at_5}/{total_queries})")
    print(f"  Recall@10               : {recall_at_10:.4f} ({hits_at_10}/{total_queries})")
    print(f"  Mean Reciprocal Rank    : {mrr:.4f}")
    print(f"  Average Latency         : {avg_latency:.2f} ms")
    print("=======================================================\n")

    return {
        "total_queries": total_queries,
        "recall_at_5": recall_at_5,
        "recall_at_10": recall_at_10,
        "mrr": mrr,
        "avg_latency_ms": avg_latency
    }

def main():
    parser = argparse.ArgumentParser(description="Evaluate Hybrid RAG Retrieval Quality")
    parser.add_argument("--file", type=str, default=DEFAULT_EVAL_FILE, help="Path to JSON questions file")
    parser.add_argument("--show-results", action="store_true", help="Print retrieved chunks for manual inspection")
    args = parser.parse_args()

    evaluate(questions_file=args.file, show_results=args.show_results)

if __name__ == "__main__":
    main()
