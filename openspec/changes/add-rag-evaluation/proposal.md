## Why

项目已具备完整的三路混合 RAG 检索能力（Milvus 语义 + ES BM25 + RRF 融合），但缺少系统化的效果评测体系。无法量化回答"dense vs bm25 vs hybrid 哪个召回更好""Reranker 提升了多少""检索结果质量如何"等关键问题。引入 RAG 评测体系是工程化项目的必备环节，也是后续参数调优和组件迭代的数据基座。

## What Changes

- 新增 RAG 评测数据集：基于 CRUD-RAG 开源中文基准数据集的 `split_merged.json` 子集（2,394 条 QA + 3,050 篇新闻文档），不使用全量 80k 语料库，QA 自带新闻文档互为干扰项
- 新增数据准备脚本 `eval/prepare_corpus.py`：从 CRUD-RAG 提取 3,050 篇独立新闻文档，格式化为可入库的 JSONL 语料库
- 新增数据准备脚本 `eval/prepare_golden.py`：从 CRUD-RAG 转换 2,394 条 QA 为评测标注集，包含 query、ground_truth_answer、relevant_docs（新闻原文，用于内容匹配判定命中）
- 新增指标计算模块 `eval/metrics.py`：实现 7 个评测指标
  - 检索层（纯计算）：Recall@K、Precision@K、MRR、NDCG
  - 生成层（LLM-as-judge）：Faithfulness、Answer Relevance、Answer
- 新增评测运行脚本 `eval/run_eval.py`：支持三种检索模式（dense / bm25 / hybrid）切换，逐条跑检索+生成+指标计算，输出对比报告
- 新增内容匹配函数：通过 chunk 前 50 字与 relevant_docs 子串匹配判定检索命中，无需 chunk_id 级标注

## Capabilities

### New Capabilities

- `rag-evaluation`: RAG 系统效果评测能力，包括评测数据集管理、检索层指标计算（Recall@K/Precision@K/MRR/NDCG）、生成层指标计算（Faithfulness/Answer Relevance/Answer via LLM-as-judge）、三模式消融对比（dense/bm25/hybrid）、评测报告生成

### Modified Capabilities

（无 — 本次变更为纯增量，不修改现有 RAG 系统的检索/生成逻辑）

## Impact

- 新增文件：`eval/prepare_corpus.py`、`eval/prepare_golden.py`、`eval/metrics.py`、`eval/run_eval.py`、`eval/corpus.jsonl`（生成物）、`eval/golden.jsonl`（生成物）
- 依赖现有系统：`RAGService.ingest()` 入库、`HybridStore.search()` 检索、`set_milvus_backend()` / `set_es_backend()` 模式切换、DashScope embedding API、DashScope LLM API（生成 + LLM-as-judge）
- 基础设施依赖：PostgreSQL（rag_chunks 表）、Milvus（向量检索）、Elasticsearch（BM25 检索）；Neo4j 不参与本次评测
- 外部数据：CRUD-RAG 开源数据集（已下载至 `eval/CRUD_RAG-main/`）
- 不影响现有代码：评测脚本独立于后端主代码，通过调用 RAGService API 或直接操作 HybridStore 进行
