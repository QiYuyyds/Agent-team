## ADDED Requirements

### Requirement: OpenTelemetry 采集层初始化

系统 SHALL 在后端启动时初始化 OpenTelemetry TracerProvider，并提供统一的 tracer 获取与埋点装饰器入口。

- `backend/app/observability/tracer.py` SHALL 提供 `init_observability(settings)`，初始化 `TracerProvider`、注册 `BatchSpanProcessor` + 自研 `PgSpanExporter`
- `get_tracer(name)` SHALL 返回标准 OTel `Tracer` 实例
- 采集开关 `trace_enabled`（默认 True）为 False 时，`init_observability` SHALL 跳过初始化且不产生任何 span
- 关闭阶段 SHALL 调用 `provider.shutdown()` 刷新缓冲 span

#### Scenario: 正常初始化

- **WHEN** 后端启动且 `trace_enabled=True`
- **THEN** TracerProvider 被创建并注册 PgSpanExporter
- **AND** 后续所有自动/手动埋点产生的 span 被批量写入 PostgreSQL

#### Scenario: 采集关闭

- **WHEN** `trace_enabled=False`
- **THEN** `init_observability` 不初始化 provider
- **AND** 所有埋点变为 no-op，不产生 span，不影响主链路

### Requirement: A 类深链路 span 采集

系统 SHALL 对一次 agent run 的关键调用点手动埋点，形成嵌套 span 树，覆盖 API → AgentRunner → Adapter → 工具 → RAG 三路召回 → Memory 全链路。

- `AgentRunner.execute_run` SHALL 产生 `agent.run` 根 span，属性含 `agent_id`、`run_id`、`conversation_id`
- `Adapter.stream` SHALL 产生 `adapter.stream` 子 span，属性含 `adapter_name`、`model_id`
- `RAGService.search` SHALL 产生 `rag.search` span，属性含 `query`（截断 100 字）、`mode`
- `milvus_search` / `es_search` / `kg_search` 回调 SHALL 各产生子 span，属性含 `hits`(int)、`empty`(bool) 或 `skipped`(bool)
- 工具执行入口 SHALL 产生 `tool.{name}` span，属性含 `tool_name`、`success`(bool)
- 所有 span SHALL 通过 OTel parent-child 上下文自动嵌套，无需手动传递 trace_id

#### Scenario: agent run span 树嵌套

- **WHEN** 触发一次含 RAG 工具调用的 agent run
- **THEN** 产生的 span 树 SHALL 包含 `agent.run > adapter.stream > tool.rag_search > rag.milvus_search` 与 `rag.es_search` 兄弟 span
- **AND** 所有子 span 的 `parent_span_id` 正确指向父 span

#### Scenario: RAG 空召回标记

- **WHEN** 一次 RAG 查询中 ES 返回 0 条结果
- **THEN** `rag.es_search` span 的 `attributes` SHALL 包含 `agenthub.empty=true` 与 `agenthub.hits=0`
- **AND** 前端 SHALL 将该 span 渲染为红色标记

### Requirement: B 类浅链路自动 instrumentation

系统 SHALL 通过 `opentelemetry-instrumentation-fastapi` 与 `opentelemetry-instrumentation-httpx` 自动包裹所有 HTTP 请求与 httpx 外部调用，零侵入覆盖常规 API。

- 所有 FastAPI 路由请求 SHALL 自动产生根 span，`traces.kind=api`
- 所有 httpx 客户端调用（含 LLM API 外部调用）SHALL 自动产生子 span，记录 url/method/duration
- 自动 instrumentation SHALL 不需要修改任何路由或服务代码

#### Scenario: 常规 API 自动记录

- **WHEN** 调用 `GET /api/conversations`
- **THEN** `traces` 表 SHALL 产生一条 `kind=api` 记录
- **AND** `spans` 表 SHALL 包含对应的 HTTP 根 span，记录路由、状态码、耗时

#### Scenario: LLM 外部调用自动记录

- **WHEN** adapter 通过 httpx 调用 LLM API
- **THEN** SHALL 自动产生 httpx 子 span，记录请求 url 与 duration
- **AND** 该 span 嵌套在 `adapter.stream` span 之下

### Requirement: PostgreSQL 持久化与表结构

系统 SHALL 将所有 trace/span 持久化到 PostgreSQL，采用 `traces` 与 `spans` 两张表。

- `traces` 表字段：`id`, `trace_id`, `kind`(agent_run|api), `root_name`, `status`(ok|error), `duration_ms`, `agent_id`(nullable), `error`(nullable), `created_at`
- `spans` 表字段：`id`, `trace_id`(FK), `span_id`, `parent_span_id`(nullable 自引用), `name`, `start_ms`(BigInteger), `end_ms`(BigInteger), `duration_ms`, `depth`, `status`, `attributes`(JSONB), `span_order`, `created_at`
- `start_ms` / `end_ms` SHALL 使用 BigInteger 类型以避免 int32 溢出
- `spans` 表 SHALL 在 `trace_id`、`parent_span_id`、`created_at` 上建索引
- span 业务属性（hits/empty/model 等）SHALL 存入 `attributes` JSONB，key 统一 `agenthub.` 前缀

#### Scenario: span 树落库

- **WHEN** 一次 agent run 完成
- **THEN** `traces` 表 SHALL 有 1 条 `kind=agent_run` 记录
- **AND** `spans` 表 SHALL 有对应的多条记录，`parent_span_id` 形成正确嵌套关系

