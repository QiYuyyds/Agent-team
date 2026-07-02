# Tasks

## 1. Backend: 结构化返回 ctxBefore / ctxAfter

- [x] 1.1 `CompactResult` dataclass 增加 `ctx_before: int` / `ctx_after: int` 字段（`context_compaction_service.py`）
- [x] 1.2 `compact_conversation` 返回时填入已算好的 `ctx_before` / `ctx_after`
- [x] 1.3 `/conversations/{id}/compact` 响应体新增 `ctxBefore` / `ctxAfter`（`conversations.py`）

## 2. Frontend: 类型与 store

- [x] 2.1 `CompactConversationResult` 增加 `ctxBefore: number` / `ctxAfter: number`（`src/lib/api.ts`）
- [x] 2.2 app-store 增加 state `ctxOverrideByConv: Record<string, { tokens: number; at: number }>` 与 action `setCtxOverride(conversationId, tokens, at)`
- [x] 2.3 `useConversationUsageTotal` 在派生 `lastInputTokens` 后，若 `ctxOverride.at` > 实际来源时间戳则覆盖 `lastInputTokens`

## 3. Frontend: 接线

- [x] 3.1 `UsageBadge.handleCompact` 在 `upsertMessage(result.message)` 后调用 `setCtxOverride(conversationId, result.ctxAfter, result.message.createdAt)`

## 4. 验证

- [x] 4.1 后端 `ruff check` 通过；`pytest -k "compact or conversation"` → 57 passed（2 个 title 测试失败为 `simplify-conversation-title-add-summary` 变更遗留的陈旧断言，与本变更无关）
- [x] 4.2 前端 `pnpm typecheck`（本仓 `src/` 零报错；multica vendored 子项目预存错误无关）+ `eslint` 改动文件通过
- [ ] 4.3 手测（留给用户）：长对话点「压缩上下文」，右上角「当前 ctx」立即降到 `ctxAfter`；随后发一条真实消息，agent 回复后被实测值接管
