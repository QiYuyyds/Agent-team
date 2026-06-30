## Why

项目当前仅有按模块分散的 `logging.basicConfig` 日志，一次 agent run 跨越 API → AgentRunner → Adapter → LLM → 工具 → RAG(Milvus+ES+KG) → Memory → DB 等 10+ 模块，日志无法关联。当 RAG 召回为空、工具调用失败时，排障依赖人工记忆中的"根因诊断任务"逐层排查，缺少直观的链路定位手段。

同时项目已明确从 local-first 向 SaaS 化转型（多用户、服务端部署）。这要求可观测性采集层采用标准语义（W3C TraceContext / OpenTelemetry），避免未来上云时重写采集代码。

引入 Trace 全链路观测能力，将排障模式从"靠经验逐层排查"转变为"点开监控页一眼定位"。

## What Changes

- 新增 OpenTelemetry SDK 采集层（`opentelemetry-api` / `opentelemetry-sdk`），采用标准 span 语义，为未来平滑接入 Jaeger/Tempo 预留采集层
- 新增 FastAPI / httpx 自动 instrumentation：自动包裹所有 HTTP 请求（B 类浅链路）与 LLM 外部 API 调用，零侵入覆盖常规接口
- 新增手动埋点覆盖 A 类深链路痛点位置：`AgentRunner.execute_run` / `Adapter.stream` / `RAGService.search` / 三路召回回调（Milvus/ES/KG）/ 工具执行入口 / `MemoryService` 召回
- 新增自研 `SpanExporter`：实现 OTel `SpanExporter.export()` 协议，将 span 写入 PostgreSQL，未来切换 Jaeger 仅需替换 exporter
- 新增 PostgreSQL 两张表 `traces` / `spans`（alembic 迁移），span 业务属性（hits/model/空召回标记）落 JSONB
- 新增 FastAPI REST 接口 `GET /api/traces`（列表）与 `GET /api/traces/{trace_id}`（含 spans 树），手动刷新模式
- 新增前端监控页 `/monitor`：Next.js 16 App Router，自研瀑布流时间轴组件，支持嵌套 span 展开、空召回红色标记、错误链路筛选
- 新增可观测性配置项：采样率、开关、存储保留策略

## Capabilities

### New Capabilities

- `trace-observability`: 全链路观测能力，包括 OTel 标准采集、A 类深链路（agent run 调用树）与 B 类浅链路（HTTP 请求）覆盖、PostgreSQL 持久化、REST 查询接口、前端瀑布流监控页

### Modified Capabilities

（无 — 本次变更为纯增量，不修改现有 agent run / RAG / 工具的业务逻辑，仅在关键函数外层包裹 span）

## Impact

- 新增文件：
  - 后端：`backend/app/observability/__init__.py`、`backend/app/observability/tracer.py`（OTel 初始化 + tracer 提供）、`backend/app/observability/exporter.py`（自研 PG SpanExporter）、`backend/app/observability/middleware.py`（FastAPI 中间件挂载）、`backend/app/observability/instrumentation.py`（手动埋点装饰器/上下文管理器）、`backend/app/api/traces.py`（REST 路由）
  - DB：`backend/app/db/models/trace.py`（SQLAlchemy 模型）、`backend/alembic/versions/xxx_add_traces_spans.py`（迁移）
  - 前端：`src/app/monitor/page.tsx`（监控页）、`src/components/monitor/trace-waterfall.tsx`（自研瀑布流组件）、`src/components/monitor/trace-detail.tsx`（详情面板）、`src/shared/api/traces.ts`（API 客户端）、`src/stores/trace-store.ts`（zustand 状态）
- 新增依赖：
  - 后端：`opentelemetry-api`、`opentelemetry-sdk`、`opentelemetry-instrumentation-fastapi`、`opentelemetry-instrumentation-httpx`
  - 前端：`swr`（可选，数据请求管理）
- 修改文件（仅埋点包裹，不改业务逻辑）：
  - `backend/app/main.py`：启动时初始化 OTel tracer + exporter + FastAPI instrumentation
  - `backend/app/services/agent_runner.py`：`execute_run` / `execute_simple_run` / `build_adapter_input` / `consume_stream` 外层加 span
  - `backend/app/adapters/base.py` 及各 adapter：`stream()` 外层加 span，记录 model/adapter_name
  - `backend/app/services/rag_service.py`：`search()` / `ingest()` 外层加 span
  - `backend/app/main.py` 内联回调 `milvus_search` / `es_search` / `kg_search`：各加子 span，记录 hits/空召回
  - 工具执行入口：每个 tool handler 外层加 span
- 基础设施依赖：PostgreSQL（新增 traces/spans 表）；不依赖新基础设施服务
- 不影响现有代码语义：所有 span 包裹为 `with span(...):` 上下文管理器或装饰器，不改变被包裹函数的返回值与异常传播
