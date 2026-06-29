## Why

当前对话列表和聊天面板的标题展示冗余：单聊显示"与 xx 的对话"和"单聊 · 1 位 Agent"，群聊显示多个 agent 名称拼接和"群聊 · N 位 Agent"。这些信息在头像和上下文已经足够明确，副标题行占空间但价值低。同时，随着对话增多，用户缺少快速回顾对话内容的手段——仅靠标题无法判断对话主题，需要逐一打开查看。

## What Changes

- **BREAKING**: 默认标题生成规则变更：单聊从"与 {name} 的对话"改为直接使用 agent 名称，群聊从 agent 名称拼接改为"群聊（N）"
- 移除 chat-panel 头部和 sidebar 会话列表的"单聊/群聊 · N 位 Agent"副标题行
- 新增对话摘要功能：首次对话后后端自动调用 agent 模型生成摘要，存储在 conversation.summary 字段
- 摘要展示在 chat-panel 头部和 sidebar 会话列表项（统一位置，无摘要时为空）
- 用户可手动编辑摘要（类似标题重命名）
- sidebar 搜索框同时匹配 title 和 summary

## Capabilities

### New Capabilities
- `conversation-summary`: 对话摘要自动生成、展示、编辑与搜索能力

### Modified Capabilities
- `frontend`: 对话标题展示规则变更（移除单聊/群聊标签，摘要替换副标题行）

## Impact

- 后端：`conversation_service.py`（标题生成规则、摘要生成/更新 API）、`models.py`（Conversation 表新增 summary 字段）、`agent_runner.py`（首次回复后触发摘要生成）、`events.py`（新增 summary_updated SSE 事件）、`requests.py`（ConversationResponse 加 summary）
- 前端：`chat-panel.tsx`（移除副标题行，新增摘要展示）、`sidebar.tsx`（副标题改为摘要 + 编辑 + 搜索增强）、`schema.ts`（conversations 表加 summary）、`api.ts`（新增 API 调用）、`app-store.ts`（摘要状态管理）
- 数据库：conversations 表新增 `summary TEXT` 列