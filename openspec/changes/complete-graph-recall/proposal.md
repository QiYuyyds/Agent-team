## Why

AgentHub 记忆系统从 AGI-memory 移植时，GraphMemory 的**图扩展召回能力**（`find_related`）未被集成到实际召回链路。当前 `memory_recall` 工具和 Prompt 装配的 `RecallSource` 仅走 LTM 向量/TF 相似度搜索，完全没有利用图谱关系做邻居扩展。这意味着图谱结构虽在每次写入时完整维护（FOLLOWS/SIMILAR_TO 边），但召回时是"写满读空"——图谱的唯一实际价值仅剩合并期的中心度保护。AGI-memory 原版中，图扩展是 recall 流程的内建步骤，能"顺藤摸瓜"找到语义不直接相关但逻辑关联的记忆。需补齐此缺口以释放图谱记忆的全部价值。

## What Changes

- **LTM recall 集成图扩展**：改造 `LongTerm.recall()` 为两阶段召回——先向量/TF 语义搜索拿种子，再对种子做 `graph_memory.find_related()` 1-hop 扩展，扩展条目赋予固定分数（0.45），合并排序后截断 top_k
- **RecallSource 适配**：Prompt 装配层的 `RecallSource.fetch()` 无需修改（它已调 `memory_service.recall()`），图扩展在 `recall()` 内部透明完成
- **memory_recall 工具适配**：工具 handler 无需修改（它已调 `memory_service.recall()`），返回结果自动包含图扩展条目

## Capabilities

### New Capabilities
- `graph-expanded-recall`: 图扩展增强的语义召回能力——LTM recall 自动集成 1-hop 图邻居扩展

### Modified Capabilities

## Impact

- **后端代码**：`backend/app/memory/long_term.py`（recall 方法改造）、`backend/app/memory/memory_service.py`（recall 透传无需改动，但需确认 graph_memory 引用传递）
- **数据库**：无 schema 变更，利用已有 `memory_nodes`/`memory_edges` 表数据
- **依赖**：Neo4j 可用时自动启用图扩展；不可用时透明降级为纯向量/TF 召回（无新增依赖）
- **API**：无接口变更，`memory_recall` 工具返回格式不变，仅召回质量提升
