# Frontend (Delta)

## Purpose

本 delta 记录对话标题和摘要展示规则的前端变更。

## ADDED Requirements

### Requirement: 对话标题展示 SHALL 移除单聊/群聊标签

chat-panel 头部和 sidebar 会话列表项 MUST 不再显示"单聊/群聊 · N 位 Agent"副标题行。单聊默认标题直接使用 agent 名称，群聊默认标题使用"群聊（N）"格式。

#### Scenario: 单聊对话不显示模式标签
- **WHEN** 用户查看单聊对话
- **THEN** chat-panel 头部和 sidebar 会话列表项不显示"单聊 · 1 位 Agent"

#### Scenario: 群聊对话不显示模式标签
- **WHEN** 用户查看群聊对话
- **THEN** chat-panel 头部和 sidebar 会话列表项不显示"群聊 · N 位 Agent"

#### Scenario: 新建单聊默认标题为 agent 名称
- **WHEN** 用户创建单聊对话（选择 1 个 agent）
- **THEN** 对话默认标题为该 agent 的名称（不再使用"与 xx 的对话"格式）

#### Scenario: 新建群聊默认标题为"群聊（N）"
- **WHEN** 用户创建群聊对话（选择 N 个 agent，N ≥ 2）
- **THEN** 对话默认标题为"群聊（N）"（不再使用 agent 名称拼接格式）