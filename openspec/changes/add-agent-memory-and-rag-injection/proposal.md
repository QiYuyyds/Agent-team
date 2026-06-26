## Why

Agent 当前缺少记忆和知识库能力：后端已注册 `memory_recall` 和 4 个 `rag_*` 工具，但前端 `AVAILABLE_AGENT_TOOLS` 白名单未包含它们，导致新建 Agent 无法使用这些工具。Agent 没有记忆 = 每次对话都是陌生人；无法检索知识库 = 知识库形同虚设。

## What Changes

### 1. memory_recall 后端隐式注入
- `agent_runner.py` 在 tool resolve 前，对所有 custom adapter 的 Agent 自动追加 `memory_recall`
- 前端不可见，用户无法控制
- 保证所有 custom agent 都具备基础记忆能力

### 2. 会话级 RAG 开关（全量注入）
- `conversations` 表新增 `rag_enabled: boolean, default false`
- 新增 API：`PATCH /api/conversations/{id}/rag-mode`
- `conversation_service.send_message()` 在 `rag_enabled=true` 时，给所有 responder 的 `tool_names` 追加全部 4 个 RAG 工具（`rag_search`、`rag_ingest`、`rag_list_documents`、`rag_delete_document`）
- 前端 `message-input.tsx` 新增 RAG toggle 按钮（复用 `fsWriteApprovalMode` 的 UI 模式）
- 单聊 + 群聊均适用

### 3. 边界处理
- Agent 已含 `rag_*` 工具时不重复注入（Set 去重）
- `claude-code` / `codex` agent 不注入（它们用 SDK 内置工具集）
- Orchestrator 分派子任务时，子 Agent 也继承 conversation 的 `rag_enabled` 状态

## Capabilities

### New Capabilities
- `agent-memory-injection`: 后端运行时自动为 custom agent 注入 memory_recall 工具，确保基础记忆能力
- `rag-session-toggle`: 会话级 RAG 开关，用户在对话界面启用/禁用知识库检索与管理能力

### Modified Capabilities
- `tools`: 工具解析逻辑增加隐式注入和会话级动态注入机制
- `conversation-context`: 会话上下文需携带 rag_enabled 状态，影响工具可用性

## Impact

- **后端**：`agent_runner.py`、`conversation_service.py`、`conversations.py`（API routes）、`requests.py`（schema）、`models.py`（DB model）
- **前端**：`message-input.tsx`、`api.ts`、`schema.ts`
- **数据库**：`conversations` 表加一列 `rag_enabled`（有 default 值，无需迁移脚本）
- **向后兼容**：已有会话 `rag_enabled=false`（默认关闭）；`memory_recall` 注入为新增工具不影响已有工具
