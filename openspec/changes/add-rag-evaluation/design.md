## Context

项目已具备完整的三路混合 RAG 检索能力：

- **HybridStore**（`backend/app/infra/hybrid.py`）：三路并发检索（Milvus 语义 + ES BM25 + KG 图谱），RRF 融合排序，通过 `set_milvus_backend()` / `set_es_backend()` / `set_kg_backend()` 注入开关控制检索路径，`mode()` 方法返回 `"hybrid"` / `"semantic"` / `"keyword"` / `"unavailable"`
- **RAGEngine**（`backend/app/rag/rag_engine.py`）：`ingest(doc)` 执行 split→embed→index 全链路；`query_with_history(question)` 执行 rewrite→search_multi→rerank→compose_answer 全链路，返回 `(answer: str, chunks: List[dict])`
- **RAGService**（`backend/app/services/rag_service.py`）：门面类，聚合 HybridStore + RAGEngine，提供 `ingest()` / `search()` / `set_milvus_backend()` / `set_es_backend()` 等方法

当前缺少：对上述检索系统的效果量化评测。无法回答"dense vs bm25 vs hybrid 哪个更好""Reranker 带来多少提升"等问题。

CRUD-RAG 数据集已下载至 `eval/CRUD_RAG-main/`，其中 `split_merged.json` 子集包含 2,394 条 QA（questanswer_1doc 800 条 + 2docs 797 条 + 3docs 797 条），引用 3,050 篇独立新闻文档。QA 自带的 news1/news2/news3 既是相关文档又互为干扰项（干扰比 3049:1），无需全量 80k 语料库。

## Goals / Non-Goals

**Goals:**

- 基于 CRUD-RAG split_merged.json 构建 RAG 评测数据集（3,050 篇语料 + 2,394 条 QA 标注）
- 实现 7 个评测指标：检索层 4 个（Recall@K、Precision@K、MRR、NDCG）+ 生成层 3 个（Faithfulness、Answer Relevance、Answer）
- 支持 dense / bm25 / hybrid 三种检索模式消融对比
- 输出 Markdown 对比报告，一目了然展示三种模式在各指标上的表现
- 评测脚本独立于后端主代码，通过 RAGService API 调用

**Non-Goals:**

- 不修改现有 RAG 系统的检索/生成/切分逻辑
- 不测试 KG（知识图谱）检索路径，只测 dense + bm25 + hybrid(dense+bm25)
- 不做参数调优（top_k、chunk_size、semantic_weight 等参数保持当前值）
- 不做多领域对比（CRUD-RAG 均为新闻领域）
- 不做端到端 API 测试（不通过 HTTP API，直接调用 Python 对象）

## Decisions

### D1: 使用 split_merged.json 子集而非全量数据

**选择**：CRUD-RAG 论文子集 `split_merged.json`（2,394 条 QA + 3,050 篇新闻）

**理由**：
- 全量 80k 语料库（91,964 篇）入库需 ~230,000 次 embedding 调用，而 split 子集仅需 ~7,625 次（97% 削减）
- QA 自带新闻文档互为干扰项，干扰比 3049:1 已远超真实知识库场景（通常几百比一）
- 从 3000:1 到 80000:1 的干扰比增加对 Recall/Precision 指标影响 <0.1%，边际收益可忽略
- split_merged.json 是 CRUD-RAG 论文使用的评测子集，具备学术可比性

**备选**：全量 80k 入库 / 200 条采样试跑。全量成本过高且无指标收益；200 条适合验证流程但不适合正式评测。

### D2: 内容匹配判定检索命中（非 chunk_id 匹配）

**选择**：通过 chunk 内容前 50 字与 relevant_docs（新闻原文）做子串匹配

**理由**：
- CRUD-RAG 的 news1/news2/news3 是新闻原文，入库后会被 RecursiveSplitter 切分为多个 chunk
- 无法预先知道原文切分后的 chunk_id，因此不能用 chunk_id 级标注
- chunk 内容是原文的子串，所以 chunk[:50] 必然是原文的子串 → 双向子串匹配可行
- 项目 `RAGService.search()` 返回的 chunks 中 `content` 字段是 `parent_content or chunk_content`，parent 同样是原文子串

**匹配算法**：
```
def is_hit(chunk_content: str, relevant_docs: List[str], prefix_len: int = 50) -> bool:
    prefix = chunk_content[:prefix_len].strip()
    if not prefix:
        return False
    for doc in relevant_docs:
        if prefix in doc or doc[:prefix_len] in chunk_content:
            return True
    return False
```