#### Scenario: 业务属性查询

- **WHEN** 查询 `spans.attributes @> '{"agenthub.empty": true}'`
- **THEN** SHALL 返回所有空召回的 RAG 子 span
- **AND** 可直接用于排障定位

### Requirement: 自研 PgSpanExporter

系统 SHALL 实现 OTel `SpanExporter` 协议的自研 exporter，将 span 批量写入 PostgreSQL。

- `PgSpanExporter` SHALL 实现 `export(spans: Sequence[SpanData])` 与 `shutdown()` 方法
- exporter SHALL 通过 `BatchSpanProcessor` 异步批量写库，不阻塞主链路
- 未来切换 Jaeger 时，仅需将 `PgSpanExporter` 替换为 `OTLPSpanExporter`，采集代码零改动

#### Scenario: 批量异步写库

- **WHEN** 一次 agent run 产生 20+ span
- **THEN** span 通过 BatchSpanProcessor 批量异步写入 PG
- **AND** 主链路延迟影响 SHALL < 5%

### Requirement: REST 查询接口

系统 SHALL 提供 REST 接口查询 trace 数据，支持手动刷新模式。

- `GET /api/traces` SHALL 支持 query 参数 `kind`(agent_run|api)、`status`(ok|error)、`limit`(默认 50)、`offset` 分页
- 返回字段：`trace_id`, `kind`, `root_name`, `status`, `duration_ms`, `agent_id`, `created_at`
- `GET /api/traces/{trace_id}` SHALL 返回该 trace 的所有 spans，按 `depth`+`span_order` 排序，含 `attributes` JSONB
- 路由 SHALL 注册在 `/api` 前缀下，tag 为 `traces`

#### Scenario: 列表筛选错误链路

- **WHEN** 调用 `GET /api/traces?status=error&limit=20`
- **THEN** SHALL 返回最近 20 条 `status=error` 的 trace
- **AND** 不包含 `status=ok` 的 trace

#### Scenario: 详情树查询

- **WHEN** 调用 `GET /api/traces/run_xxx`
- **THEN** SHALL 返回该 trace 的所有 spans
- **AND** spans 按 `depth` 升序、`span_order` 升序排列，前端可直接渲染嵌套树

### Requirement: 前端瀑布流监控页

系统 SHALL 在 `/monitor` 路由提供监控页，自研瀑布流组件可视化 trace 调用树。

- 监控页 SHALL 包含筛选栏（kind/status 下拉 + 刷新按钮）、左侧 trace 列表、右侧详情面板
- 瀑布流组件 SHALL 按 `depth` 字段缩进展示 span 层级
- 时间条 SHALL 根据 `start_ms`/`end_ms` 相对 trace 起点计算 `left%`/`width%` 定位
- `agenthub.empty=true` 的 span SHALL 红色标记
- `status=error` 的 span SHALL 高亮
- hover span SHALL 显示该 span 的全部 `attributes`
- 数据获取 SHALL 通过手动刷新触发（非实时 SSE）

#### Scenario: 空召回可视化定位

- **WHEN** 用户在 `/monitor` 打开一次 RAG 召回为空的 agent run trace
- **THEN** 瀑布流 SHALL 展示 `rag.milvus_search` 与 `rag.es_search` 子 span
- **AND** 返回 0 hits 的 span SHALL 红色标记，用户一眼定位是哪路召回为空

#### Scenario: 错误链路筛选

- **WHEN** 用户在筛选栏选择 `status=error` 并刷新
- **THEN** 左侧列表 SHALL 只展示出错的 trace
- **AND** 点开详情后瀑布流中错误 span 高亮

### Requirement: 配置与保留策略

系统 SHALL 提供可观测性配置项与数据保留策略。

- `backend/app/config.py` SHALL 新增：`trace_enabled`(bool, 默认 True)、`trace_sample_rate`(float, 默认 1.0)、`trace_retention_days`(int, 默认 7)
- 系统 SHALL 在后台按 `trace_retention_days` 清理过期 `traces`/`spans`
- `trace_sample_rate=1.0` 表示全量记录；< 1.0 时按比例采样

#### Scenario: 保留期清理

- **WHEN** `trace_retention_days=7` 且存在 8 天前的 trace
- **THEN** 后台清理任务 SHALL 删除该 trace 及其所有 spans
- **AND** 清理后 `traces`/`spans` 表不残留过期数据

#### Scenario: 采样关闭

- **WHEN** `trace_sample_rate=0`
- **THEN** 不产生任何 span（等价于 `trace_enabled=False`）

### Requirement: 属性 key 语义约定

系统 SHALL 统一 span 属性 key 命名，业务自定义属性加 `agenthub.` 前缀，标准属性对齐 OTel semantic conventions。

- 业务属性：`agenthub.hits`、`agenthub.empty`、`agenthub.skipped`、`agenthub.model`、`agenthub.adapter_name`、`agenthub.tool_name`、`agenthub.success`
- 标准属性：`http.method`、`http.url`、`http.status_code`、`db.system`（对齐 OTel semantic conventions，为未来接 Jaeger 兼容）
- 属性 key 常量 SHALL 在 `instrumentation.py` 集中定义，埋点统一引用

#### Scenario: 属性 key 一致性

- **WHEN** 新增一个工具的埋点
- **THEN** 该工具 span 的 `tool_name` 属性 SHALL 使用 `agenthub.tool_name` key
- **AND** 不直接硬编码字符串，而是引用 `instrumentation.py` 中的常量
