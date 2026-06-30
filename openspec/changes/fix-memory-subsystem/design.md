## Context

AgentHub 记忆子系统从 AGI-memory 移植而来，包含三层记忆架构：
- **ShortTerm（STM）**：内存 deque 滑动窗口，最近 N 轮对话
- **LongTerm（LTM）**：embedding 向量 + PG 持久化，语义召回
- **GraphMemory**：Neo4j 图增强 + PG 镜像表

当前状态：移植时 4 处关键写入链路断裂，导致 `chat_history`、`long_term_memory.embedding`、`memory_nodes`、`memory_edges` 数据异常或为空。AGI-memory 原始实现中这些链路完整，可作为修复参考。

约束：
- 后端为 async Python（FastAPI + SQLAlchemy async session）
- `embed_fn` 已有基础设施（DashScope/OpenAI），仅需注入
- Neo4j 为可选基础设施，PG 镜像表需作为降级 fallback
- LLM 抽取需要 `generate_fn`，不可用时需优雅降级

## Goals / Non-Goals

**Goals:**
- 修复 `chat_history` PG 持久化，支持跨会话 STM 恢复
- 修复 `embed_fn` 注入，恢复 LTM 语义召回能力
- 实现 `memory_nodes`/`memory_edges` PG 镜像写入
- 移植智能记忆抽取，提升 LTM 内容质量（LLM 抽取 + 规则分类 + cosine dedup）

**Non-Goals:**
- 不改造 Neo4j 图操作逻辑（已正常工作）
- 不引入新的外部基础设施依赖
- 不修改前端 API 接口
- 不实现 `chat_history` 的启动期回放（后续迭代）

## Decisions

### D1: chat_history 写入位置 — 在 `MemoryService.on_message_end()` 中写入

**选择**：在 `on_message_end()` 中，`stm.add()` 之后立即写入 `ChatHistory`。
**替代**：改造 `ShortTerm.add()` 方法内部写入 → 会导致 ShortTerm 产生 DB 依赖，破坏纯内存设计。
**理由**：`on_message_end()` 已是记忆写入的统一入口，在此补上 PG 持久化最自然，保持 ShortTerm 纯内存。

### D2: embed_fn 注入时机 — 在 main.py lifespan RAG 初始化之后注入

**选择**：复用 `_make_embed_fn(settings)` 产出的 embed_fn，在 RAG 注入之后立即调 `_memory_service.set_embed_fn(embed_fn)`。
**理由**：一行修复，无新代码逻辑，只需调整 main.py lifespan 中的注入顺序。

### D3: PG 镜像表写入 — 在 Neo4j Cypher 操作后同步写入 PG

**选择**：在 `GraphMemory` 的 `_upsert_memory_node` / `_add_memory_edge` 成功执行 Cypher 后，同步执行 `session.add(MemoryNode/MemoryEdge)`。Neo4j 不可用时跳过 PG 写入（保持 no-op 降级）。
**替代**：用后台任务异步写入 → 增加复杂度，且 PG 镜像表非热路径，同步写入可接受。
**理由**：保持 GraphMemory 单一写入入口，PG 镜像作为附加操作不影响 Neo4j 主路径。

### D4: LTM 智能抽取 — 移植 AGI-memory memory_writer 核心逻辑

**选择**：新增 `app/memory/memory_writer.py`，移植 AGI-memory 的 `extract_memory_from_reply` + `classify_memory_content` + `store_classified` 链路。在 `_post_run_memory_hook` 中：
- 用户消息：仍用当前简单 importance 启发式直接 `ltm.add()`
- assistant 回复：走 LLM 抽取 → 分类 → `ltm.store_classified()` 链路

**替代**：全量移植 AGI-memory AsyncMemoryWriter 线程模型 → AgentHub 已是 asyncio 架构，无需 threading。
**理由**：保留核心抽取逻辑，适配 AgentHub 的 async 架构。LLM 不可用时降级为当前的简单 `ltm.add()`。

## Risks / Trade-offs

- **[LLM 抽取增加延迟]** → 抽取走 `asyncio.create_task` 后台执行，不阻塞主消息路径
- **[PG 镜像写入增加 Neo4j 路径开销]** → 单行 `session.add()` 开销极低（< 1ms），可忽略
- **[历史 LTM 数据无 embedding]** → 修复后新写入的条目有 embedding，旧条目保留 NULL（recall 时 TF fallback 兼容）
- **[chat_history 表无 created_at 默认值]** → ORM 模型已有 `created_at: Float`，写入时填 `time.time()`
