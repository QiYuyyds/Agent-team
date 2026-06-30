## 1. embed_fn 注入修复（D2 — 最小改动）

- [x] 1.1 在 `backend/app/main.py` lifespan 中，RAG embed_fn 注入之后增加 `_memory_service.set_embed_fn(embed_fn)` 调用
- [ ] 1.2 验证：启动后端，检查日志中 MemoryService 初始化行确认 embed_fn 已注入
- [ ] 1.3 验证：发送一条消息，查询 `long_term_memory` 表确认新条目的 embedding 列非 NULL

## 2. chat_history PG 持久化（D1）

- [x] 2.1 在 `backend/app/memory/memory_service.py` 的 `on_message_end()` 中，`stm.add()` 之后添加 `ChatHistory` PG 写入逻辑（使用 `get_db()` + `session.add(ChatHistory(...))`）
- [x] 2.2 写入逻辑包裹在 try/except 中，失败时 logger.warning 不阻塞主流程
- [ ] 2.3 验证：发送 user 和 assistant 消息各一条，查询 `chat_history` 表确认有 2 行数据

## 3. memory_nodes/memory_edges PG 镜像写入（D3）

- [x] 3.1 在 `backend/app/memory/graph_memory.py` 的 `_upsert_memory_node()` 中，Neo4j Cypher 执行成功后添加 `session.add(MemoryNode(...))` 写入 PG
- [x] 3.2 在 `_add_memory_edge()` 中，Neo4j Cypher 执行成功后添加 `session.add(MemoryEdge(...))` 写入 PG
- [x] 3.3 PG 写入使用 `from app.db.engine import get_db` 和 `from app.db.models import MemoryNode, MemoryEdge`，包裹在 try/except 中
- [ ] 3.4 验证：确保 Neo4j 运行中，触发 LTM add，查询 `memory_nodes` 和 `memory_edges` 表确认有数据
- [ ] 3.5 验证：停止 Neo4j，触发 LTM add，确认 `memory_nodes`/`memory_edges` 无新写入（降级 no-op）

## 4. LTM store_classified 方法实现（D4 前置）

- [x] 4.1 在 `backend/app/memory/long_term.py` 中移植 AGI-memory 的 `store_classified()` 方法：接受 content, importance, emb, category, tags, slot_hint 参数
- [x] 4.2 实现 embedding cosine dedup 逻辑：遍历 self.items，similarity >= 0.95 时更新已有条目（importance/tags/category/slot_hint），不插新行
- [x] 4.3 dedup 未命中时走完整 add 路径：构造新 Item + PG 写入 + graph_memory.add_to_graph hook
- [ ] 4.4 验证：写入两条高相似度内容，确认 PG 只有一条记录且 importance 被更新

## 5. 智能记忆抽取模块（D4）

- [x] 5.1 新建 `backend/app/memory/memory_writer.py`，移植 AGI-memory 的 `classify_memory_content()` 规则分类函数（identity/preference/tool_failure/policy 四类规则）
- [x] 5.2 实现 `extract_memory_from_reply()` 异步函数：调用 generate_fn 用 LLM 从 assistant 回复中抽取 k-v 事实
- [x] 5.3 实现 LLM 抽取 prompt：系统提示要求输出 JSON 格式的 key-value 对列表
- [x] 5.4 在 `MemoryService` 中添加 `set_generate_fn()` 方法，注入 LLM generate 函数
- [x] 5.5 在 `backend/app/main.py` lifespan 中，generate_fn 可用时调用 `_memory_service.set_generate_fn(generate_fn)`
- [x] 5.6 修改 `MemoryService.on_message_end()`：assistant 消息走 `extract_memory_from_reply()` → `store_classified()` 链路（asyncio.create_task 后台执行），user 消息保持当前简单 `ltm.add()` 逻辑
- [x] 5.7 添加 trivial 过滤：assistant 回复 < 10 字符或匹配"好的/没问题/OK"等模式时跳过抽取
- [ ] 5.8 验证：发送一条有信息量的对话，确认 `long_term_memory` 中存的是抽取后的事实而非原始消息

## 6. 集成测试与回归验证

- [x] 6.1 运行现有测试 `pytest backend/tests/` 确认无回归
- [ ] 6.2 端到端验证：创建对话 → 发送多轮消息 → 检查四张表数据完整性
- [ ] 6.3 验证语义召回：发送含特定信息的对话，随后用相关问题触发 memory_recall，确认返回正确记忆
