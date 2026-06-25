# 阶段一：全局认知 — AgentHub 深度学习指南

> **学习目标**：不翻代码也能掌握 AgentHub 是什么、怎么分层、数据怎么流动、核心概念间的关系。
> 完成后你应该能口述「用户发消息 → UI 实时看到回复」经过了哪些模块。

---

## 目录

1. [项目定位与核心理念](#1-项目定位与核心理念)
2. [技术栈全景](#2-技术栈全景)
3. [五层架构深度剖析](#3-五层架构深度剖析)
4. [八个核心实体与关系](#4-八个核心实体与关系)
5. [StreamEvent：系统的腰部协议](#5-streamevent系统的腰部协议)
6. [MessagePart：消息不是字符串](#6-messagepart消息不是字符串)
7. [Artifact：独立于消息的产物](#7-artifact独立于消息的产物)
8. [Adapter：统一适配器层](#8-adapter统一适配器层)
9. [工具系统：Agent 的副作用入口](#9-工具系统agent-的副作用入口)
10. [Orchestrator：多 Agent 编排引擎](#10-orchestrator多-agent-编排引擎)
11. [一条消息的完整生命周期](#11-一条消息的完整生命周期)
12. [前后端分离架构](#12-前后端分离架构)
13. [安全与沙箱机制](#13-安全与沙箱机制)
14. [目录结构与代码地图](#14-目录结构与代码地图)
15. [自检清单](#15-自检清单)

---

## 1. 项目定位与核心理念

### 一句话定位

> **AgentHub** = 把多 Agent 协作做成 IM 群聊体验。
> Agent 是「联系人」，对话是「工作空间」，Orchestrator 是「群里的项目经理」。

### 五大核心能力

| 能力 | 说明 |
|------|------|
| **IM 范式会话** | 单聊/群聊/多会话并行，搜索/置顶/归档/未读 |
| **统一适配器层** | 一个接口接入 Claude Code、Codex、DeepSeek、OpenAI 等 |
| **Orchestrator 编排** | 自动拆任务 → DAG 并行调度 → 聚合结果 |
| **产物内联预览** | 网页/文档/PPT/图片/代码，面板内预览与二次编辑 |
| **Workspace 沙箱** | 每个会话独立工作目录，Agent 读写文件/跑命令都受限 |

### 运行形态

- **本地运行**：SQLite 文件数据库，不依赖任何云服务
- **前后端分离**：Python FastAPI 后端 + Next.js 前端
- **跨端**：Web（主力） + Electron 桌面版 + Capacitor 移动伴随 App

### IM 隐喻理解

把整个系统想象成一个聊天软件：

```
微信/钉钉               AgentHub
─────────              ─────────
联系人          ←→     Agent（智能体）
聊天窗口        ←→     Conversation（会话）
一条消息        ←→     Message（消息）
群聊 @某人      ←→     mentionedAgentIds
群里项目经理    ←→     Orchestrator
文件/图片       ←→     Artifact（产物）+ Attachment（附件）
```

---

## 2. 技术栈全景

### 前端（L4-L5）

| 技术 | 版本/说明 | 为什么选 |
|------|----------|---------|
| Next.js | 16 (App Router) | SSR/CSR 灵活，**注意 16 与旧版有 breaking change** |
| React | 19 | 最新并发特性 |
| TypeScript | strict 模式 | 不写 `any`，用 `unknown` + narrow |
| Tailwind CSS | v4 + shadcn/ui | 原子化 CSS，组件复制模式 |
| Zustand | + Immer middleware | 轻量状态管理，不用 Redux |
| SSE | EventSource API | 一条全局连接，不用 WebSocket |

### 后端（L1-L3）

| 技术 | 版本/说明 | 为什么选 |
|------|----------|---------|
| FastAPI | Python 3.11 | async 原生，自动 OpenAPI 文档 |
| SQLAlchemy | 2.0 async + aiosqlite | 成熟 ORM，异步支持 |
| Pydantic | v2 | 数据验证 + 序列化，替代 Zod |
| SQLite | WAL 模式 | 本地优先，零运维 |

### AI SDK（后端）

| SDK | 对接平台 |
|-----|---------|
| `anthropic` (Python) | Claude |
| `openai` (Python) | OpenAI / DeepSeek / 火山方舟 / 通用兼容 |

### 工程化

| 工具 | 用途 |
|------|------|
| pnpm | 前端包管理（monorepo workspaces） |
| pip/venv | 后端包管理 |
| Drizzle | 前端保留类型定义（DB 由后端 SQLAlchemy 拥有） |

---

## 3. 五层架构深度剖析

这是理解整个系统最重要的部分。AgentHub 采用严格的五层分层架构：

```
┌─────────────────────────────────────────────────────────────┐
│ L5  UI 组件 (React / shadcn)              src/components/      │  ← 前端
│ L4  State + Transport (Zustand + SSE)     src/stores/ src/lib/ │  ← 前端
├─────────────────────────────────────────────────────────────┤
│                    HTTP (REST + SSE)  ↕  跨进程边界            │
├─────────────────────────────────────────────────────────────┤
│ L3  Application Services                  backend/app/services/│  ← Python
│     (AgentRunner · Orchestrator · ConversationService ·       │
│      EventBus · ToolExecutor · ...)                           │
│ L2  Agent Platform Adapters               backend/app/adapters/│  ← Python
│     (Claude · Custom · Mock)                                  │
│ L1  Persistence (SQLAlchemy + SQLite)      backend/app/db/     │  ← Python
└─────────────────────────────────────────────────────────────┘
```

### 三条铁律（必须牢记）

1. **UI 永远不直接调 LLM SDK**，必须经过 L3 服务层
2. **Adapter 永远不写 DB**，它只负责事件流翻译
3. **Orchestrator 是特殊 Agent**，走同一个 AgentRunner，不是独立服务

### 各层职责

| 层 | 职责 | 关键文件 |
|----|------|---------|
| **L5** | 渲染 UI，响应用户交互 | `src/components/*.tsx` |
| **L4** | 管理前端状态，接收 SSE 事件 | `src/stores/app-store.ts`, `stream-provider.tsx` |
| **L3** | 业务逻辑核心：会话管理、Agent 执行、工具执行、事件广播 | `backend/app/services/` |
| **L2** | 屏蔽不同 LLM 平台差异，输出统一事件流 | `backend/app/adapters/` |
| **L1** | 数据持久化 + 文件系统管理 | `backend/app/db/`, workspace 文件系统 |

### 层间数据流

```
用户点击发送
  → L5 (ChatPanel) 调 API
  → L4 (api.ts) POST /api/conversations/{id}/messages
  ── HTTP 跨进程 ──
  → L3 (conversation_service) 持久化用户消息
  → L3 (agent_runner) 启动 run
  → L2 (adapter.stream) 调 LLM，产出 StreamEvent
  → L3 (agent_runner) 持久化事件 + 推 EventBus
  ── SSE 跨进程 ──
  → L4 (stream-provider) 收事件
  → L4 (app-store reducer) 应用事件到状态
  → L5 (React) 重渲染 UI
```

---

## 4. 八个核心实体与关系

### 实体一览

| 实体 | ID 前缀 | 一句话说明 |
|------|---------|-----------|
| **Agent** | `ag_` | 可对话的智能体（IM 里的「联系人」） |
| **Conversation** | `conv_` | 会话/聊天窗口 |
| **Message** | `msg_` | 消息容器，真正内容在 `parts` 数组 |
| **Artifact** | `art_` | Agent 产出的独立产物（网页/文档/PPT...） |
| **Workspace** | `ws_` | 每个会话的独立工作目录 |
| **Tool** | — | Agent 可调用的能力（代码中声明，不入库） |
| **AgentRun** | `run_` | 一次 Agent 执行的元信息 |
| **Attachment** | `att_` | 用户上传的附件（图片/文件） |

### 实体关系图

```
Conversation ─1:1─ Workspace
     │
     ├─1:N─ Message ─0:N─ artifact_ref part ──┐
     │         │            ─0:N─ image/file_attachment part ──┐
     │         │                              │                │
     │         └─N:1─ Agent                   ▼                │
     │                                    Artifact ─N:1─ Artifact (parent version)
     │                                        │                │
     ├─1:N─ AgentRun                          │                │
     │         │                              │                │
     │         ├─N:1─ Agent                   │                ▼
     │         └─0:N─ AgentRun (parent)       │            Attachment
     │                                        │
     │         created_by ────────────────────┘
     │
     └─1:N─ Attachment
```

### Agent 关键字段

```
Agent {
  id, name, avatar, description    // 基本信息
  systemPrompt                      // 决定行为的核心提示
  adapterName: 'claude-code' | 'codex' | 'custom' | 'mock'
  modelProvider?: 'anthropic' | 'openai' | 'deepseek' | 'volcano-ark' | 'openai-compatible'
  modelId?: string                  // 厂商内部模型 ID
  apiKey?: string                   // per-agent 自定义 key（最高优先级）
  apiBaseUrl?: string               // per-agent 自定义 API endpoint
  toolNames: string[]               // 该 Agent 可调用的工具列表
  isBuiltin: boolean                // 内置 Agent 不可删
  isOrchestrator: boolean           // 标记为协调者
  capabilities: string[]            // 能力标签，Orchestrator 据此选派
}
```

**五种 Adapter 对应的工具策略**：
- `claude-code`：用 SDK 内置工具集，`toolNames` 强制 `[]`
- `codex`：用 SDK 内置工具集，`toolNames` 强制 `[]`
- `custom`：用 `toolNames` 声明可用工具
- `mock`：预设脚本，不真正调工具

### Conversation 关键字段

```
Conversation {
  id, title
  mode: 'single' | 'group'         // 单聊 vs 群聊
  agentIds: string[]                // 参与的 Agent
  pinnedMessageIds: string[]        // 置顶消息（上限 5 条）
  fsWriteApprovalMode: 'auto' | 'review'  // Agent 写文件的审批策略
  archived: boolean
}
```

- 单聊 `agentIds.length === 1`
- 群聊 `agentIds.length >= 2`，且最多 1 个 Orchestrator
- 创建时自动创建关联的 Workspace（1:1）

### Message 关键字段

```
Message {
  id, conversationId
  role: 'user' | 'agent' | 'system'
  agentId?: string                  // agent 消息必填
  parts: MessagePart[]              // 真正内容在 parts 数组！
  status: 'streaming' | 'complete' | 'error' | 'aborted'
  runId?: string                    // 由哪个 AgentRun 产生
  mentionedAgentIds: string[]       // 用户 @ 提及的 Agent
}
```

**核心认知**：Message 是「容器」，真正内容在 `parts` 数组中（后面详述）。

### Workspace 两种模式

```
Workspace {
  id, conversationId                // 与会话 1:1
  mode: 'sandbox' | 'local'
  rootPath: string                  // 隔离目录绝对路径
  boundPath: string | null          // local 模式绑定的真实项目路径
}
```

| 模式 | 说明 | 配额 |
|------|------|------|
| **sandbox** | 隔离目录（`.agenthub-data/workspaces/<conv_id>/`） | 100MB / 1000 文件 |
| **local** | 绑定用户真实项目 | 不限（用户自管理） |

---

## 5. StreamEvent：系统的腰部协议

StreamEvent 是整个系统最重要的协议——它像「腰椎」一样连接所有层。

### 设计原则

1. **细粒度**：run / message / part / tool / artifact / dispatch 各自有事件
2. **增量**：流式 part 用 `delta` 事件追加，不重传全量
3. **可恢复**：所有事件携带稳定 ID
4. **传输无关**：事件是纯数据，不绑死 SSE

### 事件类型分类

```
StreamEvent 分为 7 大类：

1. Run 生命周期         run.start / run.end
2. Message 生命周期     message.start / message.end / message.added / message.removed
3. Part 增量（最高频）  part.start / part.delta / part.end
4. 工具调用             tool.call / tool.result
5. 产物                 artifact.create / artifact.update / deploy.status
6. Orchestrator 调度    dispatch.plan / dispatch.start / dispatch.end
7. 审批与安全           fs_write.pending/resolved · bash_command.pending/resolved
                        + run.usage · heartbeat
```

### 事件流示例：单聊 Agent 回复文字 + 产物

```
时间线 →

run.start         (runId=r1, agentId=cc)          ← run 开始
message.start     (messageId=m1, agentId=cc)      ← 创建消息壳
part.start        (m1, 0, {type:'text'})           ← 开始第一个文字 part
part.delta        (m1, 0, {type:'text.append', text:'好的，'})   ← 增量追加
part.delta        (m1, 0, {type:'text.append', text:'我来写...'})
part.end          (m1, 0)                          ← part 完成
tool.call         (m1, c1, 'write_artifact', {...}) ← 调工具
artifact.create   ({id:'a1', type:'web_app'})       ← 产物创建
tool.result       (m1, c1, {artifactId:'a1'})       ← 工具返回
part.start        (m1, 1, {type:'artifact_ref', artifactId:'a1'})  ← 引用注入
message.end       (m1)                             ← 消息完成
run.end           (r1, 'complete')                 ← run 完成
```

### 事件流示例：群聊 Orchestrator 调度

```
run.start(r1, orch)
message.start(m1, orch, r1)
part.start(m1, 0, {type:'thinking'})
part.delta(...)
tool.call(m1, c1, 'plan_tasks', {...})
dispatch.plan(r1, [t1→pm, t2→design dependsOn t1])   ← 计划发布
message.end(m1)

dispatch.start(r1, r2, t1, pm)                        ← t1 启动
  run.start(r2, pm, parentRunId=r1)
  ...子 Agent 工作...
  run.end(r2, 'complete')
dispatch.end(t1, 'complete')

dispatch.start(r1, r3, t2, design)                    ← t2 启动（依赖 t1）
  ...
dispatch.end(t2, 'complete')

message.start(m4, orch, r1)                           ← 聚合消息
part.start(m4, 0, {type:'text'})
...聚合总结...
message.end(m4)
run.end(r1, 'complete')
```

### 持久化 vs 透传

| 事件类型 | 落库？ | 说明 |
|---------|--------|------|
| `run.*` | ✅ | `agent_runs` 表 |
| `message.start/end` | ✅ | `messages` 表 |
| `part.start/delta` | ✅ | `messages.parts` JSON 列 |
| `tool.call/result` | ✅ | `messages.parts` 中的 tool_use/tool_result part |
| `artifact.*` | ✅ | `artifacts` 表 |
| `dispatch.*` | ❌ | 透传（信息来自 plan_tasks + agent_runs） |
| `fs_write/bash_command.*` | ❌ | 内存 pending 队列 |
| `heartbeat` | ❌ | 防断连 |

**高频写入优化**：`part.delta` 使用内存缓冲 + 100ms 定时 flush，避免每个 delta 都打 DB。

---

## 6. MessagePart：消息不是字符串

**核心认知**：Message = parts 数组，不是 markdown 字符串。

### 10 种 Part 类型

```typescript
type MessagePart =
  | { type: 'text';           content: string }           // Agent 文字输出
  | { type: 'code';           language: string; content } // 独立代码块
  | { type: 'thinking';       content: string }           // 思考链（可折叠）
  | { type: 'tool_use';       callId; toolName; args }    // 工具调用记录
  | { type: 'tool_result';    callId; result; isError }   // 工具执行结果
  | { type: 'artifact_ref';   artifactId: string }        // 引用产物
  | { type: 'deploy_status';  deployment }                // 部署状态
  | { type: 'deploy_candidates'; candidates }             // 部署候选
  | { type: 'image_attachment'; attachmentId; ... }       // 图片附件
  | { type: 'file_attachment';  attachmentId; ... }       // 文件附件
```

### 可增量 vs 一次性

| 类型 | 可增量（delta 追加） | 说明 |
|------|---------------------|------|
| `text` | ✅ `text.append` | 流式追加文字 |
| `code` | ✅ `code.append` | 流式追加代码 |
| `thinking` | ✅ `thinking.append` | 流式追加思考 |
| `tool_use` | ❌ | 一次性完整 push |
| `tool_result` | ❌ | 工具执行完才有 |
| `artifact_ref` | ❌ | AgentRunner 注入 |
| 其余 | ❌ | 一次性 |

### tool_use + tool_result 的配对机制

```
1. Adapter emit tool.call(callId='call_xxx', toolName='write_artifact', args={...})
   → 前端持久化为 tool_use part

2. 工具执行 → toolRegistry.execute()

3. Adapter emit tool.result(callId='call_xxx', result={...}, isError=false)
   → 前端持久化为 tool_result part

4. 前端渲染时按 callId 合并为一张工具卡片
   显示「调用中 / 已完成 / 失败」三态
```

**失败兜底**：run 失败或中止时，AgentRunner 为未配对的 `tool_use` 补 `isError=true` 的 `tool_result`。

### artifact_ref 的注入路径（重要！）

`artifact_ref` 不是 Adapter 直接 emit 的，而是由 AgentRunner 注入：

```
1. Adapter 执行 write_artifact 工具 → 返回 { artifactId }
2. Adapter emit artifact.create（带完整 artifact 行）
3. AgentRunner 接到 artifact.create →
   在当前 message 末尾 push artifact_ref part
   并补发 part.start 事件
```

**为什么这样设计**：保持「Adapter 只翻译事件，不操心 message.parts 结构」的边界。AgentRunner 是唯一持有 message 流的角色。

---

## 7. Artifact：独立于消息的产物

**核心认知**：Artifact 独立于 Message，有自己的生命周期、版本、二次编辑。

### 七种产物类型

| 类型 | 存储位置 | 用途 |
|------|---------|------|
| `web_app` | DB JSON（files + entry） | 完整 HTML/CSS/JS 包，iframe 渲染 |
| `document` | DB JSON（markdown content） | 文档/报告 |
| `image` | DB JSON（url + alt） | URL 或 data URI |
| `ppt` | DB JSON（slides 数组） | 幻灯片，分页预览 + 导出 .pptx |
| `diagram` | DB JSON（Mermaid source） | 流程图/架构图 |
| `code_file` | 仅路径入 DB，文件在 workspace | 大代码文件 |
| `project` | 仅文件清单入 DB | 多文件代码项目 |

### 版本链

```
v1 (art_001, version=1, parentArtifactId=null)
 ↑
v2 (art_002, version=2, parentArtifactId=art_001)  ← 新版本是新行
 ↑
v3 (art_003, version=3, parentArtifactId=art_002)
```

三条写新版本的路径：
1. **Agent 驱动**：`write_artifact` 工具传 `parentArtifactId`
2. **用户驱动**：在预览面板编辑 → 提交为新版本
3. **workspace code_file**：面板编辑文件 → 创建新版本记录

### 消息只持有引用

```
Message.parts = [
  { type: 'text', content: '我做了一个组件：' },
  { type: 'artifact_ref', artifactId: 'art_001' }   ← 只是引用！
]
```

产物本身存在 `artifacts` 表，有独立的生命周期。删除产物不删消息，消息里的 `artifact_ref` 会显示「产物已删除」墓碑卡片。

---

## 8. Adapter：统一适配器层

### 四种 Adapter

| Adapter | 对接平台 | 核心 SDK |
|---------|---------|---------|
| `MockAdapter` | 无（假数据） | 预设脚本 |
| `CustomAgentAdapter` | DeepSeek/OpenAI/火山方舟/通用兼容 | OpenAI SDK |
| `ClaudeCodeAdapter` | Claude Code | `@anthropic-ai/claude-agent-sdk` |
| `CodexAdapter` | OpenAI Codex | `@openai/codex-sdk` |

### 统一接口

```python
# 所有 Adapter 实现同一接口
class AgentPlatformAdapter:
    name: str
    async def stream(self, input: AdapterInput, signal) -> AsyncIterator[StreamEvent]:
        ...
```

### Adapter 的唯一职责

> 把厂商 SDK 的输出翻译成 StreamEvent。

**不做的事**：不写 DB、不发 SSE、不持有跨调用状态。

### API Key 四层解析链

```
优先级从高到低：

1. agents.api_key              ← per-agent 自定义 key（最高优先级）
2. app_settings.<provider>     ← 用户在「设置」面板自填
3. process.env.<PROVIDER>_API_KEY  ← .env 文件兜底
4. SDK OAuth fallback           ← 仅 Claude Code
```

Adapter 只看 `AdapterInput.api_key` 一个字段，不关心来源。

---

## 9. 工具系统：Agent 的副作用入口

### 12 个内置工具

| 工具 | 用途 | 副作用 |
|------|------|--------|
| `write_artifact` | 创建产物 | 写 DB |
| `read_artifact` | 读产物内容 | 读 DB |
| `deploy_artifact` | 部署 web_app | 写发布目录 |
| `deploy_workspace` | 部署 workspace 静态目录 | 复制文件 |
| `read_attachment` | 读用户上传附件 | 读文件系统 |
| `ask_user` | 向用户发问 | 等待回答（内存 pending） |
| `plan_tasks` | Orchestrator 拆任务 | 无（输出端工具） |
| `report_task_result` | 子任务上报结果 | 无（输出端工具） |
| `fs_read` | 读 workspace 文件 | 读文件系统 |
| `fs_write` | 写 workspace 文件 | 写文件系统（需审批） |
| `bash` | 跑 shell 命令 | 进程/文件系统（需审批） |

### 工具接口

```python
class ToolDef:
    name: str                    # 全局唯一
    description: str             # 给 LLM 看的说明
    parameters: dict             # JSON Schema
    handler: (args, ctx) -> ToolResult  # 异步处理函数

class ToolContext:
    conversation_id: str
    workspace_path: str
    agent_id: str
    run_id: str
    abort_signal: AbortSignal    # 必须尊重！
```

### 工具调用生命周期

```
LLM 决定调用
  → Adapter emit tool.call (callId, toolName, args)
  → AgentRunner 持久化为 tool_use part
  → toolRegistry.execute(name, args, ctx)
  → Adapter emit tool.result (callId, result, isError)
  → AgentRunner 持久化为 tool_result part
  → 前端按 callId 合并为工具卡片
```

---

## 10. Orchestrator：多 Agent 编排引擎

### 定位

Orchestrator 是「特殊 Agent」：`isOrchestrator: true`，走同一个 AgentRunner，不是独立服务。

### 触发条件

```
群聊 (mode === 'group'):
  用户发消息:
    if 有 @ 提及 → 直接为被 @ 的 Agent 创建独立 Run
    else → 触发 Orchestrator 的 Run

单聊 (mode === 'single'):
  直接触发那个 Agent，Orchestrator 不参与
```

### 三阶段工作流

```
Stage 1: PLAN（规划）
  输入：群聊上下文 + 用户消息 + 可用 Agent 列表
  行为：LLM 调用 plan_tasks 工具输出结构化计划
  输出：dispatch.plan（包含 tasks + dependsOn）
  ↓ 用户审批

Stage 2: EXECUTE（执行）
  输入：plan.tasks
  行为：按 dependsOn 做 DAG 拓扑排序
        同一波次无依赖任务并行（受全局上限 4 约束）
        子 Agent 必须调用 report_task_result 上报
  输出：Map<taskId, TaskResult>

Stage 3: AGGREGATE（聚合）
  输入：所有子任务结果
  行为：再调一次 LLM，生成聚合总结
  输出：一条包含完成情况 + 失败原因 + 产物链接的消息
```

### DAG 调度示例

```
Plan: t1(无依赖), t2(依赖t1), t3(无依赖), t4(依赖t2,t3)

波次 1: [t1, t3] 并行     ← 无依赖，立即启动
波次 2: [t2]               ← 等 t1 完成
波次 3: [t4]               ← 等 t2, t3 都完成
```

### 失败降级策略

- **不自动重试**：AgentRunner 层不做重试
- **如实上报**：失败任务标 `status='failed'`
- **级联跳过**：上游失败 → 下游 `skipped`
- **动态重规划**：一轮失败后可触发补救 plan（最多 1 轮）

---

## 11. 一条消息的完整生命周期

这是理解数据流最关键的部分。追踪一条用户消息从发送到 UI 显示的完整路径：

### 单聊场景

```
1. 用户在 ChatPanel 输入消息，点击发送
   │
2. src/lib/api.ts → POST /api/conversations/{id}/messages
   │
   ── HTTP 请求到达 Python 后端 ──
   │
3. L3: conversation_service.send_message()
   ├─ 持久化 user message (status='complete')
   ├─ 找到该会话的 Agent
   └─ 启动 asyncio.Task → agent_runner.run()
   │
4. L3: agent_runner.execute_run()
   ├─ build_adapter_input()  ← 历史注入 + token 预算 + key 选择
   ├─ 发 run.start 事件 → 持久化到 agent_runs 表 → EventBus 广播
   ├─ 创建 agent message (status='streaming')
   └─ 发 message.start + part.start 事件
   │
5. L2: adapter.stream(input, signal) → AsyncIterator[StreamEvent]
   ├─ 调 LLM API（Claude/OpenAI/DeepSeek...）
   ├─ 流式接收 chunks
   ├─ 翻译为 StreamEvent:
   │   part.delta (text.append)    ← 增量文字
   │   tool.call                   ← 工具调用
   │   tool.result                 ← 工具结果
   │   artifact.create             ← 产物创建
   └─ 每个事件 yield 出去
   │
6. L3: agent_runner.consume_stream()
   ├─ persist_event()  ← 事件落 DB（part.delta 用缓冲 + 100ms flush）
   └─ event_bus.publish() → SSE 广播
   │
   ── SSE 事件推到前端 ──
   │
7. L4: stream-provider.tsx 的 EventSource.onmessage
   ├─ JSON.parse(event.data)
   └─ appStore.applyEvent(event)
   │
8. L4: app-store.ts 的 reducer
   ├─ 按 event.type 分发
   ├─ part.delta → 追加到 messages[id].parts[index].content
   ├─ run.end → 更新消息 status
   └─ 触发 React 重渲染
   │
9. L5: React 组件重渲染
   ├─ MessageList 显示新内容
   ├─ ToolUsePart 显示工具卡片
   └─ ArtifactPreviewPanel 滑入产物预览
```

### 群聊场景（Orchestrator）

```
1-3 同上
   │
4. L3: agent_runner 检测到目标是 Orchestrator
   └─ 转 orchestrator.execute_orchestrator_run()
   │
5. Stage 1: PLAN
   ├─ adapter.stream() → LLM 调 plan_tasks
   ├─ AgentRunner 拦截 plan_tasks 调用
   ├─ 编译 plan + 语义校验
   ├─ 发 dispatch.plan.pending → 等用户审批
   └─ 用户批准 → 发 dispatch.plan
   │
6. Stage 2: EXECUTE
   ├─ DAG 拓扑排序
   ├─ 按波次并行启动子 AgentRun
   │   每个子任务: AgentRunner.run(subAgent, parentRunId=orchRunId)
   ├─ 子 Agent 完成后必须调 report_task_result
   └─ 收集所有 TaskResult
   │
7. Stage 3: AGGREGATE
   ├─ 再调一次 LLM，注入所有任务结果
   └─ Orchestrator 生成聚合消息
   │
8-9 同单聊
```

---

## 12. 前后端分离架构

### 通信方式

| 方向 | 协议 | 说明 |
|------|------|------|
| 前端 → 后端 | REST (HTTP) | `src/lib/api.ts` 统一封装 |
| 后端 → 前端 | SSE | `stream-provider.tsx` EventSource |

### API Base URL 配置

```
.env.local:
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

- 前端所有 API 调用都加 `API_BASE_URL` 前缀
- 默认空串 = 同源（兼容旧架构）
- 设为 `http://localhost:8000` = 连接独立 Python 后端

### 前后端共享类型

`src/shared/` 目录定义了前后端共享的类型契约：

```
src/shared/
├── types.ts          ← StreamEvent / MessagePart / Artifact 等核心类型
├── constants.ts      ← 常量（PIN_LIMIT 等）
├── model-registry.ts ← 模型清单
└── ppt-theme.ts      ← PPT 主题配置
```

**这些是纯类型定义，不含逻辑**。后端 Pydantic schemas（`backend/app/schemas/`）与之对应，使用 snake_case 字段 + camelCase 别名保持兼容。

---

## 13. 安全与沙箱机制

### LLM 输出永远是不可信输入

- HTML/JS 在 iframe 渲染时必须 `sandbox="allow-scripts"`（不给 `allow-same-origin`）
- SQL / shell 命令必须经过白名单或参数化

### Bash 命令安全

**双平台黑名单**：
- POSIX: `rm -rf /`, `sudo`, `chmod 777`, fork bomb, `curl|bash` 等
- Windows: `Remove-Item -Recurse -Force`, `format C:`, `shutdown`, `reg delete` 等

**关键命令审批**：安装依赖、git reset、批量删除等不直接禁止，但需要用户确认。

### Workspace 沙箱

```
所有 fs_read / fs_write / bash:
  path.resolve() 后必须落在 effective cwd 子树内
  bash 的 cwd 强制为 effective cwd
```

| 模式 | 配额 | 说明 |
|------|------|------|
| sandbox | 100MB / 1000 文件 | 隔离目录，安全 |
| local | 不限 | 用户真实项目，自己管理 |

### fs_write 审批

| 模式 | 行为 |
|------|------|
| `auto` | Agent 写入直接生效 |
| `review`（默认） | 弹 diff 对话框，用户决定应用/拒绝 |

### API Key 安全

- 绝不在代码中硬编码 key
- 不引入 keychain/第三方加密（本地单用户，文件权限已够）
- 缺失 key 时由 adapter 抛清晰错误，不阻止启动

---

## 14. 目录结构与代码地图

### 顶层结构

```
bitdance-agenthub-main/
├── backend/              ★ Python 后端（L1-L3 全部业务逻辑）
│   ├── app/
│   │   ├── main.py         FastAPI 入口
│   │   ├── config.py       配置
│   │   ├── db/             L1: SQLAlchemy 模型 + 引擎
│   │   ├── schemas/        Pydantic 模型（事件/消息/产物/请求）
│   │   ├── services/       ★ L3: 核心大头（26 个服务）
│   │   ├── adapters/       L2: 4 种 Adapter
│   │   ├── tools/          12 个内置工具
│   │   ├── api/            51 个 REST 路由
│   │   └── utils/          工具函数（安全/平台/ID/token 估算）
│   └── tests/              390 个测试
├── src/                  前端（L4-L5）+ 共享类型
│   ├── app/              Next.js 页面入口
│   ├── components/       59 个 React 组件
│   ├── lib/              REST 客户端 + 工具
│   ├── stores/           Zustand store
│   ├── shared/           ★ 前后端共享类型
│   └── db/               仅保留类型（DB 由后端拥有）
├── specs/                ★ 18 份编号规格文档
├── openspec/             OpenSpec 能力契约 + 变更提案
├── electron/             桌面版外壳
├── apps/mobile/          移动伴随 App
├── scripts/              构建辅助脚本
├── CLAUDE.md             AI 协作规则
├── ARCHITECTURE.md       架构与目录说明
├── OVERVIEW.md           代码地图
└── QUICKSTART.md         快速启动指南
```

### 后端关键文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `services/agent_runner.py` | ~1365 | **最核心**：per-run 生命周期 |
| `services/orchestrator.py` | ~1369 | 三阶段调度 |
| `services/conversation_service.py` | — | 会话/消息 CRUD |
| `services/event_bus.py` | — | SSE 事件总线 |
| `adapters/custom_adapter.py` | — | OpenAI 兼容 + tool loop |
| `adapters/claude_adapter.py` | — | Anthropic API |
| `schemas/events.py` | — | 30+ StreamEvent 定义 |

### 前端关键文件

| 文件 | 说明 |
|------|------|
| `stores/app-store.ts` | Zustand + Immer，事件 reducer 在此应用 |
| `components/stream-provider.tsx` | SSE 全局连接 |
| `lib/api.ts` | REST 客户端 |
| `shared/types.ts` | StreamEvent / MessagePart 等核心类型 |
| `components/chat-panel.tsx` | 聊天主面板 |
| `components/message-parts.tsx` | 10 种 Part 渲染 |
| `components/artifact-preview-panel.tsx` | 产物预览 |

### 9 张数据库表

| 表 | 说明 |
|----|------|
| `agents` | AI 代理 |
| `conversations` | 会话 |
| `messages` | 消息（parts JSON 列） |
| `artifacts` | 产物（content JSON 列） |
| `workspaces` | 工作区 |
| `attachments` | 附件 |
| `agent_runs` | 运行记录（usage JSON 列） |
| `conversation_context_summaries` | 上下文压缩摘要 |
| `app_settings` | 全局设置（单行表） |

---

## 15. 自检清单

完成阶段一学习后，你应该能回答以下问题：

### 基础概念

- [ ] AgentHub 的一句话定位是什么？
- [ ] 五个核心能力分别是什么？
- [ ] 五层架构从 L1 到 L5 分别是什么？三条铁律是什么？
- [ ] 项目使用了哪些核心技术栈？前端和后端分别是什么？

### 实体与关系

- [ ] 八个核心实体分别是什么？它们的 ID 前缀是什么？
- [ ] Conversation 和 Workspace 是什么关系？
- [ ] Message 和 MessagePart 是什么关系？为什么说「消息不是字符串」？
- [ ] Artifact 为什么独立于 Message？版本链怎么实现？
- [ ] Agent 的 `adapterName` 和 `toolNames` 有什么关系？

### 数据流

- [ ] StreamEvent 在整个系统中扮演什么角色？分几大类？
- [ ] `part.delta` 事件为什么需要缓冲 flush？
- [ ] `artifact_ref` part 是由谁注入的？为什么不直接让 Adapter 发？
- [ ] 描述从「用户发消息」到「UI 显示回复」的完整路径

### 适配器

- [ ] 四种 Adapter 分别对接什么平台？
- [ ] Adapter 的唯一职责是什么？它不做哪些事？
- [ ] API Key 的四层解析链是什么？

### 工具与安全

- [ ] 12 个内置工具分别是什么？
- [ ] `plan_tasks` 和 `report_task_result` 为什么是「输出端工具」？
- [ ] Workspace 的 sandbox 和 local 模式有什么区别？
- [ ] fs_write 的 review 审批模式是怎么工作的？

### Orchestrator

- [ ] Orchestrator 和普通 Agent 有什么区别？
- [ ] 三阶段工作流分别做什么？
- [ ] DAG 调度算法是怎么处理依赖关系的？
- [ ] 失败降级策略是什么？动态重规划是什么？

### 架构与部署

- [ ] 前后端通过什么方式通信？
- [ ] `NEXT_PUBLIC_API_BASE_URL` 环境变量的作用是什么？
- [ ] 9 张数据库表分别存什么？

---

> **下一步**：如果以上问题都能回答，进入阶段二（技术栈基础补齐）和阶段三（后端核心自底向上阅读）。
>
> **推荐阅读顺序**：
> 1. `CLAUDE.md` §1-3（项目背景 + 技术栈 + 架构原则）
> 2. `ARCHITECTURE.md`（架构与目录说明）
> 3. `OVERVIEW.md`（代码地图）
> 4. `specs/01-core-entities.md`（核心实体）
> 5. `specs/02-stream-events.md`（StreamEvent 协议）
> 6. `specs/03-message-parts.md`（MessagePart 类型）