**备选**：doc_hash 匹配（需要 ingest 后查 PG 获取 doc_hash→chunk 映射，过于复杂）；模糊匹配（编辑距离，计算量大且阈值难定）。

### D3: 模式切换通过保存/重注入 backend 函数

**选择**：评测脚本启动时保存 Milvus/ES 的 search_fn 和 insert_fn，运行时通过 `set_milvus_backend(None)` / `set_es_backend(None)` 切换模式

**理由**：
- HybridStore 的 `mode()` 由 `_milvus_ok()` 和 `_es_ok()` 决定，二者检查 search_fn 是否为 None
- 保存原始函数引用，切换时重注入即可恢复，无需重新初始化基础设施连接
- `set_milvus_backend(search_fn, insert_fn)` 和 `set_es_backend(search_fn, index_fn)` 是现有公开 API

**切换逻辑**：
```
# 启动时保存
milvus_search = hybrid._milvus_search_fn
milvus_insert = hybrid._milvus_insert_fn
es_search = hybrid._es_search_fn
es_index = hybrid._es_index_fn

# dense 模式
rag_service.set_milvus_backend(milvus_search, milvus_insert)
rag_service.set_es_backend(None)

# bm25 模式
rag_service.set_milvus_backend(None)
rag_service.set_es_backend(es_search, es_index)

# hybrid 模式
rag_service.set_milvus_backend(milvus_search, milvus_insert)
rag_service.set_es_backend(es_search, es_index)
```

**备选**：包装 ToggleableBackend 类（过度工程化）；通过环境变量控制（需要重启后端，不适合单次评测多模式）。

### D4: LLM-as-judge 使用 DashScope qwen-plus

**选择**：用项目已配置的 DashScope LLM（`backend/.env.local` 中的 `LLM_API_KEY` + `LLM_MODEL`）作为 judge

**理由**：
- 项目已有 DashScope LLM 集成，无需额外引入 OpenAI/Anthropic API
- qwen-plus 支持中文理解，与 CRUD-RAG 中文数据集匹配
- 三个生成层指标均设计为 0.0-1.0 分数输出，prompt 约束 LLM 只返回数字

**备选**：引入 Ragas 框架（额外依赖，且 Ragas 默认用 OpenAI）；用规则匹配替代 LLM（无法评估语义忠实度和相关性）。

### D5: 评测脚本直接调用 Python 对象（非 HTTP API）

**选择**：评测脚本通过 `import` 后端模块，直接操作 RAGService 对象

**理由**：
- 直接调用避免 HTTP 序列化开销，2,394×3=7,182 次检索 + 14,364 次 LLM 调用通过 HTTP 会显著增加延迟
- 可以直接访问 HybridStore 内部状态进行模式切换
- 后端 FastAPI 服务仍需运行（提供基础设施初始化），但评测脚本绕过 HTTP 层

**备选**：通过 HTTP API 调用（需要新增模式切换 API 端点，增加后端代码改动）。

### D6: 分两阶段执行 — 先 200 条采样验证，再全量跑

**选择**：`run_eval.py` 支持 `--limit N` 参数，先跑 200 条验证流程正确性

**理由**：
- 7,182 次检索 + 14,364 次 LLM 调用全量跑约需 1-2 小时
- 先用 200 条（~10 分钟）验证脚本无 bug、指标计算正确、模式切换有效
- 验证通过后去掉 `--limit` 全量跑

## Risks / Trade-offs

- **[内容匹配误判]** chunk[:50] 可能恰好出现在多篇新闻中（如通用导语"本报讯"）→ 缓解：前 50 字通常包含具体事件信息；如误判率高，可增大 prefix_len 到 100 或增加最小独特字符数检查
- **[LLM-as-judge 一致性]** 同一 (question, answer) 对多次评分可能不一致 → 缓解：每个指标跑 2 次取平均；prompt 约束输出为纯数字减少解析歧义
- **[ingest 去重]** RAGEngine 用 `sha256(doc)` 计算 doc_hash，相同新闻在不同 QA 中出现时会跳过重复入库 → 这不是风险，反而是优化（3,050 篇独立文档中可能有跨 QA 重复）
- **[模式切换副作用]** `set_es_backend(None)` 会影响后续 ingest 的 ES 索引 → 缓解：模式切换只影响 search，ingest 在评测前一次性完成（全模式共享同一份索引数据）
- **[parent_content 干扰]** `search()` 返回的 content 可能是 parent_content（更大范围），导致匹配更容易 → 这反而更保守（parent 命中 = chunk 必然命中），不会虚高 Recall
