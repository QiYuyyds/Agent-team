# RAG Evaluation Toolkit

基于 [CRUD-RAG](https://github.com/noneur/CRUD_RAG) 数据集的 RAG 系统效果评测工具，支持 **dense / bm25 / hybrid** 三种检索模式消融对比，覆盖检索层与生成层共 7 项指标。

## 目录结构

```
eval/
├── CRUD_RAG-main/          # 源数据集（新闻 QA）
│   └── data/crud_split/split_merged.json
├── prepare_corpus.py       # 语料提取脚本 → corpus.jsonl
├── prepare_golden.py       # QA 标注转换脚本 → golden.jsonl
├── metrics.py              # 7 项评测指标实现
├── test_metrics.py         # 指标单元测试（26 tests）
├── run_eval.py             # 评测主运行器
├── inspect_data.py         # 数据结构检查工具
├── corpus.jsonl            # 3,050 篇去重新闻文档
├── golden.jsonl            # 2,394 条 QA 标注
├── results_1/              # 第一轮结果（旧权重 sem_w=0.7, kw_w=0.0）
│   ├── dense_results.json
│   ├── bm25_results.json
│   ├── hybrid_results.json
│   └── comparison_report.md
└── results_2/              # 第二轮结果（修复权重 sem_w=0.5, kw_w=0.5）
    ├── hybrid_results.json
    └── comparison_report.md
```

## 前置条件

### 1. 基础设施

确保 Docker Compose 已启动以下服务：

| 服务 | 端口 | 用途 |
|------|------|------|
| PostgreSQL | 5432 | 文档 chunk 存储 |
| Milvus | 19530 | 语义向量检索 |
| Elasticsearch | 9200 | BM25 关键词检索 |

```bash
docker compose up -d postgres milvus milvus-etcd elasticsearch
```

### 2. 后端配置

`backend/.env.local` 需配置以下关键项：

```env
# 检索基础设施
MILVUS_HOST=localhost
ES_ADDRESSES=http://localhost:9200

# Embedding（DashScope）
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-v3

# LLM（DashScope qwen-turbo）
LLM_API_KEY=sk-xxx
LLM_MODEL=qwen-turbo

# RAG 权重（影响 hybrid RRF 融合）
RAG_SEMANTIC_WEIGHT=0.5    # 语义检索权重
KG_WEIGHT=0.0              # 知识图谱权重（0 = 禁用）
RAG_RRF_CONSTANT_K=60      # RRF 常数
```

> **权重关系**：`kw_w = 1.0 - RAG_SEMANTIC_WEIGHT - KG_WEIGHT`
> 若 `RAG_SEMANTIC_WEIGHT + KG_WEIGHT = 1.0`，则 BM25 权重为 0，hybrid 退化为纯语义检索。

### 3. Python 环境

使用后端虚拟环境运行（依赖 pydantic-settings、pymilvus、elasticsearch 等）：

```powershell
# 所有命令使用后端 .venv
$python = "..\backend\.venv\Scripts\python.exe"
```

## 使用流程

### Step 1: 数据准备（已完成，通常无需重跑）

```powershell
# 提取 3,050 篇去重文档
$python prepare_corpus.py

# 转换 2,394 条 QA 标注
$python prepare_golden.py
```

**corpus.jsonl** 格式：
```json
{"doc_id": 0, "content": "新华社北京...", "source": "questanswer_1doc"}
```

**golden.jsonl** 格式：
```json
{"query_id": 0, "query": "...", "ground_truth_answer": "...", "relevant_docs": ["..."], "num_relevant_docs": 1, "task_type": "1doc"}
```

### Step 2: 运行评测

```powershell
cd d:\java\project\bitdance-agenthub-main\eval

# 快速验证（200 条采样，需 ~40 分钟）
..\backend\.venv\Scripts\python.exe -X utf8 run_eval.py --limit 200 --skip-ingest

# 全量评测（2,394 条 × 3 模式，需 ~13 小时）
..\backend\.venv\Scripts\python.exe -X utf8 run_eval.py --skip-ingest

# 首次运行（需先入库 3,050 篇文档）
..\backend\.venv\Scripts\python.exe -X utf8 run_eval.py --limit 200
```

### Step 3: 增量重跑（仅指定模式）

权重调整后只需重跑受影响的模式，其余模式从已有 JSON 加载：

```powershell
# 只跑 hybrid（dense/bm25 从 results/ 加载）
..\backend\.venv\Scripts\python.exe -X utf8 run_eval.py --limit 200 --skip-ingest --modes hybrid

# 跑 dense + hybrid
..\backend\.venv\Scripts\python.exe -X utf8 run_eval.py --limit 200 --skip-ingest --modes dense,hybrid
```

### CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--limit N` | 随机采样 N 条 golden 条目（seed=42 可复现） | 全部 2,394 条 |
| `--skip-ingest` | 跳过语料入库（已索引时使用） | 否 |
| `--modes` | 指定运行的模式（逗号分隔），未指定的从 JSON 加载 | dense,bm25,hybrid |

## 评测指标

### 检索层（纯计算，无 LLM 调用）

| 指标 | 公式 | 说明 |
|------|------|------|
| **Recall@K** | 命中数 / 相关文档数 | K=5，检索覆盖率 |
| **Precision@K** | 命中数 / K | K=5，检索精度 |
| **MRR** | 1 / 首个命中排名 | 平均倒数排名 |
| **NDCG@K** | DCG / IDCG | K=5，考虑排名位置的增益 |

命中检测采用**双向子串匹配**（`is_hit()`）：取 chunk 前 50 字符与 relevant_docs 做双向包含判断，解决 chunk_id 与文档级标注不对齐的问题。

### 生成层（LLM-as-judge）

| 指标 | 评判内容 | 分数范围 |
|------|----------|----------|
| **Faithfulness** | 答案是否忠于检索上下文（无幻觉） | [0, 1] |
| **Answer Relevance** | 答案与问题的相关程度 | [0, 1] |
| **Answer Quality** | 答案的综合质量（完整性、准确性） | [0, 1] |

使用 DashScope `qwen-turbo` 作为评判 LLM，通过结构化 prompt 约束输出为单一数值分数。

## 运行单元测试

```powershell
cd d:\java\project\bitdance-agenthub-main\eval
..\backend\.venv\Scripts\python.exe -X utf8 -m pytest test_metrics.py -v
```

覆盖 `is_hit`、`recall_at_k`、`precision_at_k`、`mrr`、`ndcg_at_k` 共 26 个测试用例。

## 评测结果

### 第一轮：旧权重（sem_w=0.7, kw_w=0.0, kg_w=0.3）

> BM25 权重为 0，hybrid 退化为纯语义检索

| Metric | dense | bm25 | hybrid |
|--------|-------|------|--------|
| recall@5 | **0.7700** | 0.7617 | 0.7492 |
| mrr | **0.8442** | 0.8325 | 0.8108 |
| ndcg@5 | 0.7337 | **0.7376** | 0.7154 |
| faithfulness | **0.9925** | 0.9825 | 0.9840 |
| answer_relevance | 0.9235 | **0.9295** | 0.9225 |

### 第二轮：修复权重（sem_w=0.5, kw_w=0.5, kg_w=0.0）

> BM25 恢复权重后 hybrid 改善

| Metric | hybrid (旧) | hybrid (新) | 变化 |
|--------|-------------|------------|------|
| recall@5 | 0.7492 | 0.7492 | — |
| mrr | 0.8108 | 0.8258 | +1.5% |
| ndcg@5 | 0.7154 | 0.7277 | +1.2% |
| answer_relevance | 0.9225 | 0.9330 | +1.1% |

### 关键发现

1. **权重配置陷阱**：`RAG_SEMANTIC_WEIGHT + KG_WEIGHT = 1.0` 会导致 BM25 权重为 0，hybrid 退化为 degraded dense
2. **RRF k=60 压缩区分度**：相邻排名分数差仅 ~0.0002，排序信号弱
3. **Recall 不变但 MRR/NDCG 提升**：BM25 加入后改变了排序但未改变 top-5 文档集合
4. **Reranker 可能覆盖 RRF 排序**：LLM reranker 对融合结果重新打分，可能抹平 RRF 差异

## 输出文件说明

### `<mode>_results.json`

每条 golden 条目的逐条评测结果，包含 query、retrieved chunks、generated answer、各指标分数。

### `comparison_report.md`

Markdown 格式的对比报告，包含：
- 运行元数据（时间、采样数、配置）
- 7×3 指标对比表（最优值加粗）
- 每个模式的详细平均值

## 技术细节

### 模式切换机制

评测脚本通过保存/重注入后端函数引用来切换检索模式：

| 模式 | Milvus | ES | mode() 返回值 | 搜索路径 |
|------|--------|-----|---------------|----------|
| dense | ✅ | ❌ (None) | "semantic" | `_search_semantic` |
| bm25 | ❌ (None) | ✅ | "keyword" | `_search_keyword` |
| hybrid | ✅ | ✅ | "hybrid" | `_search_hybrid` (RRF) |

### Windows 编码注意

PowerShell 下运行需加 `-X utf8` 标志，避免 GBK 编码错误：

```powershell
..\backend\.venv\Scripts\python.exe -X utf8 run_eval.py
```

### Token 消耗估算（200 条采样）

| 环节 | 调用次数 |
|------|----------|
| Query embedding | 200 × 模式数 |
| LLM 生成答案 | 200 × 模式数 |
| LLM-as-judge 评分 | 200 × 模式数 × 3 指标 |

单模式 200 条约消耗 ~1000 次 API 调用，三模式约 ~3000 次。
