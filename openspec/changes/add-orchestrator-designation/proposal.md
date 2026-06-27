# Add Orchestrator Designation

## Why

当前 Orchestrator 角色（`is_orchestrator=true`）在整条链路上都是断裂的：

1. **前端创建 Agent 时** — `CreateAgentDialog` 没有 `isOrchestrator` 开关，用户无法把任何 Agent 设为协调者。
2. **API 层** — `CreateAgentBody` / `UpdateAgentBody` 均不含 `isOrchestrator` 字段。
3. **后端** — `create_agent()` 硬编码 `is_orchestrator=False`，所有新建 Agent 永远不是 Orchestrator。
4. **群聊创建时** — `NewConversationDialog` 不显示已选 Agent 中谁是协调者，也不在缺少协调者时给出警告。
5. **运行时** — `_decide_responders()` 在群聊无 Orchestrator 时静默返回空列表，用户发消息后没有任何反馈。

用户唯一能让群聊有 Orchestrator 的方式是手动写数据库或 seed 测试 fixtures。这不可接受。

## What Changes

### 1. Agent 创建/编辑表单加 Orchestrator 开关（方案 A）
- 在 `CreateAgentDialog` 基本信息 tab 增加「设为协调者」toggle。
- 勾选时自动注入 `plan_tasks` + `ask_user` 工具，并在 UI 提示说明。
- 前端 `CreateAgentBody` / `UpdateAgentBody` 增加 `isOrchestrator?: boolean`。
- 后端 `create_agent` / `update_agent` 接收并持久化 `is_orchestrator`。

### 2. 新建群聊时展示 Orchestrator 状态
- 检测已选 Agent 中 `isOrchestrator=true` 的项。
- 有 → 显示 "协调者: {name} ✓"。
- 无 → 显示警告 "此群聊无协调者，消息须 @ 具体 Agent 才能被响应"。
- 不阻止创建（弱约束，兼容 @-mention only 模式）。

### 3. 群聊无 Orchestrator 时运行时反馈
- `_decide_responders()` 返回空时，不再静默。
- 改为创建一条 agent/system 消息告知用户："此群聊没有协调者。请使用 @Agent名 指定回复对象。"

## Impact

- **前端**：`create-agent-dialog.tsx`、`new-conversation-dialog.tsx`、`api.ts`。
- **后端**：`agents.py`（API routes）、`conversation_service.py`（消息路由 + 系统消息）。
- **数据库**：无 schema 变更（`is_orchestrator` 字段已存在于 agents 表）。
- **向后兼容**：已有 Agent 数据不受影响；`isOrchestrator` 字段在 API body 中为 optional。
