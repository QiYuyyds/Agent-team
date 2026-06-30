## ADDED Requirements

### Requirement: Evaluation corpus preparation

The system SHALL provide a script (`eval/prepare_corpus.py`) that extracts unique news documents from CRUD-RAG's `split_merged.json` and outputs a JSONL corpus file (`eval/corpus.jsonl`) ready for RAG ingestion.

- Input: `eval/CRUD_RAG-main/data/crud_split/split_merged.json`
- Output: `eval/corpus.jsonl`, one JSON object per line with fields `doc_id` (string, zero-padded sequential), `content` (full news text), `source` (literal `"crud-rag"`)
- Deduplication: documents SHALL be deduplicated by first 100 characters of content
- Source tasks: `questanswer_1doc`, `questanswer_2docs`, `questanswer_3docs` (fields `news1`, `news2`, `news3`)
- Expected output: ~3,050 unique documents

#### Scenario: Extract corpus from split_merged.json

- **WHEN** `prepare_corpus.py` is executed with the correct CRUD-RAG path
- **THEN** `eval/corpus.jsonl` is created with approximately 3,050 lines
- **AND** each line is valid JSON with `doc_id`, `content`, and `source` fields
- **AND** no two lines have the same first 100 characters in `content`

#### Scenario: Skip non-QA tasks

- **WHEN** the script processes `split_merged.json`
- **THEN** only `questanswer_1doc`, `questanswer_2docs`, `questanswer_3docs` keys are processed
- **AND** `event_summary`, `continuing_writing`, `hallu_modified` keys are skipped

### Requirement: Evaluation golden set preparation

The system SHALL provide a script (`eval/prepare_golden.py`) that converts CRUD-RAG QA data into an evaluation golden set (`eval/golden.jsonl`).

- Input: `eval/CRUD_RAG-main/data/crud_split/split_merged.json`
- Output: `eval/golden.jsonl`, one JSON object per line
- Each golden entry SHALL contain: `query_id` (string), `query` (string, from `questions` field), `ground_truth_answer` (string, from `answers` field), `relevant_docs` (list of news full texts from `news1`/`news2`/`news3`), `num_relevant_docs` (integer), `task_type` (string: `"1doc"`/`"2doc"`/`"3doc"`)
- Expected output: ~2,394 golden entries

#### Scenario: Convert QA entries to golden format

- **WHEN** `prepare_golden.py` is executed
- **THEN** `eval/golden.jsonl` is created with approximately 2,394 lines
- **AND** each line contains `query_id`, `query`, `ground_truth_answer`, `relevant_docs`, `num_relevant_docs`, `task_type`
- **AND** `relevant_docs` length matches `num_relevant_docs` for each entry

#### Scenario: Handle multi-document QA entries

- **WHEN** processing a `questanswer_2docs` entry
- **THEN** `relevant_docs` contains 2 elements (from `news1` and `news2`)
- **AND** `num_relevant_docs` is 2
- **AND** `task_type` is `"2doc"`

### Requirement: Content-based hit detection

The system SHALL provide a content matching function that determines whether a retrieved chunk is relevant by substring matching against golden relevant documents.

- Function signature: `is_hit(chunk_content: str, relevant_docs: list[str], prefix_len: int = 50) -> bool`
- Matching logic: extract first `prefix_len` characters of `chunk_content`, check if it appears as a substring in any relevant doc; also check if the first `prefix_len` characters of any relevant doc appear in `chunk_content` (bidirectional matching)
- Empty or whitespace-only prefixes SHALL return `False`

#### Scenario: Chunk from relevant document

- **WHEN** `is_hit` is called with a chunk content that is a substring of a relevant document
- **THEN** the function returns `True`

#### Scenario: Chunk from irrelevant document

- **WHEN** `is_hit` is called with a chunk content that does not appear in any relevant document
- **THEN** the function returns `False`

#### Scenario: Empty chunk content

- **WHEN** `is_hit` is called with an empty or whitespace-only `chunk_content`
- **THEN** the function returns `False`

### Requirement: Retrieval layer metrics

The system SHALL implement four retrieval-layer metrics that operate on retrieved chunks and relevant documents without requiring LLM calls.

- `recall_at_k(retrieved: list[str], relevant_docs: list[str], k: int) -> float`: fraction of relevant documents found in top-K retrieved chunks
- `precision_at_k(retrieved: list[str], relevant_docs: list[str], k: int) -> float`: fraction of top-K retrieved chunks that are relevant
- `mrr(retrieved: list[str], relevant_docs: list[str]) -> float`: reciprocal rank of first relevant chunk
- `ndcg_at_k(retrieved: list[str], relevant_docs: list[str], k: int) -> float`: normalized discounted cumulative gain at K
- All metrics SHALL return 0.0 when `retrieved` is empty
- All metrics SHALL use `is_hit()` for relevance determination

#### Scenario: Perfect retrieval

- **WHEN** all relevant documents are retrieved in top-K positions
- **THEN** `recall_at_k` returns 1.0
- **AND** `precision_at_k` returns `num_relevant / k`

#### Scenario: No relevant results

- **WHEN** none of the retrieved chunks match any relevant document
- **THEN** `recall_at_k` returns 0.0
- **AND** `mrr` returns 0.0
- **AND** `ndcg_at_k` returns 0.0

