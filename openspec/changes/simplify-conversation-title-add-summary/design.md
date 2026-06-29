## Context

当前 AChat 的对话标题和副标题展示存在信息冗余，且对话增多后用户缺乏快速回顾内容的手段。本次变更分两部分：标题简化（纯展示层改动）和摘要系统（新增能力）。

**现有相关基础设施：**
- `ContextSummary` 表已存在，用于 LLM 上下文窗口压缩，与本次"对话摘要"定位不同（内部压缩 vs 用户展示），不复用
- `extractMessageSummary` 函数已存在，仅截取消息前 80 字符，不适合作语义摘要
- sidebar 已有搜索框和标题重命名机制，可作为摘要编辑的参考模式

## Goals / Non-Goals

**Goals:**
- 简化对话标题展示，移除冗余的"单聊/群聊"标签
- 首次对话后自动生成语义摘要，帮助用户快速回顾对话主题
- 摘要统一展示在 chat-panel 头部和 sidebar 会话列表
- 用户可手动编辑摘要，摘要参与 sidebar 搜索

**Non-Goals:**
- 不持续更新摘要（仅首次对话后生成一次）
- 不修改已有对话的标题（仅影响新建对话的默认标题）
- 不复用 ContextSummary 表（定位不同）
- 不生成消息级别的摘要（复用现有 extractMessageSummary）

## Decisions

### 决策 1：标题生成规则

**选择：** 前端显示时动态判断，后端仅改默认标题生成规则。

**理由：** 已存在的旧对话标题不会自动更新，前端动态显示可保证旧对话也展示为 agent 名称。但默认标题的生成规则变更让新建对话从源头就正确。

- 后端 `_default_title_for()`: 单聊 → `agent_name`，群聊 → `群聊（N）`
- 前端显示：直接使用 `conv.title`，不做额外判断

### 决策 2：摘要存储位置

**选择：** 在 `Conversation` 表新增 `summary` 字段（`TEXT | NULL`）。

**理由：** 摘要与对话 1:1 绑定，生命周期与对话一致，放在 Conversation 表最自然。不新建独立表也不复用 `ContextSummary`（后者为上下文压缩设计，字段语义不同）。

### 决策 3：摘要生成触发机制

**选择：** 后端自动触发，在 `agent_runner` 首次回复完成后通过 SSE 推送。

**流程：**
```
agent_runner.run() 完成首次回复
    │
    ▼
检查 conversation.summary IS NULL?
    │
    ├── 不为空 → 跳过（已生成或已手动编辑）
    │
    └── 为空 → 异步调用 agent 模型
               │
               ▼
            写入 conversation.summary
               │
               ▼
            推送 SSE: { type: "summary_updated", conversationId, summary }
               │
               ▼
            前端 store 更新 → sidebar + chat-panel 实时刷新
```

**替代方案考虑：**
- 前端主动调用 API：依赖前端在线，多客户端场景下不一致，且增加前端判断"是否首次对话"的复杂度
- 同步阻塞生成：会延迟用户看到回复的时间，不可接受

### 决策 4：摘要生成模型

**选择：** 使用当前对话的 agent 模型。

**理由：** 保持摘要风格与对话上下文一致。单聊用该 agent 模型，群聊用第一个 agent 的模型。

**Prompt 设计：**
```
请用一句话（不超过 50 字）总结以下对话的核心话题和结论：

用户：{user_message}
{agent_name}：{agent_response}

只输出摘要内容，不要加任何前缀或引号。
```

### 决策 5：并发安全

**选择：** 在写入前再次检查 `summary IS NULL`，使用数据库行级保证幂等。

**伪代码：**
```python
async def maybe_generate_summary(conversation_id, agent_id, user_msg, agent_reply):
    async with get_db() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv.summary is not None:
            return  # 已生成，跳过
        summary = await _call_agent_for_summary(agent_id, user_msg, agent_reply)
        conv.summary = summary
        await db.commit()
    await event_bus.publish("summary_updated", ...)
```

### 决策 6：前端展示逻辑

**选择：** chat-panel 和 sidebar 统一逻辑：有 summary 显示 summary，无 summary 不显示副标题。

**chat-panel 头部修改：**
- 删除：`{conv.mode === 'single' ? '单聊' : '群聊'} · {participantAgents.length} 位 Agent`
- 新增：`{conv.summary && <span className="text-xs text-muted-foreground truncate">{conv.summary}</span>}`

**sidebar 会话列表项修改：**
- 删除：`{conversation.mode === 'single' ? '单聊' : '群聊'} · {conversation.agentIds.length} 位 Agent`
- 新增：摘要展示 + hover 编辑图标

### 决策 7：摘要编辑

**选择：** 复用 sidebar 现有的标题重命名机制（`RenameInput` 组件），hover 摘要行时显示编辑图标。

**API：** `PATCH /api/conversations/{id}` 增加 `summary` 字段支持。

### 决策 8：搜索增强

**选择：** 前端 sidebar 搜索的过滤逻辑增加对 `summary` 字段的匹配。

**修改位置：** `sidebar.tsx` 中 `filteredConversations` 的计算逻辑，将 `c.title` 匹配扩展为同时匹配 `c.title` 和 `c.summary`。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| Agent 模型生成摘要失败（超时、token 不足等） | 静默失败，summary 保持 NULL，不影响对话流程 |
| 摘要生成额外消耗 token | 一次对话仅生成一次，成本可控；prompt 精简到 50 字以内 |
| 群聊场景下摘要可能不够准确 | 首次对话通常只有用户消息 + 一个 agent 回复，摘要质量有保障 |
| 旧对话标题"与 xx 的对话"不自动更新 | 用户可手动重命名标题，影响有限 |
| 数据库迁移需要 ALTER TABLE | SQLite 和 PostgreSQL 均支持 `ALTER TABLE ADD COLUMN`，无停机风险 |

## Open Questions

- 无。所有关键决策已在探索阶段确定。