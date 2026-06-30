## Context

AgentHub 记忆系统已从 AGI-memory 移植 GraphMemory 组件，包括 Neo4j 节点/边写入、FOLLOWS/SIMILAR_TO 边构建、PG 镜像表同步、以及合并期的中心度保护。但移植时遗漏了 AGI-memory `MemoryManager.recall()` 中的图扩展召回步骤。

当前 `LongTerm.recall()` 和 `recall_by_filter()` 仅做向量/TF 语义搜索，直接按 score 排序返回。AGI-memory 原版中，recall 是两阶段流程：先语义搜索拿种子（seed），再对种子 ID 做 `graph_memory.find_related()` 1-hop 扩展，扩展条目赋予固定 score=0.45，与种子合并排序后截断 top_k。

约束：
- `LongTerm` 已持有 `self.graph_memory: Optional[GraphMemory]` 引用
- `find_related()` 已是 async 方法，返回 `List[int]`（扩展的 mem_id 列表）
- `LongTerm.items` 已在内存中，可直接按 id 查找扩展条目
- Neo4j 不可用时 `find_related()` 已静默返回空列表

## Goals / Non-Goals

**Goals:**
- 在 `LongTerm.recall()` 和 `recall_by_filter()` 中集成 1-hop 图扩展
- 保持 Neo4j 不可用时的透明降级（纯语义召回不变）
- 确保扩展条目与种子条目正确合并排序

**Non-Goals:**
- 不改造 Neo4j 图写入逻辑（已正常工作）
- 不引入多跳扩展（AGI-memory 原版也仅做 1-hop）
- 不修改 `memory_recall` 工具 handler 或 `RecallSource`（图扩展在 `recall()` 内部透明完成）
- 不修改 `memory_service.recall()` 签名（透传层无需变动）

## Decisions

### D1: 图扩展集成位置 — 在 `LongTerm.recall()` / `recall_by_filter()` 内部实现

**选择**：直接在 `LongTerm` 的两个 recall 方法末尾追加图扩展步骤。
**替代**：在 `MemoryService.recall()` 层做扩展 → 需要在 facade 层操作 `ltm.items`，破坏封装。
**理由**：`LongTerm` 已持有 `self.graph_memory` 引用和 `self.items` 列表，图扩展所需数据都在此处，集成最自然。上层调用方（MemoryService / RecallSource / memory_recall handler）无需任何修改。

### D2: 扩展条目评分 — 固定 0.45 分

**选择**：图扩展找到的条目统一赋予 score=0.45。
**替代**：按边权重动态计算 → 增加复杂度，且 AGI-memory 原版也用固定分数。
**理由**：与 AGI-memory 原版保持一致。0.45 低于正常语义召回阈值 0.4（但扩展条目不受该阈值约束），确保强语义匹配的种子排前面，弱关联的图邻居排在后面作为补充。

### D3: 提取公共图扩展方法 — `_graph_expand()` 内部方法

**选择**：抽取 `_graph_expand(seed_items, top_k)` 私有方法供 `recall()` 和 `recall_by_filter()` 共用。
**理由**：避免两个方法重复相同的图扩展 + 合并排序逻辑。

## Risks / Trade-offs

- **[find_related 增加召回延迟]** → `find_related()` 是 async Neo4j Cypher 查询，典型耗时 < 10ms。且仅在种子非空时执行，影响可忽略。Neo4j 不可用时直接返回空列表，零开销。
- **[扩展引入噪声记忆]** → 1-hop 扩展可能引入与 query 无关的记忆。固定 score=0.45 确保它们排在高相关性种子之后，且受 top_k 截断限制。后续可通过调整分数阈值或引入边权重优化。
- **[graph_memory 引用时序]** → `recall()` 执行时 `self.graph_memory` 可能已被 `set_graph_memory()` 设置或仍为 None。代码已通过 `if self.graph_memory is not None` 守卫处理。