#### Scenario: Partial retrieval with ranking

- **WHEN** retrieved chunks contain 1 of 2 relevant documents, with the hit at position 2
- **THEN** `recall_at_k` returns 0.5
- **AND** `mrr` returns 0.5 (1/2)
- **AND** `ndcg_at_k` reflects the discounted position

### Requirement: Generation layer metrics via LLM-as-judge

The system SHALL implement three generation-layer metrics using LLM-as-judge, each returning a float score between 0.0 and 1.0.

- `faithfulness(question: str, answer: str, context: str, llm_fn: callable) -> float`: evaluates whether the answer is fully grounded in the provided context (no fabrication)
- `answer_relevance(question: str, answer: str, llm_fn: callable) -> float`: evaluates whether the answer directly addresses the question
- `answer_quality(ground_truth: str, generated: str, llm_fn: callable) -> float`: evaluates semantic consistency between generated answer and ground truth answer
- Each metric SHALL use a dedicated prompt template that constrains the LLM to output only a numeric score
- The LLM function `llm_fn(system_prompt: str, user_msg: str) -> str` SHALL be the project's existing DashScope generate function

#### Scenario: Faithful answer

- **WHEN** the generated answer only contains information present in the retrieved context
- **THEN** `faithfulness` returns a score close to 1.0

#### Scenario: Hallucinated answer

- **WHEN** the generated answer contains information not present in the retrieved context
- **THEN** `faithfulness` returns a score close to 0.0

#### Scenario: Irrelevant answer

- **WHEN** the generated answer does not address the question
- **THEN** `answer_relevance` returns a score close to 0.0

### Requirement: Three-mode retrieval evaluation

The system SHALL support evaluating RAG retrieval in three modes: dense (Milvus only), bm25 (ES only), and hybrid (Milvus + ES + RRF).

- Mode switching SHALL be achieved by saving original backend function references and re-injecting via `set_milvus_backend()` / `set_es_backend()`
- Dense mode: `set_milvus_backend(real_fn)` + `set_es_backend(None)`
- BM25 mode: `set_milvus_backend(None)` + `set_es_backend(real_fn)`
- Hybrid mode: `set_milvus_backend(real_fn)` + `set_es_backend(real_fn)`
- After each mode switch, the system SHALL verify `hybrid.mode()` returns the expected mode string
- Corpus ingestion SHALL happen once before any mode evaluation (all modes share the same indexed data)

#### Scenario: Switch to dense mode

- **WHEN** the evaluation runner switches to dense mode
- **THEN** `hybrid.mode()` returns `"semantic"`
- **AND** only Milvus search path is active

#### Scenario: Switch to hybrid mode

- **WHEN** the evaluation runner switches to hybrid mode
- **THEN** `hybrid.mode()` returns `"hybrid"`
- **AND** both Milvus and ES search paths are active

#### Scenario: Shared corpus across modes

- **WHEN** the evaluation runner completes corpus ingestion
- **THEN** all three modes use the same indexed chunks in PG/Milvus/ES
- **AND** no re-ingestion is needed between mode switches

### Requirement: Evaluation runner with limit parameter

The system SHALL provide `eval/run_eval.py` that executes the full evaluation pipeline with support for a `--limit N` parameter for sub-sampling.

- The script SHALL: (1) load corpus.jsonl and golden.jsonl, (2) ingest corpus into RAG, (3) for each mode in [dense, bm25, hybrid], for each golden entry, execute search + metrics computation, (4) output per-mode results JSON and a Markdown comparison report
- `--limit N` SHALL randomly sample N golden entries (seed=42 for reproducibility) for quick validation
- Without `--limit`, all 2,394 golden entries SHALL be evaluated
- Results SHALL be saved to `eval/results/<mode>_results.json` and `eval/results/comparison_report.md`
- Progress SHALL be logged to console with current mode, entry index, and running metrics average

#### Scenario: Full evaluation run

- **WHEN** `run_eval.py` is executed without `--limit`
- **THEN** all 2,394 golden entries are evaluated across 3 modes
- **AND** results are saved to `eval/results/`

#### Scenario: Limited evaluation run

- **WHEN** `run_eval.py --limit 200` is executed
- **THEN** 200 randomly sampled golden entries are evaluated across 3 modes
- **AND** the same 200 entries are used for all 3 modes (consistent comparison)

### Requirement: Evaluation comparison report

The system SHALL generate a Markdown comparison report (`eval/results/comparison_report.md`) summarizing all 7 metrics across 3 modes.

- The report SHALL contain a table with rows = metrics, columns = modes (dense/bm25/hybrid)
- Each cell SHALL show the mean score across all evaluated entries
- The report SHALL include a summary section highlighting the best-performing mode for each metric
- The report SHALL include run metadata: timestamp, total entries, limit (if any), RAG config (top_k, chunk_size, rewrite_enabled, rerank_enabled)

#### Scenario: Report generation after evaluation

- **WHEN** all three modes complete evaluation
- **THEN** `comparison_report.md` is generated with a 7×3 metrics table
- **AND** each cell contains a float value rounded to 4 decimal places
- **AND** the best mode for each metric is highlighted
