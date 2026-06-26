## 1. 后端 — memory_recall 隐式注入

- [x] 1.1 `agent_runner.py`: 在 `base_tool_names` 解析后、`tool_registry.resolve()` 前，对 custom adapter 自动追加 `memory_recall`（去重 + INFO 日志）
- [ ] 1.2 编写测试：验证 custom agent 运行时 tool list 包含 `memory_recall`；验证 SDK agent 不受影响

## 2. 后端 — conversations 表 + model 加 rag_enabled 字段

- [x] 2.1 `db/models.py`: Conversation model 加 `rag_enabled: Mapped[bool] = mapped_column(Boolean, name="rag_enabled", nullable=False, default=False)`
- [x] 2.2 `services/conversation_service.py`: `_conversation_response()` 返回值加 `ragEnabled` 字段
- [x] 2.3 `services/conversation_service.py`: `create_conversation()` 和 `create_group_conversation()` 默认 `rag_enabled=False`

## 3. 后端 — RAG mode API endpoint

- [x] 3.1 `schemas/requests.py`: 新增 `SetRagModeRequest` schema（`rag_enabled: bool = Field(alias="ragEnabled")`）
- [x] 3.2 `api/conversations.py`: 新增 `PATCH /conversations/{id}/rag-mode` 路由，调用 `conversation_service.set_rag_mode()`
- [x] 3.3 `services/conversation_service.py`: 新增 `set_rag_mode()` 方法（更新 DB + 返回 conversation 对象）

## 4. 后端 — send_message 动态注入 RAG 工具

- [x] 4.1 `services/conversation_service.py`: `send_message()` 中读取 `conv.rag_enabled`，为每个 responder 的 `tool_names` 追加 4 个 RAG 工具（去重）
- [x] 4.2 确保 Orchestrator 分派子任务时，子 Agent 的 `override_tool_names` 也包含 RAG 工具
- [ ] 4.3 编写测试：验证 `rag_enabled=true` 时 responder 工具列表包含 RAG 工具；验证 SDK agent 不受影响

## 5. 前端 — schema + API 对接

- [x] 5.1 `db/schema.ts`: conversations 表加 `ragEnabled: integer('rag_enabled', { mode: 'boolean' }).notNull().default(false)`
- [x] 5.2 `lib/api.ts`: `ConversationWithMeta` 类型加 `ragEnabled: boolean`
- [x] 5.3 `lib/api.ts`: 新增 `setRagMode(conversationId, enabled)` 函数，调用 `PATCH /api/conversations/{id}/rag-mode`

## 6. 前端 — message-input.tsx RAG toggle 按钮

- [x] 6.1 新增 RAG toggle 按钮（BookOpen 或 Database 图标），复用 `fsWriteApprovalMode` toggle 的 UI 模式
- [x] 6.2 按钮状态绑定 `conversation.ragEnabled`，点击调用 `setRagMode()` 并 `upsertConversation()`
- [x] 6.3 tooltip 文案：未启用="启用 RAG 知识库检索"，已启用="RAG 已启用 · Agent 可检索与管理知识库"

## 7. 测试与验证

- [ ] 7.1 后端单元测试：memory_recall 隐式注入（custom/SDK 分支覆盖）
- [ ] 7.2 后端单元测试：RAG 开关对 responder 工具注入的影响
- [ ] 7.3 端到端验证：创建会话 → 启用 RAG → 发消息 → 确认 Agent 可调用 rag_search
