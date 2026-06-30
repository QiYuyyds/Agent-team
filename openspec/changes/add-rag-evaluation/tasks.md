## 1. Data Preparation Scripts

- [x] 1.1 Create `eval/prepare_corpus.py`: read `split_merged.json`, extract unique news docs from `questanswer_1doc/2docs/3docs` (fields news1/news2/news3), deduplicate by first 100 chars, output `eval/corpus.jsonl` with `{doc_id, content, source}` per line
- [x] 1.2 Create `eval/prepare_golden.py`: read `split_merged.json`, convert each QA entry to `{query_id, query, ground_truth_answer, relevant_docs, num_relevant_docs, task_type}`, output `eval/golden.jsonl`
- [x] 1.3 Run both scripts and verify outputs: corpus.jsonl ~3,050 lines, golden.jsonl ~2,394 lines, each line valid JSON

## 2. Metrics Module

- [x] 2.1 Create `eval/metrics.py` with `is_hit(chunk_content, relevant_docs, prefix_len=50) -> bool`: bidirectional substring matching, empty content returns False
- [x] 2.2 Implement retrieval metrics: `recall_at_k`, `precision_at_k`, `mrr`, `ndcg_at_k` — all using `is_hit` for relevance, returning 0.0 on empty input
- [x] 2.3 Implement generation metrics: `faithfulness(question, answer, context, llm_fn)`, `answer_relevance(question, answer, llm_fn)`, `answer_quality(ground_truth, generated, llm_fn)` — each with dedicated LLM-as-judge prompt template, returning float 0.0-1.0
- [x] 2.4 Write unit tests for `is_hit`, `recall_at_k`, `mrr`, `ndcg_at_k` with known inputs/outputs (perfect retrieval, no hits, partial retrieval)

## 3. Evaluation Runner

- [x] 3.1 Create `eval/run_eval.py` skeleton: argparse for `--limit N`, load corpus.jsonl and golden.jsonl, setup Python path to import backend modules (RAGService, HybridStore)
- [x] 3.2 Implement corpus ingestion: loop over corpus.jsonl, call `rag_service.ingest(doc_content)` for each, log progress, skip duplicates (RAGEngine auto-deduplicates by sha256)
- [x] 3.3 Implement mode switching: save original `_milvus_search_fn`/`_es_search_fn`/`_milvus_insert_fn`/`_es_index_fn` references, implement `switch_mode(mode)` that re-injects via `set_milvus_backend()`/`set_es_backend()` and verifies `hybrid.mode()` returns expected string
- [x] 3.4 Implement evaluation loop: for each mode in [dense, bm25, hybrid], for each golden entry, call `rag_service.search(query)` → extract retrieved chunk contents → compute 4 retrieval metrics → compute 3 generation metrics (if answer is non-empty) → collect results
- [x] 3.5 Implement `--limit N` sampling: use `random.seed(42)` + `random.sample()` to select N golden entries, use same subset across all 3 modes
- [x] 3.6 Implement progress logging: print mode, entry index, query_id, and running metric averages every 50 entries

## 4. Report Generation

- [x] 4.1 Implement per-mode JSON output: save `eval/results/<mode>_results.json` with per-entry metrics + mode-level averages
- [x] 4.2 Implement Markdown comparison report: generate `eval/results/comparison_report.md` with 7×3 metrics table (rows=metrics, columns=modes), best-mode highlighting, run metadata (timestamp, entry count, RAG config)

## 5. Verification & Execution

- [x] 5.1 Verify infrastructure: ensure Docker Compose (PG + Milvus + ES) is running, backend FastAPI is started with DashScope API keys configured
- [x] 5.2 Run `run_eval.py --limit 200` to validate the full pipeline: verify corpus ingestion succeeds, mode switching works, metrics are computed, report is generated
- [x] 5.3 Inspect 200-sample results: check for obvious anomalies (all zeros, all ones, NaN values), verify content matching is working correctly
- [ ] 5.4 Run full evaluation `run_eval.py` (no limit): 2,394 entries × 3 modes, monitor progress, collect final results
- [x] 5.5 Review comparison report: analyze dense vs bm25 vs hybrid performance, document findings
