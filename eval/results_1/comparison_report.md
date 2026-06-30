# RAG Evaluation Comparison Report

## Run Metadata

- **Timestamp**: 2026-06-30 16:14:03
- **Total Entries**: 200
- **Limit**: 200
- **Top-K**: 5
- **Chunk Size**: 200
- **Chunk Overlap**: 50
- **Rewrite Enabled**: True
- **Rerank Enabled**: True

## Metrics Comparison

| Metric | dense | bm25 | hybrid |
|--------|--------|--------|--------|
| recall_at_k | **0.7700** | 0.7617 | 0.7492 |
| precision_at_k | **0.6058** | 0.6042 | 0.6058 |
| mrr | **0.8442** | 0.8325 | 0.8108 |
| ndcg_at_k | 0.7337 | **0.7376** | 0.7154 |
| faithfulness | **0.9925** | 0.9825 | 0.9840 |
| answer_relevance | 0.9235 | **0.9295** | 0.9225 |
| answer_quality | 0.7605 | **0.7745** | 0.7620 |

## Best Mode Summary

- **recall_at_k**: dense
- **precision_at_k**: dense
- **mrr**: dense
- **ndcg_at_k**: bm25
- **faithfulness**: dense
- **answer_relevance**: bm25
- **answer_quality**: bm25

## Per-Mode Details

### dense
- Total entries: 200
- Generation-evaluated entries: 200
- Averages:
  - recall_at_k: 0.7700
  - precision_at_k: 0.6058
  - mrr: 0.8442
  - ndcg_at_k: 0.7337
  - faithfulness: 0.9925
  - answer_relevance: 0.9235
  - answer_quality: 0.7605

### bm25
- Total entries: 200
- Generation-evaluated entries: 200
- Averages:
  - recall_at_k: 0.7617
  - precision_at_k: 0.6042
  - mrr: 0.8325
  - ndcg_at_k: 0.7376
  - faithfulness: 0.9825
  - answer_relevance: 0.9295
  - answer_quality: 0.7745

### hybrid
- Total entries: 200
- Generation-evaluated entries: 200
- Averages:
  - recall_at_k: 0.7492
  - precision_at_k: 0.6058
  - mrr: 0.8108
  - ndcg_at_k: 0.7154
  - faithfulness: 0.9840
  - answer_relevance: 0.9225
  - answer_quality: 0.7620
