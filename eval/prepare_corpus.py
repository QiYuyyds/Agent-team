#!/usr/bin/env python
"""Prepare evaluation corpus from CRUD-RAG split_merged.json.

Extracts unique news documents from questanswer_1doc/2docs/3docs entries,
deduplicates by first 100 characters of content, and outputs a JSONL corpus
file ready for RAG ingestion.

Usage:
    cd eval && python prepare_corpus.py
"""

import json
import os
import sys

# ─── Paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(SCRIPT_DIR, "CRUD_RAG-main", "data", "crud_split", "split_merged.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "corpus.jsonl")

# QA task types to process (skip event_summary, continuing_writing, hallu_modified)
QA_TASK_KEYS = ["questanswer_1doc", "questanswer_2docs", "questanswer_3docs"]

# News fields in each QA entry
NEWS_FIELDS = ["news1", "news2", "news3"]

# Deduplication prefix length
DEDUP_PREFIX_LEN = 100


def extract_unique_docs(data: dict) -> list[str]:
    """Extract unique news documents from QA entries, deduplicated by first 100 chars.

    Returns an ordered list of unique news document strings.
    """
    seen_prefixes: set[str] = set()
    unique_docs: list[str] = []

    for task_key in QA_TASK_KEYS:
        entries = data.get(task_key, [])
        for entry in entries:
            for field in NEWS_FIELDS:
                content = entry.get(field, "")
                if not content or not content.strip():
                    continue
                prefix = content[:DEDUP_PREFIX_LEN].strip()
                if not prefix:
                    continue
                if prefix in seen_prefixes:
                    continue
                seen_prefixes.add(prefix)
                unique_docs.append(content)

    return unique_docs


def write_corpus_jsonl(docs: list[str], output_path: str) -> int:
    """Write unique documents to JSONL file with sequential doc_ids.

    Returns the number of documents written.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, content in enumerate(docs):
            doc_id = f"doc_{idx:05d}"
            record = {
                "doc_id": doc_id,
                "content": content,
                "source": "crud-rag",
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(docs)


def main() -> None:
    if not os.path.exists(INPUT_PATH):
        print(f"ERROR: Input file not found: {INPUT_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading: {INPUT_PATH}")
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Verify expected keys exist
    for key in QA_TASK_KEYS:
        count = len(data.get(key, []))
        print(f"  {key}: {count} entries")

    # Extract unique documents
    unique_docs = extract_unique_docs(data)
    print(f"Unique documents (dedup by first {DEDUP_PREFIX_LEN} chars): {len(unique_docs)}")

    # Write output
    written = write_corpus_jsonl(unique_docs, OUTPUT_PATH)
    print(f"Written: {OUTPUT_PATH} ({written} lines)")

    # Quick validation: verify each line is valid JSON
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            obj = json.loads(line)
            assert "doc_id" in obj, f"Line {i}: missing doc_id"
            assert "content" in obj, f"Line {i}: missing content"
            assert "source" in obj, f"Line {i}: missing source"
            assert obj["source"] == "crud-rag", f"Line {i}: unexpected source={obj['source']}"
    print(f"Validation passed: all {written} lines are valid JSON with required fields")


if __name__ == "__main__":
    main()
