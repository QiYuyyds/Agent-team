# 阶段五：进阶专题 — 深入系统内部机制

> **学习目标**：掌握 AgentHub 后端的进阶系统——Artifact 产物引擎、Orchestrator 多 Agent 编排、
> 计划审核门控、任务完成证据链、辅助服务矩阵、安全沙箱模型。
> 所有代码示例均来自项目真实源码，配合设计决策分析。

---

## 目录

1. [Artifact 产物引擎](#1-artifact-产物引擎)
2. [Dispatch Plan 全生命周期](#2-dispatch-plan-全生命周期)
3. [Orchestrator 三阶段编排](#3-orchestrator-三阶段编排)
4. [计划审核门控 (Plan Review Gate)](#4-计划审核门控-plan-review-gate)
5. [DAG 执行引擎](#5-dag-执行引擎)
6. [Task Result Report — 完成证据链](#6-task-result-report--完成证据链)
7. [辅助服务矩阵](#7-辅助服务矩阵)
8. [安全与沙箱模型](#8-安全与沙箱模型)
9. [可扩展性设计](#9-可扩展性设计)
10. [自检清单](#10-自检清单)

---

## 1. Artifact 产物引擎

### 1.1 架构概览

Artifact 系统是 AgentHub 的"成果容器"——Agent 产出的所有内容（网页、文档、图表、代码文件、PPT、
差异对比、项目文件包）都通过 Artifact 存储和展示。

```
┌─────────────────────────────────────────────────────────┐
│                    Artifact 系统                         │
│                                                         │
│  build_artifact_content()   ← 松散输入 → 强类型 content  │
│  create_artifact_version()  ← 版本链创建                  │
│  list_artifact_versions()   ← 爬根 + BFS 遍历            │
│  serialize_artifact_export()← 导出序列化                  │
│                                                         │
│  7 种类型: web_app | document | diagram | image |        │
│            diff | code_file | ppt                        │
└─────────────────────────────────────────────────────────┘
```

核心文件：`backend/app/services/artifact_service.py`（892 行）

### 1.2 内容标准化 — build_artifact_content()

LLM 返回的产物内容是"松散的"——可能是 dict、string、甚至 JSON 字符串化的 dict。
`build_artifact_content()` 是单一入口，将任何松散输入规范化为强类型 content dict。

```python
# artifact_service.py
def build_artifact_content(artifact_type: str, raw_input: Any) -> dict[str, Any] | None:
    """Coerce loose content into a typed artifact content dict, or None."""
    raw = _unwrap_stringified_content(raw_input)  # 处理 LLM 把 JSON 当字符串传回

    if artifact_type == "web_app":
        return _build_web_app(raw)
    if artifact_type == "document":
        return _build_document(raw)
    if artifact_type == "diagram":
        return _build_diagram(raw)
    if artifact_type == "image":
        return _build_image(raw)
    if artifact_type == "diff":
        return _build_diff(raw)
    if artifact_type == "code_file":
        return _build_code_file(raw)
    if artifact_type == "ppt":
        return _build_ppt(raw)
    return None
```

**设计决策**：为什么需要 `_unwrap_stringified_content()`？
> LLM 有时候会把整个 JSON 对象当字符串传回（`"{\"type\":\"web_app\", ...}"`），
> 而不是作为 dict。这个函数尝试 JSON.parse，如果成功就解包，是处理 LLM 不可预测输出的防御层。

#### 各类型 Builder 详解

**web_app** — 最复杂的类型，支持 3 种输入格式：

```python
def _build_web_app(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        # 格式 1: { files: { "index.html": "...", "style.css": "..." } }
        files = obj.get("files")
        if isinstance(files, dict):
            normalised = {k: v for k, v in files.items() if isinstance(v, str)}
            entry = obj.get("entry")
            return {"type": "web_app", "files": normalised,
                    "entry": entry if isinstance(entry, str) else "index.html"}

        # 格式 2: { html: "...", css: "...", js: "..." }  ← LLM 友好格式
        if isinstance(obj.get("html"), str) or isinstance(obj.get("css"), str):
            out_files = {}
            if isinstance(obj.get("html"), str): out_files["index.html"] = obj["html"]
            if isinstance(obj.get("css"), str):  out_files["style.css"]  = obj["css"]
            if isinstance(obj.get("js"), str):   out_files["script.js"]  = obj["js"]
            return {"type": "web_app", "files": out_files, "entry": "index.html"}

        # 格式 3: { content: "..." } 或 { code: "..." }  ← 单文件降级
        if isinstance(obj.get("content"), str):
            return {"type": "web_app", "files": {"index.html": obj["content"]}, "entry": "index.html"}

    # 格式 4: 纯字符串 → 当作 index.html
    if isinstance(raw, str):
        return {"type": "web_app", "files": {"index.html": raw}, "entry": "index.html"}
```

**diagram** — Mermaid 图表，支持 source/mermaid/code/content 四种字段名别名：

```python
def _build_diagram(raw: Any) -> dict[str, Any] | None:
    syntax = _read_string(raw.get("syntax")) or "mermaid"
    if syntax.lower() != "mermaid":
        return None  # 只支持 mermaid
    source = (
        _read_string(raw.get("source"))
        or _read_string(raw.get("mermaid"))   # 别名 1
        or _read_string(raw.get("code"))       # 别名 2
        or _read_string(raw.get("content"))    # 别名 3
    )
    normalised = _normalise_diagram_source(source)  # Mermaid 语法标准化
    return {"type": "diagram", "syntax": "mermaid", "source": normalised}
```

**ppt** — 幻灯片，支持数组或 `{ slides: [...] }` 输入：

```python
def _build_ppt(raw: Any) -> dict[str, Any] | None:
    # 拒绝含无界二进制载荷的输入
    if _contains_unbounded_binary_payload(raw):
        return None
    # 支持 list 直接传入或 { slides: [...] }
    raw_slides = raw if isinstance(raw, list) else obj.get("slides")
    slides = []
    for item in raw_slides:
        # 每页：title + subtitle + bullets/points + blocks + notes + layout
        title = _read_string(item.get("title"))
        bullets = item.get("bullets")  # list 或 \n 分隔的 string
        blocks = normalize_blocks(item.get("blocks"))  # PPT DSL 块标准化
        layout = _normalise_ppt_layout(item.get("layout"))
```

### 1.3 版本链 — 自引用树结构

Artifact 通过 `parent_artifact_id` 字段形成版本链（单向链表 → 树）：

```
art_v1 (version=1, parent=null)
  └─ art_v2 (version=2, parent=art_v1)
       └─ art_v3 (version=3, parent=art_v2)
```

```python
# artifact_service.py
async def create_artifact_version(parent_id, content, title=None):
    parent = await db.get(Artifact, parent_id)
    artifact = Artifact(
        id=new_artifact_id(),
        version=parent.version + 1,         # 版本号递增
        parent_artifact_id=parent.id,       # 指向父版本
        type=parent.type,                   # 类型继承
        created_by_agent_id=parent.created_by_agent_id,  # Agent 继承
    )
```

**list_artifact_versions()** — 爬根 + BFS：

```python
async def list_artifact_versions(artifact_id):
    root = await db.get(Artifact, artifact_id)

    # 1) 向上爬到根
    climbed = {root.id}
    while root.parent_artifact_id and root.parent_artifact_id not in climbed:
        climbed.add(root.parent_artifact_id)
        parent = await db.get(Artifact, root.parent_artifact_id)
        root = parent

    # 2) BFS 向下遍历所有后代
    collected, visited, queue = [root], {root.id}, [root.id]
    while queue:
        parent_id = queue.pop(0)
        children = await db.execute(
            select(Artifact).where(Artifact.parent_artifact_id == parent_id))
        for child in children.scalars().all():
            if child.id not in visited:
                visited.add(child.id)
                collected.append(child)
                queue.append(child.id)

    collected.sort(key=lambda a: a.version)
```

> **为什么要先爬根再 BFS？** 因为用户可能点击版本链中间的某个版本请求"查看全部版本"，
> 如果只向下 BFS 会漏掉更早的版本。爬根保证找到链的起点。

### 1.4 导出序列化

`serialize_artifact_export()` 将 Artifact 转为可下载格式：

```python
class ArtifactExport:
    kind: Literal["file", "redirect", "error", "deferred"]
    filename: str | None
    body: bytes | None           # kind="file" 时的文件内容
    redirect_url: str | None     # kind="redirect" 时（image 类型）
    deferred_kind: Literal["ppt", "project"] | None  # 需要额外处理

# 各类型的导出策略：
# web_app  → ZIP（所有 files 打包 + README.txt）
# document → .md 文件
# diagram  → .mmd 文件（Mermaid 源码）
# image    → 302 redirect 到 url
# diff     → JSON fallback
# ppt      → deferred（需要 pptx 生成）
# project  → deferred（需要 workspace zip）
```

---

## 2. Dispatch Plan 全生命周期

### 2.1 概述

Dispatch Plan 是 Orchestrator 的核心数据——描述"把一个大任务拆成多个子任务，分配给不同 Agent"。
它的生命周期：**LLM 输出 → 解析 → 验证 → 编译（依赖推断 + 合约标准化） → 审核 → DAG 执行**。

核心文件：`backend/app/services/dispatch_plan.py`（835 行）

### 2.2 解析 — parse_dispatch_plan_tool_args()

LLM 通过 `plan_tasks` 工具调用输出计划，原始参数需要严格解析：

```python
def parse_dispatch_plan_tool_args(args: object) -> list[DispatchPlanItem]:
    if not _is_record(args) or not isinstance(args.get("tasks"), list):
        raise ValueError("Invalid dispatch plan: plan_tasks args must include a tasks array")

    result = []
    for index, raw in enumerate(args["tasks"]):
        item_id = _read_non_empty_string(raw.get("id"), ...)
        agent_id = _read_non_empty_string(raw.get("agentId"), ...)
        task = _read_non_empty_string(raw.get("task"), ...)
        task_kind = _read_optional_task_kind(raw.get("taskKind"), ...)
        depends_on = ...       # 可选依赖列表
        expected_outputs = ... # 预期产出
        inputs = ...           # 输入引用（fromTaskId + outputId）
        acceptance_criteria = ...  # 验收标准
        required_commands = ...    # 必须执行的验证命令
        required_evidence = ...    # 必须提供的证据
```

**MCP 工具命名兼容**：

```python
def extract_plan_tasks_tool_args(tool_name: str, args: object) -> object | None:
    """处理多种 MCP 命名前缀"""
    if tool_name == "plan_tasks": return args
    if tool_name == "mcp__agenthub__plan_tasks": return args
    if tool_name == "codex_mcp_agenthub_plan_tasks":
        return _read_codex_mcp_tool_arguments(args)  # Codex 会把参数 JSON 字符串化
    if tool_name.endswith("__plan_tasks") or tool_name.endswith("_plan_tasks"):
        return args
    return None
```

### 2.3 验证 — validate_dispatch_plan()

验证阶段检查计划的**结构完整性**：

```python
def validate_dispatch_plan(plan, available_agents, orchestrator_agent_id, ...):
    # 1. 计划不能为空
    # 2. task id 不能重复
    # 3. 每个 task 检查：
    #    - 不能分配给 orchestrator 自身（防递归）
    #    - agentId 必须在可用 agent 列表中
    #    - dependsOn 不能自引用
    #    - dependsOn 不能有重复依赖
    #    - dependsOn 引用的 task 必须存在
    #    - expectedOutputs 中 id 不能重复
    #    - inputs 不能引用自身
    #    - inputs 引用的上游 task 和 output 必须存在
    # 4. 环检测（DFS）
    assert_acyclic_dispatch_plan(plan)
```

**环检测 — DFS 三色标记法**：

```python
def assert_acyclic_dispatch_plan(plan):
    visiting = set()  # 灰色：正在访问
    visited = set()   # 黑色：已完成
    stack = []        # 当前路径

    def visit(task_id):
        if task_id in visited: return
        if task_id in visiting:
            # 找到环！输出完整路径
            cycle_start = stack.index(task_id)
            cycle = [*stack[cycle_start:], task_id]
            raise ValueError(f"circular dependency {' -> '.join(cycle)}")
        visiting.add(task_id)
        stack.append(task_id)
        for dep in task.depends_on or []:
            visit(dep)
        stack.pop()
        visiting.discard(task_id)
        visited.add(task_id)
```

### 2.4 编译 — compile_dispatch_plan()

编译阶段做两件重要的事：**文本启发式依赖推断** + **代码任务合约标准化**。

#### 依赖推断

当 LLM 没有显式声明 `dependsOn` 时，系统通过文本分析自动推断：

```python
def _infer_dependencies_for_task(task, previous_tasks):
    inferred = set()

    # 策略 1: 任务文本中有依赖信号词 + 引用了前序 task id
    if _has_dependency_signal(task_text):  # "读取"/"参考"/"依赖"/"产物"...
        for previous in previous_tasks:
            if _contains_task_id_reference(task_text, previous.id):
                inferred.add(previous.id)

    # 策略 2: 消费-生产主题匹配（PRD → UI 设计 → 前端）
    consumed_topics = _get_consumed_artifact_topics(task_text)  # "参考 PRD" → {prd}
    if consumed_topics:
        for previous in previous_tasks:
            produced_topics = _get_produced_artifact_topics(previous.task)  # "撰写 PRD" → {prd}
            if consumed_topics & produced_topics:
                inferred.add(previous.id)

    # 策略 3: 审查任务依赖所有产出 artifact 的前序任务
    if _is_review_task(task_text):
        for previous in previous_tasks:
            if task_expects_artifact(previous):
                inferred.add(previous.id)
```

**主题匹配正则示例**（中英文双语）：

```python
_CONSUMES_PRD_PATTERN = re.compile(
    r"(?:读取|基于|参考|根据|按照|了解|审查|检查|验收|read|review)"
    r".{0,40}"
    r"(?:PRD|产品需求|需求文档)|"
    r"(?:PRD|产品需求|需求文档)"
    r".{0,40}"
    r"(?:读取|基于|参考|根据|按照|了解|审查|检查|验收|符合|read|review)",
    re.IGNORECASE,
)
```

#### 代码任务合约标准化

对代码实现类任务，自动追加 `project` 输出 + 可运行验收标准：

```python
def normalize_task_contract(task):
    if not is_code_implementation_task(task):
        return task
    return task.model_copy(update={
        "expected_outputs": _ensure_code_project_output(task.expected_outputs),
        "acceptance_criteria": _append_unique(
            task.acceptance_criteria,
            "项目构建/编译验证通过（至少一条非准备验证命令 exitCode=0）"
        ),
        "required_evidence": _append_unique(
            task.required_evidence,
            "至少一条构建/编译/测试/类型检查命令 exitCode=0"
        ),
    })
```

**代码任务判定启发式**：

```python
_CODE_TASK_PATTERN = re.compile(
    r"(?:实现|开发|修复|改造|重构|搭建|脚手架|前端|后端|接口|组件|页面|代码|"
    r"implement|develop|build|scaffold|frontend|backend|api|component|code)",
    re.IGNORECASE,
)
# 同时排除审查/分析类任务
```

---

## 3. Orchestrator 三阶段编排

### 3.1 全局流程

```
用户消息
  │
  ▼
Stage 1: PLAN ───── LLM 输出 plan_tasks
  │                    │
  │              Plan Review Gate ← 用户审核/修改/拒绝
  │                    │
  ▼
Stage 2: EXECUTE ── DAG 执行（分 wave 并行，失败 → replan 循环）
  │
  ▼
Stage 3: AGGREGATE ─ 总结轮（合并所有子任务结果）
```

核心文件：`backend/app/services/orchestrator.py`（1370 行）

### 3.2 主循环 — execute_orchestrator_run()

```python
async def execute_orchestrator_run(run_id, cancel_event, args, user_prompt, attachments):
    all_artifact_ids = []
    merged_results = {}
    plan_items_by_id = {}
    last_conflicts = []

    # ─── Stage 1+2: PLAN → EXECUTE，最多 MAX_DISPATCH_ROUNDS 轮补救 ────
    for round_no in range(1, MAX_DISPATCH_ROUNDS + 1):
        if cancel_event.is_set():
            raise RuntimeError("Orchestrator run aborted")

        # 非第一轮时构建 replan 上下文
        replan_context = (
            None if round_no == 1
            else build_replan_context(
                _to_replan_views(plan_items_by_id, merged_results),
                _to_replan_conflicts(last_conflicts),
            )
        )

        # Stage 1: PLAN
        initial_plan, plan_run = await _run_plan_stage(...)

        # Plan Review Gate: approve / reject / revise
        plan = initial_plan
        reviewing = True
        while reviewing:
            outcome = await _wait_for_dispatch_plan_review(...)
            if outcome.kind == "approve":
                approved_plan = outcome.plan
                reviewing = False
            elif outcome.kind == "reject":
                reviewing = False
            else:  # revise: 用户反馈 → 重新 plan
                revised_plan, _ = await _run_plan_stage(..., build_revise_context(plan, outcome.feedback))
                plan = revised_plan

        # Stage 2: EXECUTE (DAG)
        results, conflicts = await _execute_dag(approved_plan, DagContext(...))

        # 检查是否需要 replan
        if not should_replan(round_views, conflicts):
            break

    # ─── Stage 3: AGGREGATE ───
    aggregate_tool_names = [n for n in agent.tool_names_list
                            if n != "plan_tasks" and n != ASK_USER_TOOL_NAME]
    agg_stream = adapter.stream(await build_adapter_input(..., aggregate_user_prompt, ...))
    agg_run = await consume_stream(agg_stream, agent.id, run_id)
```

### 3.3 PLAN 阶段 — 拦截 plan_tasks 工具调用

```python
async def _run_plan_stage(...):
    plan_ref = {"value": None}

    def on_tool_call(event):
        """拦截 plan_tasks 工具调用，解析但不实际执行"""
        plan_args = extract_plan_tasks_tool_args(event.tool_name, event.args)
        if plan_args is None:
            return None
        plan = parse_dispatch_plan_tool_args(plan_args)
        plan_ref["value"] = plan
        return {"stop": True, "result": {"acknowledged": True, "taskCount": len(plan)}}

    plan_stream = adapter.stream(await build_adapter_input(..., plan_tool_names, ...))
    plan_run = await consume_stream(plan_stream, agent.id, run_id, on_tool_call)

    # 解析 + 编译 + 验证
    plan = compile_and_validate_dispatch_plan(plan_ref["value"], ...) if plan_ref["value"] else None
    return plan, plan_run
```

> **设计亮点**：`plan_tasks` 不是真正执行的工具——它被 `on_tool_call` 拦截，
> 解析出计划后立即返回 `stop: True`，终止 LLM 的 turn 循环。
> LLM 以为自己在调用工具，实际上系统只是"偷听"了它的计划输出。

---

## 4. 计划审核门控 (Plan Review Gate)

### 4.1 异步阻塞等待

Orchestrator 生成计划后，会**阻塞等待**用户审核。这通过 `asyncio.Future` + 
`PendingDispatchPlansStore` 实现：

核心文件：`backend/app/services/pending_dispatch_plans.py`（177 行）

```python
# orchestrator.py
async def _wait_for_dispatch_plan_review(...):
    # 1. 注册计划到 pending store
    pending = pending_dispatch_plans.register(
        conversation_id=..., plan=plan, validator=validator,
    )

    # 2. 创建 Future，等待用户决策
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    # 3. 绑定 resolver（用户操作时触发）
    pending_dispatch_plans.attach_resolver(pending.id, lambda outcome: future.set_result(outcome))

    # 4. 级联取消：abort 时取消 parked plan
    abort_watcher = asyncio.ensure_future(cancel_event.wait())
    abort_watcher.add_done_callback(lambda _: pending_dispatch_plans.cancel(pending.id))

    return await future  # 阻塞直到 approve/reject/revise
```

### 4.2 PendingDispatchPlansStore

```python
class PendingDispatchPlansStore:
    def register(self, *, conversation_id, agent_id, run_id, plan, validator):
        """停放计划，发布 dispatch.plan.pending 事件"""
        pending_plan = PendingDispatchPlan(id=..., plan=plan, ...)
        self._map[pending_id] = _PendingEntry(pending_plan, validator, resolver=None)
        event_bus.publish(DispatchPlanPendingEvent(...))
        return pending_plan

    def approve(self, pending_id):
        """审批：先通过 validator 重新验证，再交给 resolver"""
        entry = self._map.get(pending_id)
        compiled_plan = entry.validator(entry.pending_plan.plan)  # 重新编译验证
        entry.resolver(PlanReviewOutcome(kind="approve", plan=compiled_plan))

    def revise(self, pending_id, feedback):
        """修改：把用户自然语言反馈交给 resolver"""
        entry.resolver(PlanReviewOutcome(kind="revise", feedback=feedback))

    def reject(self, pending_id):
        """拒绝"""
        entry.resolver(PlanReviewOutcome(kind="reject"))
```

> **为什么 approve 时重新验证？** 因为在用户审核期间，可用 Agent 列表可能已变化
> （Agent 被删除或修改），重新验证确保计划仍然合法。

---

## 5. DAG 执行引擎

### 5.1 拓扑排序 + 分 Wave 并行

```python
async def _execute_dag(plan, ctx):
    results = { ... }  # 包含前轮的 seed_results
    remaining = {t.id for t in plan}
    conflicts = []

    while remaining:
        # 1. 跳过上游失败的任务
        for task in plan:
            blockers = [dep for dep in task.depends_on
                        if dep in results and results[dep].status != "complete"]
            if blockers:
                results[task.id] = _skipped_task_result(task, blockers)
                remaining.discard(task.id)

        # 2. 找出所有依赖已完成的任务（当前 wave）
        ready = [t for t in plan
                 if t.id in remaining
                 and all(results.get(d) is not None and results[d].status == "complete"
                         for d in (t.depends_on or []))]

        # 3. 当前 wave 的所有任务并行执行
        wave = await asyncio.gather(
            *(_run_child_task(t, results, plan_context, ctx) for t in ready)
        )

        # 4. 同 wave 文件冲突检测
        if len(ready) > 1:
            conflicts.extend(detect_wave_conflicts(run_writes))
```

```
         Wave 1          Wave 2          Wave 3
      ┌─────────┐    ┌─────────┐    ┌─────────┐
      │ Task A  │    │ Task C  │    │ Task E  │
      │ (设计)   │───▶│ (前端)   │───▶│ (测试)   │
      └─────────┘    │ Task D  │    └─────────┘
                     │ (后端)   │
      ┌─────────┐    └─────────┘
      │ Task B  │
      │ (PRD)   │
      └─────────┘
```

### 5.2 子任务执行 — 重试 + 信号量

```python
async def _run_child_task(task, upstream, plan, ctx):
    # 1. 解析输入（上游产出 → artifact id）
    resolved_inputs = _resolve_task_inputs(task, upstream, plan)
    missing_required = [e for e in resolved_inputs if e.missing and e.input.required is not False]
    if missing_required:
        return _skipped_missing_inputs_task_result(task, missing_required)

    # 2. 获取信号量（最多 4 个子任务并行，FIFO + abort-aware）
    release = await sub_agent_run_semaphore.acquire(ctx.cancel_event)
    try:
        base_prompt = await build_sub_agent_prompt(task, upstream, ...)
        continuation_context = None

        # 3. 重试循环（最多 MAX_CHILD_TASK_ATTEMPTS 次）
        for attempt in range(1, MAX_CHILD_TASK_ATTEMPTS + 1):
            prompt = (
                _build_continuation_prompt(base_prompt, task, attempt, continuation_context)
                if continuation_context else base_prompt
            )
            evaluation = await _run_child_task_attempt(task, prompt, ctx)
            evaluated_result = _evaluate_child_task_result(task, evaluation.raw_result, evidence)

            if evaluated_result.status == "complete":
                # 自动创建 project artifact
                project_id = await _maybe_create_project_artifact(evidence=..., ...)
                return result

            # 构建 continuation context 供下一次重试
            continuation_context = _build_task_continuation_context(task, evaluation, attempt, MAX)
    finally:
        release()
```

### 5.3 Continuation Prompt — 不从头再来

当子任务失败需要重试时，系统不会重新发送完整提示，而是追加一个 `<continuation>` 块：

```python
def _build_continuation_prompt(base_prompt, task, attempt, continuation_context):
    return "\n".join([
        base_prompt,
        "",
        "<continuation>",
        f'You are continuing the same dispatched task "{task.id}". '
        f'This is attempt {attempt}/{MAX_CHILD_TASK_ATTEMPTS}.',
        "Do not restart from scratch if useful files already exist. "
        "Inspect the workspace, fix the missing or failing parts.",
        continuation_context,  # 上一次尝试的详细结果
        "</continuation>",
    ])
```

`continuation_context` 包含：
- 上次尝试的状态和错误信息
- 验证命令的执行结果（exit code、output 尾部 4000 字符）
- target paths（期望修改的文件路径）

### 5.4 同 Wave 文件冲突检测

当同一 wave 中多个子任务并行执行时，可能写入同一文件：

```python
# 检测逻辑（在 utils/dispatch_file_writes.py 中）
def detect_wave_conflicts(run_writes: list[RunFileWrites]) -> list[FileWriteConflict]:
    """同一文件被 ≥2 个子任务以不同内容写入 → 冲突"""
```

冲突会触发 replan——系统会建议"把写同一文件的任务用 dependsOn 串行化"。

---

## 6. Task Result Report — 完成证据链

### 6.1 概述

子任务完成后必须调用 `report_task_result` 工具提交结构化报告。
系统会对报告进行多维度门控验证，确保任务真正完成而不是"LLM 自己说完成了"。

核心文件：`backend/app/services/task_result_report.py`（433 行）

### 6.2 报告结构

```python
class ReportTaskResultArgs(BaseModel):
    status: str                    # "complete" | "failed" | "blocked"
    summary: str                   # 完成摘要
    acceptanceResults: list[...]   # 每条验收标准的通过/失败 + 证据
    filesChanged: list[...]        # 修改/创建/删除的文件
    commandsRun: list[...]         # 执行过的命令 + exitCode
    tests: list[...]               # 测试命令 + 通过/失败
    blockers: list[str]            # 阻塞因素
```

### 6.3 完成门控 — evaluate_task_result_report()

这是最关键的验证函数，按严格顺序检查 6 个维度：

```python
def evaluate_task_result_report(task, report, evidence):
    # ① 报告存在性
    if not report:
        return Evaluation(ok=False, error="completed without report_task_result")

    # ② 状态检查
    if report["status"] != "complete":
        return Evaluation(ok=False, error="reported failed/blocked")

    # ③ 失败命令证据（有 exit_code != 0 且后续没有同命令成功）
    failed_commands = [c for c in evidence.commands
                       if _is_failed_command(c)
                       and not _has_later_successful_command(c, ...)]

    # ④ 验收标准检查（报告中 acceptanceResults 必须全部 passed）
    failed_acceptance = [r for r in report["acceptanceResults"] if not r["passed"]]

    # ⑤ 合约验收覆盖（task.acceptanceCriteria 中每条都必须在报告中出现）
    missing = [c for c in task.acceptance_criteria if c not in reported_criteria]

    # ⑥ 目标路径证据（task.targetPaths 中每个路径必须在 filesChanged 或 file_writes 中出现）
    missing_paths = [p for p in task.target_paths if not _has_path_evidence(p, ...)]

    # ⑦ 必须命令证据（task.requiredCommands 每条必须有成功执行记录）
    missing_commands = [r for r in task.required_commands
                        if not _has_successful_command_evidence(r.command, ...)]

    # ⑧ 代码任务特殊检查：必须有成功的构建/编译/测试命令
    if is_code_implementation_task(task):
        if not has_successful_verification_command_evidence(evidence):
            return Evaluation(ok=False, error="missing runnable verification")

    # ⑨ 必需证据检查
    missing_evidence = [r for r in task.required_evidence
                        if not _required_evidence_satisfied(r, ...)]
```

### 6.4 验证命令识别

系统通过正则识别哪些命令是"验证命令"（vs 准备命令）：

```python
_VERIFICATION_COMMAND_PATTERNS = [
    re.compile(r"\b(?:pnpm|npm|yarn|bun)\b(?=.*\b(?:build|test|lint|typecheck)\b)"),
    re.compile(r"\b(?:tsc)\b"),              # TypeScript 编译
    re.compile(r"\bnext\s+build\b"),         # Next.js 构建
    re.compile(r"\bvite\s+build\b"),         # Vite 构建
    re.compile(r"\bmvn\b(?=.*\b(?:compile|test|package)\b)"),  # Maven
    re.compile(r"\bgradle\b(?=.*\b(?:build|test)\b)"),         # Gradle
    re.compile(r"\bgo\s+(?:test|build)\b"),  # Go
    re.compile(r"\bcargo\s+(?:test|build)\b)"), # Rust
    re.compile(r"\bpytest\b"),               # Python pytest
    re.compile(r"\bruff\s+check\b"),         # Python ruff lint
    re.compile(r"\bmypy\b"),                 # Python 类型检查
]

# 区分准备命令和验证命令：
# "pnpm install" → 准备（不算）
# "pnpm build"   → 验证（算）
def _is_prepare_command(command):
    return bool(_PREPARE_COMMAND_RE.search(command)) and not bool(_BUILD_VERB_RE.search(command))
```

---

## 7. 辅助服务矩阵

### 7.1 Settings Service — 全局配置单例行

核心文件：`backend/app/services/settings_service.py`（232 行）

```python
SINGLETON_ID = "singleton"  # 全表只有一行

async def get_effective_api_key(provider: str) -> str | None:
    """API Key 优先级：app_settings → 环境变量 → None"""
    settings = await get_app_settings()
    if provider == "anthropic":
        return settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if provider == "openai":
        return settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
    ...
```

**companion.json 同步** — 移动端伴侣配置：

```python
def sync_companion_runtime(settings):
    """写入 companion.json + 设置/清除 AGENTHUB_MOBILE_TOKEN 环境变量"""
    write_companion_config(
        companion_mode=settings.companion_mode,     # "off" | "lan" | "tailnet"
        mobile_device_token=settings.mobile_device_token,
        companion_port=DEFAULT_COMPANION_PORT,       # 60646
    )
    if settings.companion_mode != "off" and settings.mobile_device_token:
        os.environ["AGENTHUB_MOBILE_TOKEN"] = settings.mobile_device_token
    else:
        os.environ.pop("AGENTHUB_MOBILE_TOKEN", None)
```

**UPSERT 语义**：

```python
async def update_app_settings(patch):
    # key 在 patch 中 → 写入（None = 清空）
    # key 不在 patch 中 → 不触碰
    # companion_mode 开启时自动创建 mobile_device_token
    if row.companion_mode != "off" and not row.mobile_device_token:
        row.mobile_device_token = new_mobile_device_token()  # 24 bytes base64url
    sync_companion_runtime(row)  # 同步到 companion.json
```

### 7.2 Deploy Command Service — 斜杠命令部署

核心文件：`backend/app/services/deploy_command_service.py`（309 行）

用户在聊天中输入 `/deploy`（或 `部署` / `发布` / `上线`）触发部署流程：

```python
DEPLOY_COMMAND_RE = re.compile(
    r"^(?:/deploy|部署|发布|上线)(?:\s+(art_[0-9A-Za-z]+))?$",
    re.IGNORECASE,
)

# 决策流程：
# 1. 无候选 → 探测 workspace 静态输出目录（dist/build/out/client/dist...）
# 2. 单候选 → 自动部署
# 3. 多候选 → 发送选择消息让用户选
def decide_deploy_command(candidates, artifact_id):
    if artifact_id: return _DeployDecision(kind="deploy", artifact_id=artifact_id)
    if not candidates: return _DeployDecision(kind="no_candidates")
    if len(candidates) == 1: return _DeployDecision(kind="deploy", artifact_id=candidates[0].artifact_id)
    return _DeployDecision(kind="select", candidates=candidates)
```

**延迟 Handler 注册**：

```python
# 部署工具在 tools/registry.py 中注册，避免循环依赖
_deploy_artifact_fn: DeployArtifactFn | None = None
_deploy_workspace_fn: DeployWorkspaceFn | None = None

def set_deploy_handlers(*, artifact_fn=None, workspace_fn=None):
    global _deploy_artifact_fn, _deploy_workspace_fn
    if artifact_fn: _deploy_artifact_fn = artifact_fn
    if workspace_fn: _deploy_workspace_fn = workspace_fn
```

> **设计意图**：deploy_command_service 不知道具体的部署实现，
> 只负责解析命令和决策。实际的部署函数由 tools 层注入，
> 实现了"解析-决策-执行"三层分离。

### 7.3 Attachment Service — 文件上传与沙箱

核心文件：`backend/app/services/attachment_service.py`（179 行）

```python
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB 限制

async def upload_attachment(conversation_id, file_name, data, content_type=None):
    # 1. 空文件/超大文件拒绝
    # 2. 查找 conversation 的 workspace
    # 3. 写入 workspace.root_path/uploads/{id}{ext}
    # 4. 沙箱安全检查
    resolved = os.path.abspath(abs_path)
    if not is_path_within(resolved, root_path):
        raise ValueError("Path traversal detected")
    # 5. 扩展名安全过滤
    ext = _sanitize_ext(file_name)  # 只允许 .[a-z0-9]{1,8}
    # 6. MIME 推断
    mime_type = content_type or _guess_mime(ext)
```

### 7.4 Project Artifact — 自动项目文件包

核心文件：`backend/app/services/project_artifact.py`（93 行）

当子任务通过 `fs_write` 写入文件时，系统自动构建 project artifact：

```python
def build_project_files(file_writes, workspace_root):
    """fs_write 证据 → ProjectFile 列表"""
    by_path = {}
    for fw in file_writes:
        if not is_path_within(fw.absolute_path, workspace_root):
            continue  # 沙箱外文件跳过
        rel = _to_rel(fw.absolute_path, workspace_root)
        # 同路径去重，保留最后写入的 size
        by_path[rel] = ProjectFile(path=rel, sizeBytes=fw.bytes or 0)
    return sorted(by_path.values(), key=lambda f: f.path)

def zip_project_from_workspace(workspace_root, files, title, exported_at_iso):
    """实时文件 zip 导出（读当前 workspace 内容，而非创建时的快照）"""
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            abs_path = os.path.abspath(os.path.join(workspace_root, rel))
            if not is_path_within(abs_path, workspace_root):
                continue
            if os.path.isfile(abs_path):
                with open(abs_path, "rb") as fh:
                    zf.writestr(rel, fh.read())
        zf.writestr("README.txt", f"Project artifact: {title}\n...")
```

### 7.5 Context Compaction — 上下文摘要注入

核心文件：`backend/app/services/context_compaction_service.py`（58 行）

长对话中，历史消息可能超出 LLM 上下文窗口。Context Compaction 读取已存储的摘要，
注入到 prompt 前缀中：

```python
async def prefix_prompt_with_context_summary(conversation_id, prompt):
    """如果存在摘要，在 prompt 前追加 XML 摘要块"""
    latest = await get_latest_context_summary(conversation_id)
    if latest is None:
        return prompt
    return "\n".join([render_conversation_summary_block(latest), "", prompt])

def render_conversation_summary_block(summary):
    return "\n".join([
        f'<conversation_summary covered_until_message_id="{summary.covered_until_message_id}">',
        summary.summary,
        "</conversation_summary>",
    ])
```

> **注意**：当前只移植了读取/格式化部分。完整的 compact 流程
> （调 LLM 生成摘要 → 存储 ContextSummary 行）被标记为 DEFERRED，
> 因为它不在 runner 热路径上。

---

## 8. 安全与沙箱模型

### 8.1 Workspace 隔离

每个会话有独立的 workspace 目录，所有文件操作被限制在 workspace 内。

核心文件：`backend/app/utils/workspace_utils.py`（164 行）

```python
def get_effective_cwd(workspace):
    """local 模式 → 用户绑定的路径；sandbox 模式 → 内部 rootPath"""
    if workspace.mode == "local" and workspace.bound_path:
        return workspace.bound_path
    return workspace.root_path

def is_path_within(child, parent):
    """跨平台子树包含检查（Windows 大小写不敏感）"""
    c = _norm(child)  # abspath + lower (Windows)
    p = _norm(parent)
    return c == p or c.startswith(p + os.sep)
```

### 8.2 路径安全检查 — is_path_safe()

这是"软安全"——阻止用户意外把 workspace 绑定到敏感目录：

```python
def is_path_safe(abs_path):
    # 拒绝：
    # 1. UNC 设备路径和网络共享（\\?\ / \\.\）
    # 2. 用户 home 目录本身（子目录可以）
    # 3. 敏感子路径：.ssh / .aws / .gcloud / .kube / .gnupg / .docker
    #    Windows: AppData\Roaming\Microsoft\Credentials 等
    # 4. 系统根目录：
    #    POSIX: /etc, /usr, /bin, /var, /System
    #    Windows: 每个驱动器的 \Windows, \Program Files, \$Recycle.Bin
```

### 8.3 沙箱检查在各处的应用

```
┌────────────────────────────────────────────────────────────┐
│                    沙箱检查点                                │
│                                                            │
│  attachment_service   → is_path_within(resolved, root_path) │
│  project_artifact     → is_path_within(abs_path, root)      │
│  resolve_safe_path    → is_path_within(abs_path, cwd)       │
│  assert_path_within   → resolve_safe_path or raise          │
│  zip_project_export   → is_path_within(abs_path, root)      │
│                                                            │
│  _sanitize_ext()       → 只允许 .[a-z0-9]{1,8}             │
│  _normalize_project_path() → 拒绝绝对路径 + .. + 驱动前缀    │
└────────────────────────────────────────────────────────────┘
```

---

## 9. 可扩展性设计

### 9.1 添加新 Artifact 类型

1. 在 `artifact_service.py` 的 `build_artifact_content()` 中添加新的 `if` 分支
2. 编写对应的 `_build_xxx(raw)` builder 函数
3. 在 `serialize_artifact_export()` 中添加导出逻辑
4. 前端添加对应的渲染组件

### 9.2 添加新的依赖推断主题

1. 在 `dispatch_plan.py` 中定义新的 `_CONSUMES_XXX_PATTERN` 和 `_PRODUCES_XXX_PATTERN`
2. 在 `_get_consumed_artifact_topics()` 和 `_get_produced_artifact_topics()` 中添加分支
3. 系统会自动在编译阶段使用新主题进行依赖推断

### 9.3 添加新的验证命令模式

在 `task_result_report.py` 的 `_VERIFICATION_COMMAND_PATTERNS` 列表中添加正则即可：

```python
# 例如添加 Swift 编译验证
_VERIFICATION_COMMAND_PATTERNS.append(
    re.compile(r"\bxcodebuild\b(?=.*\b(?:build|test)\b)", re.IGNORECASE)
)
```

### 9.4 动态 Replan 机制

```python
def build_replan_context(views, conflicts):
    """生成补救计划的上下文前缀"""
    # 输出 XML 格式的上一轮结果：
    # <previous_round_results>
    #   <task id="t1" agent="a1" status="complete" />
    #   <task id="t2" agent="a2" status="failed" error="..." />
    # </previous_round_results>
    # <file_conflicts>
    #   <conflict path="src/index.tsx" tasks="t3, t4" />
    # </file_conflicts>
    # + 中文指导："围绕 original_request 的原始目标输出补救 plan_tasks..."

def build_revise_context(current_plan, feedback):
    """用户修改请求 → 重新计划的上下文"""
    # <current_plan>...</current_plan>
    # <user_revision_request>用户反馈</user_revision_request>
    # + "请据此调整，重新调用 plan_tasks 输出完整的新计划"
```

---

## 10. 自检清单

### Artifact 系统
- [ ] 能说出 7 种 artifact 类型及各自的标准化策略
- [ ] 理解 `_unwrap_stringified_content()` 为什么存在
- [ ] 能解释版本链的"爬根 + BFS"算法及为什么不能只 BFS
- [ ] 能区分 `ArtifactExport.kind` 的四种值

### Dispatch Plan
- [ ] 能说出 plan 生命周期的 5 个阶段（解析→验证→编译→审核→执行）
- [ ] 能解释文本启发式依赖推断的 3 种策略
- [ ] 能说出代码任务合约标准化做了什么（project output + 可运行验收）
- [ ] 能解释 DFS 三色环检测的工作原理

### Orchestrator
- [ ] 能画出 PLAN→EXECUTE→AGGREGATE 三阶段流程
- [ ] 理解 `on_tool_call` 如何拦截 `plan_tasks` 而不真正执行
- [ ] 能解释 Plan Review Gate 的 asyncio.Future 阻塞机制
- [ ] 能说出 replan 的触发条件（任务未完成 / 文件冲突）
- [ ] 能解释 continuation prompt 的设计意图

### Task Result Report
- [ ] 能列举完成门控的 6+ 个检查维度
- [ ] 能区分验证命令和准备命令
- [ ] 理解"客观证据"vs"自报告"的区别

### 安全模型
- [ ] 能解释 `is_path_within` 和 `is_path_safe` 的区别
- [ ] 能列举至少 4 个沙箱检查点
- [ ] 理解 workspace 的 local/sandbox 两种模式
