## 1. 数据库变更

- [x] 1.1 Conversation 模型新增 `summary` 字段（`app/db/models.py`，TEXT NULLABLE）
- [x] 1.2 前端 Drizzle schema 新增 `summary` 字段（`src/db/schema.ts`，text NULLABLE）

## 2. 后端：标题生成规则变更

- [x] 2.1 修改 `_default_title_for()` 函数：单聊返回 agent 名称，群聊返回"群聊（N）"（`app/services/conversation_service.py`）
- [x] 2.2 验证 `create_conversation` 使用新标题规则（`app/services/conversation_service.py`）

## 3. 后端：摘要生成

- [x] 3.1 新增 `maybe_generate_summary()` 函数，实现摘要生成逻辑（检查 summary 为空 → 调用 agent 模型 → 写入 DB）（`app/services/conversation_service.py`）
- [x] 3.2 设计摘要生成 prompt（一句话 ≤50 字，包含用户消息和 agent 回复）
- [x] 3.3 在 `agent_runner.py` 首次回复完成后调用 `maybe_generate_summary()`
- [x] 3.4 实现并发安全：写入前再次检查 `summary IS NULL`，保证幂等

## 4. 后端：SSE 事件与 API

- [x] 4.1 新增 `summary_updated` SSE 事件类型（`app/schemas/events.py`）
- [x] 4.2 摘要写入后通过 event_bus 推送 `summary_updated` 事件
- [x] 4.3 `ConversationResponse` schema 新增 `summary` 字段（`app/schemas/requests.py`）
- [x] 4.4 `PATCH /api/conversations/{id}` 支持更新 `summary` 字段（`app/api/conversations.py`）

## 5. 前端：类型与 API

- [x] 5.1 `ConversationRow` / `ConversationWithMeta` 类型新增 `summary` 字段（`src/db/schema.ts`、`src/lib/api.ts`）
- [x] 5.2 前端 API 层新增 `updateConversationSummary` 调用（`src/lib/api.ts`）

## 6. 前端：标题简化

- [x] 6.1 chat-panel.tsx：删除副标题行 `{conv.mode === 'single' ? '单聊' : '群聊'} · {participantAgents.length} 位 Agent`（第 139-141 行）
- [x] 6.2 sidebar.tsx：删除副标题行 `{conversation.mode === 'single' ? '单聊' : '群聊'} · {conversation.agentIds.length} 位 Agent`（第 108-110 行）

## 7. 前端：摘要展示

- [x] 7.1 chat-panel.tsx：标题下方新增摘要展示（`conv.summary` 不为空时显示灰色小字）
- [x] 7.2 sidebar.tsx：ConversationItem 标题下方新增摘要展示（`conversation.summary` 不为空时显示灰色小字）

## 8. 前端：摘要编辑

- [x] 8.1 sidebar.tsx：ConversationItem 摘要区域 hover 时显示编辑图标
- [x] 8.2 复用 RenameInput 组件实现摘要编辑态
- [x] 8.3 摘要编辑确认后调用 API 更新，同步更新 store

## 9. 前端：SSE 事件处理

- [x] 9.1 app-store.ts：新增 `summary_updated` SSE 事件处理，更新对应 conversation 的 summary
- [x] 9.2 确保 chat-panel 和 sidebar 响应式刷新（依赖 zustand 响应式）

## 10. 前端：搜索增强

- [x] 10.1 sidebar.tsx：`filteredConversations` 过滤逻辑增加 `c.summary` 匹配（`src/components/sidebar.tsx`）

## 11. 验证

- [ ] 11.1 验证新建单聊默认标题为 agent 名称
- [ ] 11.2 验证新建群聊默认标题为"群聊（N）"
- [ ] 11.3 验证首次对话后摘要自动生成并展示
- [ ] 11.4 验证摘要为空时不显示副标题
- [ ] 11.5 验证摘要编辑功能
- [ ] 11.6 验证 sidebar 搜索能匹配摘要内容
- [ ] 11.7 验证 SSE 推送摘要后前端实时更新
- [ ] 11.8 验证摘要生成失败不影响对话流程