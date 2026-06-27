# Design — Add Orchestrator Designation

## Decisions

### Decision 1: Orchestrator 是 Agent 级属性，不是会话级

**选择**：在 Agent 创建/编辑表单里加 `isOrchestrator` toggle（方案 A）。

**不选择**：在群聊创建时指定某个 Agent 为该会话的 Orchestrator（方案 B）。

**理由**：
- `is_orchestrator` 已经是 `agents` 表字段，Spec 01 定义在 Agent 层。
- Orchestrator 需要特殊的 system prompt + 工具集（`plan_tasks`、`ask_user`），这些都是 Agent 级属性。
- 方案 B 需要重构数据模型（增加 conversation-level orchestrator 字段），代价大且与现有 spec 冲突。

### Decision 2: 群聊创建时弱约束（提示而非阻止）

**选择**：群聊无 Orchestrator 时显示警告但仍允许创建。

**理由**：
- 有些群聊确实只需要 @-mention 模式，强制要求 Orchestrator 会限制使用场景。
- 弱约束 + 运行时明确反馈已经足够消除「信息黑洞」问题。

### Decision 3: 运行时反馈用 agent 消息而非报错

**选择**：`_decide_responders()` 返回空时，创建一条 agent/system 消息。

**不选择**：返回 HTTP 400 错误。

**理由**：
- 用户已经把消息发出去了，报错只在前端 toast 里闪过，不如聊天上下文里的消息持久。
- agent 消息融入对话流，用户回看时能看到。

---

## Architecture

### 前端改动

```
CreateAgentDialog
  ├── 新增 state: isOrchestrator (boolean)
  ├── 基本信息 tab 增加 toggle UI
  ├── 勾选时自动合并 plan_tasks + ask_user 到 toolNames
  └── 提交时把 isOrchestrator 传入 body

NewConversationDialog
  ├── 计算 selectedOrchestrator = selected agents 中 isOrchestrator=true 的
  ├── mode=group 时渲染 Orchestrator 提示区域
  │     有 → "协调者: {name} ✓"
  │     无 → ⚠ warning
  └── 不阻止提交

api.ts
  ├── CreateAgentBody 加 isOrchestrator?: boolean
  └── UpdateAgentBody 加 isOrchestrator?: boolean
```

### 后端改动

```
agents.py
  ├── CreateAgentRequest schema 加 is_orchestrator: bool = False
  ├── UpdateAgentRequest schema 加 is_orchestrator: Optional[bool]
  ├── create_agent() 使用 body.is_orchestrator 而非硬编码 False
  └── update_agent() 支持 patch is_orchestrator

conversation_service.py
  ├── _decide_responders() 返回空时，标记 "no_orchestrator"
  └── send_message() 检测到 no_orchestrator 时：
        创建一条 agent/system 消息：
        "此群聊没有协调者。请使用 @Agent名 指定回复对象。"
        通过 event_bus 广播给前端
```

---

## Non-Goals

- 不在群聊创建时指定会话级 Orchestrator（保留 Agent 级属性）。
- 不强制群聊必须有 Orchestrator。
- 不允许多个 Orchestrator（Spec 01 约束：群聊中最多 1 个）。
- 不改变 Orchestrator 的 plan/execute/aggregate 工作流。
