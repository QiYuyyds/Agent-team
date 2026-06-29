# Conversation Summary

## Purpose

定义对话摘要的自动生成、展示、编辑与搜索能力。摘要由后端在首次对话完成后自动生成，通过 SSE 推送前端同步，统一展示在 chat-panel 头部和 sidebar 会话列表。

## ADDED Requirements

### Requirement: 后端 SHALL 在首次对话完成后自动生成摘要

系统 MUST 在 Agent 首次回复完成后，检查 conversation.summary 是否为空，若为空则调用当前对话的 agent 模型生成摘要并写入数据库。摘要生成失败时 SHALL 静默处理，不影响对话流程。

#### Scenario: 首次单聊对话后生成摘要
- **WHEN** 用户发送第一条消息且 agent 回复完成
- **AND** conversation.summary 为 NULL
- **THEN** 系统调用该 agent 的模型生成摘要
- **AND** 将摘要写入 conversation.summary
- **AND** 推送 SSE 事件 `{ type: "summary_updated", conversationId, summary }`

#### Scenario: 已有摘要时跳过生成
- **WHEN** agent 回复完成
- **AND** conversation.summary 不为 NULL
- **THEN** 系统不生成摘要

#### Scenario: 摘要生成失败时静默处理
- **WHEN** 调用 agent 模型生成摘要失败（超时、token 不足等）
- **THEN** 系统记录错误日志
- **AND** conversation.summary 保持 NULL
- **AND** 对话流程不受影响

#### Scenario: 并发安全——同时多次触发
- **WHEN** 多个请求同时触发摘要生成
- **THEN** 系统在写入前再次检查 summary 是否为 NULL
- **AND** 仅第一个请求生成并写入摘要

### Requirement: 摘要 SHALL 使用当前对话的 agent 模型生成

系统 MUST 使用对话中首条 agent 的模型和 provider 调用 LLM 生成摘要。摘要 prompt SHALL 要求输出不超过 50 字的一句话总结。

#### Scenario: 单聊使用该 agent 模型
- **WHEN** 单聊对话需要生成摘要
- **THEN** 系统使用该 agent 的 modelProvider 和 modelId 调用 LLM
- **AND** prompt 包含用户消息和 agent 回复的内容

#### Scenario: 群聊使用第一个 agent 模型
- **WHEN** 群聊对话需要生成摘要
- **THEN** 系统使用 agent_ids 列表中第一个 agent 的模型

### Requirement: 前端 SHALL 在 chat-panel 和 sidebar 统一展示摘要

chat-panel 头部和 sidebar 会话列表项 MUST 在副标题位置展示 conversation.summary。摘要为空时 SHALL 不显示副标题行。

#### Scenario: chat-panel 展示摘要
- **WHEN** conversation.summary 不为空
- **THEN** chat-panel 头部标题下方显示摘要文本
- **AND** 摘要使用灰色小字（text-xs text-muted-foreground）

#### Scenario: sidebar 展示摘要
- **WHEN** conversation.summary 不为空
- **THEN** sidebar 会话列表项标题下方显示摘要文本
- **AND** 摘要使用灰色小字（text-xs text-muted-foreground）

#### Scenario: 摘要为空时不显示副标题
- **WHEN** conversation.summary 为 NULL 或空字符串
- **THEN** chat-panel 和 sidebar 均不显示副标题行

#### Scenario: SSE 推送摘要后实时更新
- **WHEN** 前端收到 `summary_updated` SSE 事件
- **THEN** store 更新对应 conversation 的 summary 字段
- **AND** chat-panel 和 sidebar 同步刷新显示

### Requirement: 用户 SHALL 可手动编辑摘要

系统 MUST 允许用户在 sidebar 会话列表项中编辑摘要，复用标题重命名的交互模式。

#### Scenario: 编辑摘要
- **WHEN** 用户 hover sidebar 会话列表项的摘要区域
- **THEN** 显示编辑图标
- **AND** 点击后进入编辑态，可修改摘要文本
- **AND** 确认后调用 `PATCH /api/conversations/{id}` 更新 summary

#### Scenario: 取消编辑摘要
- **WHEN** 用户在编辑态按 Escape 或点击取消
- **THEN** 摘要恢复为编辑前的值

### Requirement: sidebar 搜索 SHALL 同时匹配标题和摘要

sidebar 搜索框的过滤逻辑 MUST 同时匹配 conversation.title 和 conversation.summary。

#### Scenario: 搜索匹配摘要
- **WHEN** 用户在 sidebar 搜索框输入关键词
- **AND** 关键词出现在某对话的 summary 中但不在 title 中
- **THEN** 该对话出现在搜索结果中

#### Scenario: 搜索匹配标题
- **WHEN** 用户在 sidebar 搜索框输入关键词
- **AND** 关键词出现在某对话的 title 中
- **THEN** 该对话出现在搜索结果中（保持现有行为）