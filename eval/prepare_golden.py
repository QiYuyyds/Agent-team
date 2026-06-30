#!/usr/bin/env python
"""Prepare evaluation golden set from CRUD-RAG split_merged.json.

Converts each QA entry from questanswer_1doc/2docs/3docs into a golden
evaluation record with query, ground_truth_answer, and relevant_docs
(news full texts for content-based hit detection).

Usage:
    cd eval && python prepare_golden.py
"""

import json
import os
import sys

# ─── Paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(SCRIPT_DIR, "CRUD_RAG-main", "data", "crud_split", "split_merged.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "golden.jsonl")

# QA task types to process and their task_type labels
QA_TASK_MAP = {
    "questanswer_1doc": "1doc",
    "questanswer_2docs": "2doc",
    "questanswer_3docs": "3doc",
}

# News fields in each QA entry (order matters: news1, news2, news3)
NEWS_FIELDS = ["news1", "news2", "news3"]


def convert_entry(entry: dict, task_type: str, query_id: str) -> dict | None:
    """Convert a single CRUD-RAG QA entry to a golden record.

    Returns None if the entry is missing required fields.
    """
    query = entry.get("questions", "")
    answer = entry.get("answers", "")
    if not query or not query.strip():
        return None

    relevant_docs: list[str] = []
    for field in NEWS_FIELDS:
        doc = entry.get(field, "")
        if doc and doc.strip():
            relevant_docs.append(doc)

    if not relevant_docs:
        return None

    return {
        "query_id": query_id,
        "query": query,
        "ground_truth_answer": answer,
        "relevant_docs": relevant_docs,
        "num_relevant_docs": len(relevant_docs),
        "task_type": task_type,
    }


def write_golden_jsonl(records: list[dict], output_path: str) -> int:
    """Write golden records to JSONL file.

    Returns the number of records written.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records)


def main() -> None:
    if not os.path.exists(INPUT_PATH):
        print(f"ERROR: Input file not found: {INPUT_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading: {INPUT_PATH}")
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    records: list[dict] = []
    for task_key, task_type in QA_TASK_MAP.items():
        entries = data.get(task_key, [])
        for idx, entry in enumerate(entries):
            query_id = f"{task_type}_{idx:04d}"
            record = convert_entry(entry, task_type, query_id)
            if record is not None:
                records.append(record)
        print(f"  {task_key}: {len(entries)} entries → {sum(1 for r in records if r['task_type'] == task_type)} golden records")

    print(f"Total golden records: {len(records)}")

    # Write output
    written = write_golden_jsonl(records, OUTPUT_PATH)
    print(f"Written: {OUTPUT_PATH} ({written} lines)")

    # Quick validation
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            obj = json.loads(line)
            assert "query_id" in obj, f"Line {i}: missing query_id"
            assert "query" in obj, f"Line {i}: missing query"
            assert "ground_truth_answer" in obj, f"Line {i}: missing ground_truth_answer"
            assert "relevant_docs" in obj, f"Line {i}: missing relevant_docs"
            assert "num_relevant_docs" in obj, f"Line {i}: missing num_relevant_docs"
            assert "task_type" in obj, f"Line {i}: missing task_type"
            assert len(obj["relevant_docs"]) == obj["num_relevant_docs"], (
                f"Line {i}: relevant_docs length {len(obj['relevant_docs'])} "
                f"!= num_relevant_docs {obj['num_relevant_docs']}"
            )
    print(f"Validation passed: all {written} lines are valid JSON with required fields")


if __name__ == "__main__":
    main()
