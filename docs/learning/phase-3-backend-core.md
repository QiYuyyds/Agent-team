# 阶段三：后端核心 — 自底向上 — AgentHub 深度学习指南

> **学习目标**：从数据库到 HTTP 接口，逐层拆解 AgentHub 后端核心代码。
> 每层配合实际代码片段 + 设计决策分析，理解「为什么这么写」。
> 预计耗时 5-7 天（每天 2-3 小时）。

---

## 目录

1. [后端架构总览](#1-后端架构总览)
2. [L1 持久化层：数据库模型与引擎](#2-l1-持久化层数据库模型与引擎)
3. [L2 适配器层：屏蔽平台差异](#3-l2-适配器层屏蔽平台差异)
4. [L3 服务层（上）：EventBus + ConversationService](#4-l3-服务层上eventbus--conversationservice)
5. [L3 服务层（中）：AgentRunner 执行引擎](#5-l3-服务层中agentrunner-执行引擎)
6. [L3 服务层（下）：Orchestrator 多 Agent 编排](#6-l3-服务层下orchestrator-多-agent-编排)
7. [工具系统：ToolDef + ToolRegistry](#7-工具系统tooldef--toolregistry)
8. [API 路由层：HTTP 接口](#8-api-路由层http-接口)
9. [消息完整生命周期追踪](#9-消息完整生命周期追踪)
10. [关键设计模式总结](#10-关键设计模式总结)
11. [自检清单](#11-自检清单)

---

## 1. 后端架构总览

### 1.1 后端分层视图

```
┌─────────────────────────────────────────────────────────┐
│  API 路由层 (api/)                                       │
│  conversations.py / agents.py / stream.py / messages.py │
├─────────────────────────────────────────────────────────┤
│  L3 服务层 (services/)                                    │
│  conversation_service → agent_runner → orchestrator     │
│  event_bus ← 所有服务发布事件                             │
├─────────────────────────────────────────────────────────┤
│  L2 适配器层 (adapters/)                                  │
│  MockAdapter / CustomAdapter / ClaudeAdapter             │
│  AgentRegistry: agent.adapter_name → 具体 Adapter        │
├─────────────────────────────────────────────────────────┤
│  工具系统 (tools/)                                        │
│  ToolDef + ToolRegistry + 12 个具体工具                   │
├─────────────────────────────────────────────────────────┤
│  L1 持久化层 (db/)                                        │
│  SQLAlchemy 2.0 模型 + 异步引擎 + SQLite                 │
└─────────────────────────────────────────────────────────┘
```

### 1.2 核心数据流

```
用户发消息 → POST /api/conversations/{id}/messages
         → conversation_service.send_message()
         → agent_runner.run()  [spawn asyncio.Task]
         → execute_simple_run() 或 execute_orchestrator_run()
         → adapter.stream()     [AsyncIterator[StreamEvent]]
         → consume_stream()     [persist + publish 每个事件]
         → event_bus.publish()
         → GET /api/stream (SSE) → 前端
```

### 1.3 文件导航地图

| 层 | 文件 | 职责 |
|---|---|---|
| API | `api/stream.py` (46 行) | SSE 全局事件流 |
| API | `api/conversations.py` (312 行) | 会话 CRUD + 发消息 |
| API | `api/agents.py` (716 行) | Agent CRUD + 草稿生成 |
| L3 | `services/conversation_service.py` (1015 行) | 会话业务逻辑核心 |
| L3 | `services/agent_runner.py` (1366 行) | Agent 执行引擎 |
| L3 | `services/orchestrator.py` (1370 行) | 多 Agent DAG 编排 |
| L3 | `services/event_bus.py` (94 行) | 进程内事件扇出 |
| L2 | `adapters/base.py` (76 行) | Adapter 抽象契约 |
| L2 | `adapters/custom_adapter.py` (534 行) | OpenAI 兼容适配器 |
| L2 | `adapters/mock_adapter.py` (258 行) | 无 LLM 脚本适配器 |
| L2 | `adapters/registry.py` (44 行) | Adapter 注册表 |
| Tool | `tools/base.py` (54 行) | 工具类型定义 |
| Tool | `tools/registry.py` (91 行) | 工具注册表 |
| Tool | `tools/write_artifact.py` (165 行) | 产物写入工具 |
| L1 | `db/models.py` (526 行) | 9 张表 ORM 模型 |
| L1 | `db/engine.py` (93 行) | 异步引擎 + SQLite PRAGMA |

---

## 2. L1 持久化层：数据库模型与引擎

### 2.1 引擎配置 — `db/engine.py`

```python
# 关键：SQLite 异步引擎 + PRAGMA 初始化
_engine = create_async_engine(
    f"sqlite+aiosqlite:///{_DB_PATH}",
    connect_args={
        "check_same_thread": False,
        # 三条 PRAGMA 缺一不可：
        "init": _sqlite_pragma_init,  # foreign_keys=ON, journal_mode=WAL, busy_timeout=5000
    },
)

# PRAGMA 初始化函数（每次新连接时执行）
async def _sqlite_pragma_init(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")   # 启用外键级联删除
    cursor.execute("PRAGMA journal_mode=WAL")   # WAL 模式：并发读写
    cursor.execute("PRAGMA busy_timeout=5000")  # 5 秒等待锁释放
    cursor.close()
```

**设计要点**：
- `foreign_keys=ON` — 删除 Conversation 时，Message / Artifact / Workspace 等级联删除
- `WAL` 模式 — 允许同时读写，不互相阻塞
- `busy_timeout=5000` — SQLite 锁等待，避免并发写冲突

**Session 工厂**：
```python
# get_db() 是 async context manager，每个调用一个独立事务
@asynccontextmanager
async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSession(_engine) as session:
        async with session.begin():
            yield session
```

### 2.2 数据库模型 — `db/models.py`

**9 张核心表**：

| 模型 | 表名 | 核心字段 | 关键外键 |
|------|------|---------|---------|
| `Agent` | agents | name, adapter_name, system_prompt, tool_names (JSON) | 无 |
| `Conversation` | conversations | title, mode, agent_ids (JSON), pinned_message_ids (JSON) | 无 |
| `Message` | messages | role, parts (JSON), status, agent_id | conversation_id → Conversation |
| `Artifact` | artifacts | type, title, content (JSON), version, parent_artifact_id | conversation_id → Conversation |
| `Workspace` | workspaces | root_path, mode, bound_path | conversation_id → Conversation |
| `Attachment` | attachments | file_name, mime_type, kind, size | conversation_id → Conversation |
| `AgentRun` | agent_runs | status, trigger_message_id, parent_run_id, error | conversation_id + agent_id |
| `ContextSummary` | context_summaries | summary, covered_until_created_at | conversation_id → Conversation |
| `AppSettings` | app_settings | anthropic_api_key, openai_api_key 等 | 无 |

**JSON 列处理模式**（本项目核心模式）：

```python
class Message(Base):
    # SQLite 存储为 TEXT(JSON)，Python 侧用 property 封装 list/dict
    _parts = Column("parts", Text, default="[]")

    @property
    def parts_list(self) -> list[dict]:
        return json.loads(self._parts) if self._parts else []

    @parts_list.setter
    def parts_list(self, value: list[dict]) -> None:
        self._parts = json.dumps(value, ensure_ascii=False)
```

**为什么不用 SQLAlchemy 的 JSON 类型？** 因为 SQLite 的 JSON 列在 aiosqlite 下有序列化/反序列化兼容问题，手动 `json.loads/dumps` 更可控，且 JSON 内容保持 **camelCase**（与前端字节兼容）。

### 2.3 表关系图

```
Conversation ──1:1── Workspace
    │
    ├──1:N── Message (conversation_id FK, CASCADE DELETE)
    │
    ├──1:N── Artifact (conversation_id FK, CASCADE DELETE)
    │              └── self-ref: parent_artifact_id → Artifact.id
    │
    ├──1:N── Attachment (conversation_id FK, CASCADE DELETE)
    │
    ├──1:N── AgentRun (conversation_id FK, CASCADE DELETE)
    │              └── self-ref: parent_run_id → AgentRun.id
    │
    └──1:N── ContextSummary (conversation_id FK, CASCADE DELETE)
```

---

## 3. L2 适配器层：屏蔽平台差异

### 3.1 抽象契约 — `adapters/base.py`

```python
# Adapter 的核心契约：给输入，还事件流
class AgentPlatformAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> AdapterName: ...

    @abstractmethod
    def stream(
        self, input: AdapterInput, cancel_event: asyncio.Event
    ) -> AsyncIterator[StreamEvent]: ...
```

**AdapterInput** 包含一次运行所需的全部上下文：

| 字段 | 说明 |
|------|------|
| `prompt` | 用户消息文本（群聊场景已包装为 XML） |
| `system_prompt` | 系统提示词（含 workspace_info） |
| `workspace_path` | 工作目录绝对路径 |
| `api_key` / `api_base_url` | 每个 Agent 独立的 API 凭证 |
| `tool_names` | 本次运行可用的工具列表 |
| `attachments` | 附件列表（图片/文件） |
| `history` | 跨 run 历史上下文（仅 CustomAdapter 使用） |
| `custom_config` | 自定义模型配置（仅 CustomAdapter 使用） |

### 3.2 四种 Adapter 对比

| Adapter | name | LLM 后端 | 工具执行 | 适用场景 |
|---------|------|---------|---------|---------|
| `MockAdapter` | `"mock"` | 无（脚本） | 无 | 开发/测试/Demo |
| `CustomAdapter` | `"custom"` | OpenAI SDK | 自身 tool loop | 自建模型 |
| `ClaudeAdapter` | `"claude-code"` | Claude SDK | SDK 内部 | Anthropic |
| `CodexAdapter` | `"codex"` | Codex SDK | SDK 内部 | OpenAI Codex |

### 3.3 MockAdapter — 最简单的实现

```python
# 根据 prompt 关键词选择预设脚本
def _pick_script(prompt: str) -> list[_ScriptStep]:
    if any(kw in p for kw in ("你好", "hello", "hi")):
        return _GREETING_SCRIPT
    if any(kw in p for kw in ("写代码", "code")):
        return _CODE_SCRIPT
    return _DEFAULT_SCRIPT

# stream() 逐步 yield StreamEvent
async def stream(self, input, cancel_event):
    yield MessageStartEvent(...)
    for step in script:
        if cancel_event.is_set():  # 随时检查取消
            break
        yield PartStartEvent(...)
        for chunk in _chunk_text(step.content, 4):
            await asyncio.sleep(0.005)  # 模拟流式延迟
            yield PartDeltaEvent(...)
        yield PartEndEvent(...)
    yield MessageEndEvent(...)
```

**学到的模式**：即使没有真实 LLM，MockAdapter 也产出完整的 StreamEvent 序列，用于端到端测试 SSE → Store → UI 渲染链路。

### 3.4 CustomAdapter — 自带工具循环

这是最复杂的 Adapter，核心是一个 **turn 循环**：

```python
while turn < MAX_TURNS:  # 最多 8 轮
    # 1. 调 LLM 流式 API
    stream = await client.chat.completions.create(
        model=model_id, messages=messages, tools=api_tools, stream=True
    )
    # 2. 消费流式 chunk → yield StreamEvent
    async for chunk in stream:
        # 处理 text / thinking / tool_calls 三种 delta
        yield PartDeltaEvent(...)

    # 3. 如果模型没有调用工具 → 结束
    if len(tool_calls) == 0 or finish_reason == "stop":
        yield MessageEndEvent(...)
        return

    # 4. 执行工具 → yield ToolCallEvent + ToolResultEvent
    for tc in tool_calls:
        result = await tool_registry.execute(tc.name, args, ctx)
        yield ToolResultEvent(...)
        messages.append({"role": "tool", "content": json.dumps(value)})
    # 5. 继续下一轮（带工具结果的 messages）
```

**关键设计**：CustomAdapter 自己管理工具循环（LLM → tool → LLM），而 SDK Adapter（Claude/Codex）的工具循环在 SDK 内部。

### 3.5 AgentRegistry — 适配器路由

```python
class AgentRegistry:
    def get_adapter(self, agent: Agent) -> AgentPlatformAdapter:
        adapter = self._adapters.get(agent.adapter_name)
        if adapter is None:
            raise ValueError(f'No adapter for "{agent.adapter_name}"')
        return adapter

# 模块加载时一次性注册所有 Adapter
agent_registry = _build_registry()  # Mock + Custom + Claude
```

---

## 4. L3 服务层（上）：EventBus + ConversationService

### 4.1 EventBus — 进程内事件扇出

```python
class EventBus:
    def __init__(self):
        self._subscribers: set[asyncio.Queue[StreamEvent]] = set()

    def publish(self, event: StreamEvent) -> None:
        """同步方法！put_nowait 不阻塞"""
        for queue in list(self._subscribers):
            _offer(queue, event)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[StreamEvent]]:
        queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

# 模块级单例
event_bus = EventBus()
```

**Overflow 策略**：如果某个订阅者的队列满了（1000 条），丢弃最旧的事件。因为 SSE 客户端断线重连后会通过 REST API 全量拉取，所以丢几条流事件不会造成数据不一致。

```python
def _offer(queue, event):
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        queue.get_nowait()      # 丢最旧的
        queue.put_nowait(event)  # 再放新的
```

### 4.2 SSE 接口 — `api/stream.py`

```python
async def _event_stream() -> AsyncIterator[dict]:
    async with event_bus.subscribe() as queue:
        yield {"data": json.dumps({"type": "connected"})}  # 立即告诉客户端连接成功
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
            except TimeoutError:
                yield {"data": json.dumps({"type": "heartbeat"})}  # 15 秒心跳保活
                continue
            yield {"data": event.model_dump_json(by_alias=True)}  # camelCase 序列化
```

### 4.3 ConversationService — 会话生命周期

这是后端最大的服务模块（1015 行），涵盖：

| 操作 | 函数 | 要点 |
|------|------|------|
| 创建 | `create_conversation()` | 验证 Agent、创建 Workspace、sandbox/local 模式 |
| 列表 | `list_conversations()` | 置顶优先，按 updatedAt 降序 |
| 删除 | `delete_conversation()` | FK CASCADE + 删目录 + 清 session |
| 发消息 | `send_message()` | 决定响应者 → spawn AgentRunner |
| 撤回 | `withdraw_latest_user_message()` | abort run → 等 500ms → 时间窗口删除 |
| 重新生成 | `regenerate_latest_response()` | 删旧回复 → 重新 spawn |
| 编辑重发 | `edit_and_resend_latest_user_message()` | 撤回 + 重发 |
| 清空历史 | `clear_conversation_history()` | 删 messages/runs/summaries |

**`send_message()` 核心流程**：

```python
async def send_message(*, conversation_id, content, mentioned_agent_ids, ...):
    # 1. 构建 user Message 的 parts
    parts = [{"type": "text", "content": content}]
    # 附加附件 parts（image_attachment / file_attachment）

    # 2. 写入数据库
    async with get_db() as db:
        msg = Message(id=message_id, role="user", parts_list=parts, ...)
        db.add(msg)

    # 3. 通过 EventBus 广播新消息（其他 SSE 客户端实时收到）
    event_bus.publish(MessageAddedEvent(...))

    # 4. 检查是否是部署命令（如 "deploy art_123"）
    deploy_intent = deploy_command_service.parse_deploy_command(content)
    if deploy_intent:
        return handle_deploy_command(...)

    # 5. 决定谁响应
    responders = _decide_responders(conv_mode, conv_agent_ids, mentions, agent_infos)

    # 6. 为每个响应者 spawn 一个 AgentRunner
    runner = get_agent_runner()
    for agent_id in responders:
        handle = runner.run(agent_id=agent_id, conversation_id=conversation_id, ...)
        run_ids.append(handle.run_id)

    return SendMessageResult(message_id=message_id, run_ids=run_ids)
```

**`_decide_responders()` 逻辑**：

```python
def _decide_responders(mode, agent_ids, mentions, agent_infos):
    if mode == "single":
        return agent_ids                    # 单聊：唯一 Agent 响应
    if mentions:
        return [m for m in mentions if m in agent_ids]  # 群聊 + @：被 @ 的响应
    orchestrator = next((a for a, is_orch in agent_infos if is_orch), None)
    return [orchestrator] if orchestrator else []  # 群聊无 @：Orchestrator 接管
```

---

## 5. L3 服务层（中）：AgentRunner 执行引擎

### 5.1 整体结构

AgentRunner 是后端的核心引擎（1366 行），负责：
1. 加载 Agent + Workspace + Trigger Message
2. 构建 AdapterInput（系统提示词 + 历史上下文 + 工具列表）
3. 调用 adapter.stream() 获取事件流
4. 消费事件流：持久化到 DB + 发布到 EventBus
5. 处理 finalize（成功/失败/中止）

### 5.2 入口：execute_run()

```python
async def execute_run(run_id, cancel_event, args):
    # 1. 加载前置数据
    agent = await load_agent(args.agent_id)
    workspace = await load_workspace(args.conversation_id)
    trigger_message = await load_trigger_message(args.trigger_message_id)

    # 2. 提取 prompt + 解析附件
    prompt = args.override_prompt or _extract_text_from_parts(trigger_parts)
    attachments = parse_attachments(trigger_parts)

    # 3. 写入 AgentRun 行 + 发布 RunStartEvent
    await insert_run(run_id, args, agent_id)
    publish(RunStartEvent(...))

    # 4. 分支：Orchestrator vs Simple
    try:
        if is_orchestrator:
            result = await execute_orchestrator_run(...)  # lazy import 避免循环
        else:
            result = await execute_simple_run(...)
        return await finalize_ok(run_id, args, result)
    except asyncio.CancelledError:
        return await finalize(run_id, args, "aborted", ...)
    except Exception as err:
        return await finalize(run_id, args, "failed", ..., str(err))
```

### 5.3 Simple 执行路径

```python
async def execute_simple_run(run_id, cancel_event, args, prompt, attachments):
    agent = await load_agent(...)
    workspace = await load_workspace(...)

    # 解析工具列表（如果是子任务，强制加入 report_task_result）
    tool_names = args.override_tool_names or agent.tool_names_list
    if args.require_task_report:
        tool_names = _ensure_includes(tool_names, "report_task_result")

    # 获取 Adapter + 构建 AdapterInput
    adapter = agent_registry.get_adapter(agent)
    adapter_input = await build_adapter_input(args, agent, run_id, prompt, workspace, tool_names, ...)

    # 核心：消费事件流
    stream = adapter.stream(adapter_input, cancel_event)
    result = await consume_stream(stream, agent_id, run_id)

    # 如果有文件写入证据，自动创建 project artifact
    if not args.parent_run_id:
        await maybe_create_project_artifact(evidence_run_id=run_id, ...)

    return result
```

### 5.4 consume_stream() — 事件消费核心

```python
async def consume_stream(stream, agent_id, run_id, on_tool_call=None):
    parts_buffer = {}       # message_id → list[dict] 内存中的 parts
    artifact_ids = []
    output_message_ids = []

    async for event in stream:
        # 1. 持久化事件到数据库
        await persist_event(event, parts_buffer, run_id, agent_id, ...)
        # 2. 发布到 EventBus（SSE 客户端实时收到）
        publish(event)

        # 3. 特殊事件处理
        if event.type == "artifact.create":
            # 自动追加 artifact_ref part 到当前消息
            ref_part = {"type": "artifact_ref", "artifactId": event.artifact.id}
            parts.append(ref_part)
            publish(PartStartEvent(...))

        if event.type == "tool.call" and on_tool_call:
            control = on_tool_call(event)
            if control and control.get("stop"):
                # Orchestrator 用这个拦截 plan_tasks 工具调用
                yield ToolResultEvent(...)
                break

    return RunExecutionResult(artifact_ids=..., output_message_ids=...)
```

### 5.5 persist_event() — 事件持久化

每个 StreamEvent 类型对应不同的数据库操作：

| 事件类型 | 数据库操作 |
|----------|-----------|
| `message.start` | 插入新 Message 行（status="streaming"） |
| `part.start` | 更新 Message.parts（追加新 part） |
| `part.delta` | 更新 Message.parts（追加文本到对应 part） |
| `tool.call` | 追加 tool_use part |
| `tool.result` | 追加 tool_result part |
| `message.end` | 更新 Message.status = "complete" |
| `run.usage` | 更新 AgentRun.usage |
| `artifact.create` | 追加 artifact_id 到列表 |

### 5.6 build_adapter_input() — 构建完整输入

```python
async def build_adapter_input(args, agent, run_id, prompt, workspace, tool_names, ...):
    # 1. 系统提示词 = workspace_info + agent.system_prompt + 工具使用指导
    system_prompt = _build_workspace_context_block(workspace) + "\n\n" + agent.system_prompt
    tool_guidance = _build_agent_hub_tool_guidance(agent, tool_names, workspace)
    system_prompt += "\n\n" + tool_guidance

    # 2. API Key 解析优先级：agent.api_key > app_settings > 环境变量
    effective_api_key = agent.api_key or _pick_settings_key(settings, agent)

    # 3. 跨 run 历史上下文（仅 CustomAdapter 使用）
    history = []
    if agent.adapter_name == "custom":
        history = await build_history_for(agent.id, conversation_id, ...)

    # 4. SDK Adapter 的上下文压缩
    if agent.adapter_name in ("claude-code", "codex"):
        effective_prompt = await prefix_prompt_with_context_summary(conversation_id, prompt)

    return AdapterInput(prompt=effective_prompt, system_prompt=system_prompt, ...)
```

### 5.7 finalize() — 运行收尾

```python
async def finalize(run_id, args, status, result, error=None):
    # 1. 如果是失败/中止 → 合成未完成的 tool_result 错误
    if status in ("failed", "aborted"):
        await _persist_unresolved_tool_failures(run_id, ...)

    # 2. 更新 AgentRun 状态
    async with get_db() as db:
        run.status = status
        run.finished_at = now_ms()
        # 所有还在 "streaming" 的消息 → 设为终态
        for msg in streaming_messages:
            msg.status = "complete" | "aborted" | "error"

    # 3. 失败/中止 → 发送错误可视化（追加文本或新建错误消息）
    if status in ("failed", "aborted"):
        await _emit_error_visualisation(run_id, args, status, error, ...)

    # 4. 更新 Conversation.updated_at
    # 5. 发布 RunEndEvent
    publish(RunEndEvent(status=status, error=error, ...))
```

---

## 6. L3 服务层（下）：Orchestrator 多 Agent 编排

### 6.1 三阶段流程

```
用户消息 → Orchestrator Agent
           │
           ├── Stage 1: PLAN
           │   ├── 构建 plan prompt（含可用 Agent 列表）
           │   ├── 限定工具：plan_tasks + ask_user + fs_list/fs_read/read_artifact
           │   ├── 拦截 plan_tasks 工具调用 → 解析计划
           │   └── 计划审核门：approve / reject / revise
           │
           ├── Stage 2: EXECUTE (DAG)
           │   ├── 拓扑排序 → 分 wave 执行
           │   ├── 同一 wave 内的任务并行（asyncio.gather）
           │   ├── 检测同 wave 文件写冲突
           │   ├── 每个子任务最多重试 MAX_CHILD_TASK_ATTEMPTS 次
           │   └── 验证 requiredCommands（build/test）
           │
           └── Stage 3: AGGREGATE
               ├── 汇总所有子任务结果
               ├── 重新调 LLM 生成总结
               └── 不再带 plan_tasks / ask_user 工具
```

### 6.2 主循环：PLAN → EXECUTE + replan

```python
async def execute_orchestrator_run(run_id, cancel_event, args, user_prompt, attachments):
    for round_no in range(1, MAX_DISPATCH_ROUNDS + 1):  # 最多 4 轮
        # Stage 1: PLAN
        plan, plan_run = await _run_plan_stage(args, agent, ...)

        if not plan:
            if round_no == 1:
                return result  # Orchestrator 直接回答了用户，不需要计划
            break

        # REVIEW 门：用户审核计划
        outcome = await _wait_for_dispatch_plan_review(plan=plan, ...)
        if outcome.kind == "approve":
            approved_plan = outcome.plan
        elif outcome.kind == "reject":
            continue  # 跳过本轮
        else:  # revise
            # 把用户反馈注入 → 重新规划 → 再次审核
            revised_plan = await _run_plan_stage(..., build_revise_context(plan, feedback))

        # Stage 2: EXECUTE (DAG)
        results, conflicts = await _execute_dag(approved_plan, ctx)

        # 判断是否需要 replan
        if not should_replan(round_views, conflicts):
            break

    # Stage 3: AGGREGATE
    aggregate_prompt = await build_aggregate_prompt(user_prompt, plan_items, results, ...)
    agg_stream = adapter.stream(aggregate_input, cancel_event)
    agg_run = await consume_stream(agg_stream, agent_id, run_id)

    return RunExecutionResult(artifact_ids=..., output_message_ids=...)
```

### 6.3 DAG 执行引擎

```python
async def _execute_dag(plan, ctx):
    remaining = {t.id for t in plan}
    results = {}

    while remaining:
        # 跳过依赖失败/中止的任务
        # 找到所有依赖已完成的就绪任务
        ready = [t for t in plan if all(results[d].status == "complete" for d in t.depends_on)]

        # 并行执行同一 wave 的所有任务
        wave = await asyncio.gather(*(_run_child_task(t, results, plan, ctx) for t in ready))

        # 检测同 wave 文件冲突（两个任务写了同一文件）
        conflicts.extend(detect_wave_conflicts(run_writes))

    return results, conflicts
```

### 6.4 子任务执行 + 重试

```python
async def _run_child_task(task, upstream, plan, ctx):
    # 获取信号量（最多 4 个并行子任务）
    release = await sub_agent_run_semaphore.acquire(ctx.cancel_event)
    try:
        for attempt in range(1, MAX_CHILD_TASK_ATTEMPTS + 1):  # 最多 4 次尝试
            # 构建子 Agent prompt（含上游结果 + 任务描述）
            prompt = await build_sub_agent_prompt(task, upstream, ...)

            # 通过 run_with_args() spawn 子 run
            child_run_id, child_task, _ = run_with_args(RunArgs(
                agent_id=task.agent_id,
                override_prompt=prompt,
                require_task_report=True,
                parent_cancel_event=ctx.cancel_event,
            ))

            # 等待子 run 完成
            run_result = await child_task

            # 评估结果：report_task_result + requiredCommands 验证
            evaluation = _evaluate_child_task_result(task, raw_result, evidence)
            if evaluation.status == "complete":
                return evaluation  # 成功！

            # 失败 → 构建 continuation context → 重试
            continuation_context = _build_task_continuation_context(task, evaluation, attempt, ...)
    finally:
        release()  # 释放信号量
```

---

## 7. 工具系统：ToolDef + ToolRegistry

### 7.1 工具类型定义 — `tools/base.py`

```python
@dataclass
class ToolContext:
    conversation_id: str
    workspace_path: str
    agent_id: str
    run_id: str
    cancel_event: asyncio.Event

@dataclass
class ToolResult:
    ok: bool
    value: Any = None
    error: str | None = None

ToolHandler = Callable[[Any, ToolContext], Awaitable[ToolResult]]

@dataclass
class ToolDef:
    name: str           # 工具名（如 "write_artifact"）
    description: str    # 给 LLM 看的描述
    parameters: dict    # JSON Schema
    handler: ToolHandler
```

### 7.2 12 个注册工具

| 工具名 | 文件 | 用途 |
|--------|------|------|
| `write_artifact` | write_artifact.py | 创建/版本化产物 |
| `read_artifact` | read_artifact.py | 读取产物内容 |
| `deploy_artifact` | deploy_artifact.py | 部署 web_app 产物为预览 |
| `deploy_workspace` | deploy_workspace.py | 部署 workspace 静态目录 |
| `read_attachment` | read_attachment.py | 读取用户上传附件 |
| `plan_tasks` | plan_tasks.py | Orchestrator 创建计划 |
| `report_task_result` | report_task_result.py | 子任务汇报结果 |
| `fs_list` | fs_list.py | 列出 workspace 目录 |
| `fs_read` | fs_read.py | 读取 workspace 文件 |
| `fs_write` | fs_write.py | 写入 workspace 文件 |
| `bash` | bash.py | 执行 shell 命令 |
| `ask_user` | ask_user.py | 结构化问答（阻塞等待用户选择） |

### 7.3 ToolRegistry — 注册表

```python
class ToolRegistry:
    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def resolve(self, names: list[str]) -> list[ToolDef]:
        """将名称列表解析为 ToolDef 列表（给 AdapterInput 用）"""
        return [self._tools[n] for n in names]

    async def execute(self, tool_name: str, args: Any, ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(tool_name)
        if not tool:
            return err(f"Unknown tool: {tool_name}")
        return await tool.handler(args, ctx)

# 模块加载时一次性注册
tool_registry = _build_registry()  # 注册全部 12 个工具
```

### 7.4 工具实现示例：write_artifact

```python
async def _handler(args: Any, ctx: ToolContext) -> ToolResult:
    parsed = _Args.model_validate(args)  # Pydantic 验证参数

    # 构建完整 content
    full_content = build_artifact_content(parsed.type, parsed.content)

    async with get_db() as db:
        # 如果有 parentArtifactId，版本自增
        version = 1
        if parsed.parent_artifact_id:
            parent = await db.get(Artifact, parsed.parent_artifact_id)
            version = parent.version + 1

        artifact = Artifact(
            id=new_artifact_id(),
            conversation_id=ctx.conversation_id,
            type=parsed.type,
            title=parsed.title,
            version=version,
            created_by_agent_id=ctx.agent_id,
        )
        artifact.content_dict = full_content
        db.add(artifact)

    return ok({"artifactId": artifact_id, "version": version})
```

---

## 8. API 路由层：HTTP 接口

### 8.1 路由注册

```python
# main.py — lifespan 管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：初始化数据库
    await init_db()
    yield
    # 关闭时：清理资源

app = FastAPI(lifespan=lifespan)

# 路由注册
from app.api import agents, artifacts, attachments, conversations, ...
app.include_router(conversations.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
# ... 其余路由
```

### 8.2 完整 API 端点

| 方法 | 路径 | 处理文件 | 说明 |
|------|------|---------|------|
| GET | `/api/stream` | stream.py | SSE 全局事件流 |
| GET | `/api/conversations` | conversations.py | 列表 |
| POST | `/api/conversations` | conversations.py | 创建 |
| DELETE | `/api/conversations/{id}` | conversations.py | 删除 |
| POST | `/api/conversations/{id}/messages` | conversations.py | 发消息 |
| DELETE | `/api/conversations/{id}/messages/{mid}` | conversations.py | 撤回消息 |
| POST | `/api/conversations/{id}/regenerate` | conversations.py | 重新生成 |
| GET | `/api/agents` | agents.py | 列表 |
| POST | `/api/agents` | agents.py | 创建 |
| PATCH | `/api/agents/{id}` | agents.py | 更新 |
| DELETE | `/api/agents/{id}` | agents.py | 删除 |
| GET | `/api/artifacts/{id}` | artifacts.py | 获取产物 |
| POST | `/api/attachments` | attachments.py | 上传附件 |
| POST | `/api/pending/{id}/approve` | pending.py | 批准计划 |

### 8.3 路由层代码模式

```python
# 薄路由层：只做参数解析 + 调 service + 序列化响应
@router.post("/conversations")
async def create_conversation(req: Request) -> JSONResponse:
    raw = await _read_json(req)
    try:
        body = CreateConversationRequest.model_validate(raw)  # Pydantic 验证
    except ValidationError as exc:
        return _invalid_body(exc)  # 400

    try:
        conversation = await conversation_service.create_conversation(
            mode=body.mode, agent_ids=body.agent_ids, ...
        )
    except ValueError as err:
        return _err(str(err), 400)

    return JSONResponse(status_code=201, content={"conversation": _model(conversation)})
```

**设计原则**：路由层不含业务逻辑，只做 验证 → 调用 → 序列化。

---

## 9. 消息完整生命周期追踪

以「用户在单聊中发送一条文本消息」为例，追踪从发送到渲染的完整路径：

```
1. POST /api/conversations/conv_123/messages
   body: { "content": "帮我写一个计数器组件" }
   │
   ├─ conversations.py → conversation_service.send_message()
   │   ├─ 写入 Message 行 (role="user", status="complete")
   │   ├─ event_bus.publish(MessageAddedEvent)      ← SSE 广播
   │   ├─ agent_runner.run(agent_id, conv_id, msg_id)
   │   │   ├─ spawn asyncio.Task → execute_run()
   │   │   └─ 返回 RunHandle(run_id) 立即
   │   └─ 返回 { messageId, runIds } 给客户端
   │
2. execute_run() [在后台 Task 中]
   │
   ├─ 加载 Agent + Workspace + TriggerMessage
   ├─ insert_run(run_id, status="running")
   ├─ publish(RunStartEvent)                        ← SSE 广播
   │
3. execute_simple_run()
   │
   ├─ build_adapter_input()
   │   ├─ system_prompt = workspace_info + agent.system_prompt + tool_guidance
   │   └─ history = build_history_for() (如果是 CustomAdapter)
   │
   ├─ adapter.stream(input, cancel_event)
   │   ├─ yield MessageStartEvent                   ← SSE 广播
   │   ├─ yield PartStartEvent(type="thinking")     ← SSE 广播
   │   ├─ yield PartDeltaEvent("thinking.append")   ← SSE 广播 × N
   │   ├─ yield PartEndEvent                        ← SSE 广播
   │   ├─ yield PartStartEvent(type="text")          ← SSE 广播
   │   ├─ yield PartDeltaEvent("text.append")       ← SSE 广播 × N
   │   ├─ yield PartEndEvent                        ← SSE 广播
   │   └─ yield MessageEndEvent                     ← SSE 广播
   │
   ├─ consume_stream() 处理每个事件：
   │   ├─ persist_event() → 写入/更新 Message 行
   │   └─ publish() → event_bus → SSE → 前端
   │
4. finalize_ok()
   │
   ├─ AgentRun.status = "complete"
   ├─ Message.status = "complete"
   ├─ Conversation.updated_at = now
   └─ publish(RunEndEvent(status="complete"))       ← SSE 广播

5. 前端 SSE 收到事件
   │
   └─ StreamProvider → applyEvent → Zustand Store → React 重新渲染
```

---

## 10. 关键设计模式总结

### 10.1 Runner Registry — 延迟绑定

```python
# runner_registry.py — 解决循环依赖
class _NoopAgentRunner:
    """真实 Runner 注册前的占位"""
    def run(self, ...) -> RunHandle:
        return RunHandle(run_id=new_run_id())  # 返回空 run_id

_runner = _NoopAgentRunner()

def set_agent_runner(runner):
    global _runner
    _runner = runner  # agent_runner.py 末尾调用：set_agent_runner(AgentRunnerImpl())
```

**为什么？** conversation_service 需要调 AgentRunner，但 AgentRunner 又依赖 conversation_service 的数据。通过 Protocol + Registry 解耦，agent_runner.py 在模块加载末尾自注册。

### 10.2 cancel_event — 取消信号传播

```python
# TS 的 AbortSignal → Python 的 asyncio.Event
cancel_event = asyncio.Event()

# 级联取消：父 run abort → 子 run abort
parent_cancel = _active_runs.get(parent_run_id)
if parent_cancel:
    watcher = asyncio.ensure_future(_wait_event(parent_cancel))
    watcher.add_done_callback(lambda _: cancel_event.set())

# Adapter 内部随时检查
if cancel_event.is_set():
    break  # 停止流式输出
```

### 10.3 Semaphore — 公平并发控制

```python
class _Semaphore:
    """FIFO 队列，abort-aware"""
    async def acquire(self, cancel_event) -> Callable[[], None]:
        if self._active < self._limit:
            self._active += 1
            return self._create_release()
        # 排队等待，如果 cancel_event 触发则跳过
        fut = loop.create_future()
        self._queue.append((fut, cancel_event))
        return await fut
```

Orchestrator 最多 4 个子任务并行，通过信号量控制。

### 10.4 事件流 = 系统的腰部协议

```
Adapter ──yield──→ StreamEvent ──→ consume_stream()
                                      ├── persist_event() → DB
                                      └── publish() → EventBus → SSE → 前端
```

所有事件都经过同一条管道：**Adapter 产出 → 持久化 → 广播**。这保证了数据库和前端状态的一致性。

### 10.5 时间窗口删除

```python
# withdraw/regenerate 用时间窗口而不是 FK 关系来清理
async def _delete_from_timewindow(conversation_id, boundary, *, inclusive):
    # inclusive: created_at >= boundary (撤回：连用户消息一起删)
    # exclusive: created_at > boundary (重新生成：保留用户消息)
    msgs = select(Message).where(Message.created_at >= boundary)
    # 同时删关联的 artifacts（通过扫描 artifact_ref parts）
    # 同时删关联的 agent_runs
```

---

## 11. 自检清单

完成本阶段学习后，检验自己能否回答以下问题：

### 架构层
- [ ] 后端分为哪几层？每层的职责边界是什么？
- [ ] 为什么用 EventBus 而不是直接调 SSE handler？
- [ ] runner_registry 为什么要用延迟绑定？

### 持久化层
- [ ] SQLite 三条 PRAGMA 分别解决什么问题？
- [ ] Message.parts 为什么存 JSON 文本而不是 SQLAlchemy JSON 类型？
- [ ] 删除 Conversation 时，哪些表会被级联删除？

### 适配器层
- [ ] AdapterInput 里哪些字段是 CustomAdapter 独有的？
- [ ] CustomAdapter 的 tool loop 和 SDK Adapter 有什么区别？
- [ ] MockAdapter 的 stream() 产出的事件序列完整吗？

### 服务层
- [ ] send_message() 是如何决定哪些 Agent 需要响应的？
- [ ] consume_stream() 对每个事件做了什么操作？
- [ ] finalize() 在失败/中止时做了哪些额外工作？

### Orchestrator
- [ ] 三阶段分别做了什么？
- [ ] DAG 执行中，同一 wave 的任务如何并行？
- [ ] 子任务失败时如何重试？最多重试几次？

### 工具系统
- [ ] ToolDef 的四个字段分别是什么？
- [ ] write_artifact 工具如何创建新版本？
- [ ] 工具注册在什么时候发生？

### API 层
- [ ] 路由层为什么不含业务逻辑？
- [ ] SSE 连接的心跳机制怎么实现的？
- [ ] 一条用户消息从 POST 到前端渲染，经过了哪些函数调用？
