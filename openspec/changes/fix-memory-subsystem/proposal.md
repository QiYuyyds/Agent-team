## Why

AgentHub 从 AGI-memory 移植记忆子系统时，存在 4 处关键缺口，导致记忆系统 4 张 PG 表（`chat_history`、`long_term_memory.embedding`、`memory_nodes`、`memory_edges`）数据异常或为空。记忆系统是智能体"长期记忆 + 语义召回"能力的核心基础设施，当前状态使得语义召回退化为 TF 文本匹配、短期历史无法跨会话恢复、图谱增强完全不可用。需尽快修复以恢复记忆系统完整能力。

## What Changes

- **chat_history 持久化**：在 `ShortTerm.add()` 或 `on_message_end()` 中补上 `ChatHistory` 模型的 PG 写入，使短期记忆支持跨会话恢复
- **embed_fn 注入修复**：在 `main.py` lifespan 中给 `_memory_service` 注入 `embed_fn`，使 `long_term_memory.embedding` 列写入真实向量，恢复语义召回能力
- **memory_nodes/memory_edges PG 镜像写入**：在 `graph_memory.py` 中实现 Neo4j 操作后的 PG 镜像表写入逻辑（`session.add(MemoryNode/MemoryEdge)`），确保 PG 可作为 Neo4j 降级时的 fallback 数据源
- **LTM 内容质量提升**：移植 AGI-memory 的 `memory_writer` 智能抽取逻辑，用 LLM 从 assistant 回复中提取 k-v 事实并分类后存入长期记忆，替代当前无差别存原始 prompt 的行为

## Capabilities

### New Capabilities
- `memory-persistence`: 记忆子系统 PG 持久化能力（chat_history 写入、embed_fn 注入、PG 镜像表同步）
- `memory-extraction`: 基于 LLM 的智能记忆抽取能力（从回复中提取事实、分类、去重后入库）

### Modified Capabilities
- `persistence`: ORM 模型的 PG 写入链路补全（memory_nodes/memory_edges 镜像写入）

## Impact

- **后端代码**：`main.py`（embed_fn 注入）、`memory_service.py`（chat_history 写入 + LTM 智能抽取）、`short_term.py`（可选 PG 持久化）、`graph_memory.py`（PG 镜像写入）、`memory_writer.py`（新增抽取模块）
- **数据库**：`chat_history`、`long_term_memory`、`memory_nodes`、`memory_edges` 四张表开始有正常数据写入
- **依赖**：LLM 抽取需要 generate_fn 可用（已有 DashScope/OpenAI 配置）
- **API**：无接口变更，纯后端修复
