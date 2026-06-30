## Context

项目当前调用链跨越多层：

- **A 类深链路**：一次 agent run 经历 `POST /api/messages` → `AgentRunner.execute_run` → `build_adapter_input` → `Adapter.stream`（LLM 调用）→ 工具调用循环（`rag_search` / `fs_grep` / ...）→ RAG 三路召回（Milvus / ES / KG）+ RRF 融合 → Memory 召回 → DB 持久化
- **B 类浅链路**：常规 API（`/api/conversations` / `/api/agents` / `/api/documents` 等 14 个路由模块）的扁平 HTTP 调用

现状：`logging.basicConfig` 按模块分散，无 trace_id 关联。RAG 召回为空时无法区分"是 ES 没召回还是 Milvus 没召回"，排障依赖人工经验。

项目已明确 SaaS 化转型（见记忆 `项目定位从local-first向SaaS化转型`），采集层需采用标准语义以支持未来多实例、跨服务传播。

## Goals / Non-Goals

**Goals:**

- 一次 agent run 产生一棵 span 树，支持嵌套展开到 Milvus/ES/KG 子调用粒度
- B 类浅链路零侵入覆盖（FastAPI 自动 instrumentation）
- span 业务属性（hits/model/空召回标记/error）可记录并可查询
- 采集层采用 OpenTelemetry 标准语义，未来切 Jaeger/Tempo 仅替换 exporter
- 前端 `/monitor` 页瀑布流可视化，空召回/错误一眼可见
- 持久化到 PostgreSQL，支持历史回溯

**Non-Goals:**

- 不引入 Prometheus / Grafana / Jaeger 服务端（桌面端打包不可行；SaaS 期再接）
- 不做 Metrics 指标聚合（QPS/p99）——本轮只做 Traces
- 不做前端发起请求的 trace（只覆盖后端侧）
- 不做实时 SSE 推送（手动刷新即可）
- 不改 agent run / RAG / 工具的业务逻辑
- 不抓取 LLM 请求/响应 body（隐私 + 体积；只记 model/duration/token 数若可得）

## Decisions

### D1: 中档方案 — OTel SDK 采集 + 自研后端存储/前端

**选择**：OpenTelemetry SDK 标准采集 + 自研 PG SpanExporter + 自研 REST + 自研瀑布流前端

**理由**：
- 纯自研（contextvars）采集层非标准，SaaS 上云后跨服务传播需重写
- 全家桶（OTel + Jaeger + Prometheus + Grafana）在桌面端打包不可行，且 Prometheus/Grafana 是 Metrics 支柱，与本轮 Traces 需求冗余
- 中档方案采集层一次写好标准语义，未来切 Jaeger 仅替换 exporter，采集代码零改动

**备选**：纯自研 contextvars（桌面端够用但 SaaS 转型需重写）；全家桶（桌面端打包灾难）。

### D2: 自研 PG SpanExporter 而非直接 OTLP exporter

**选择**：实现 OTel `SpanExporter` 协议，`export(spans)` 将 span 批量写入 PostgreSQL `spans` 表

**理由**：
- 直接用 OTLP exporter 需起 Collector/Jaeger 服务端，桌面端不可行
- 复用项目已有 PostgreSQL + SQLAlchemy + asyncpg，零新基础设施
- 未来 SaaS 切 Jaeger：`provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=...)))`，采集代码不动
- 自研 exporter 可定制业务字段落库（hits/空召回直接入 JSONB，查询比 Jaeger tag 直观）

**备选**：直接 OTLP exporter → 本地 Jaeger（多一个服务进程）；用 OTel SDK 但 span 只入内存（无持久化）。

### D3: 痛点库手动埋点清单与属性约定

**选择**：对以下位置手动 `tracer.start_as_current_span()` 包裹，并记录业务属性：

| 埋点位置 | span name | 关键属性 |
|---------|-----------|---------|
| `AgentRunner.execute_run` | `agent.run` | `agent_id`, `run_id`, `conversation_id` |
| `build_adapter_input` | `agent.build_input` | `tool_names` |
| `execute_simple_run` | `agent.simple_run` | — |
| `Adapter.stream` | `adapter.stream` | `adapter_name`, `model_id` |
| `RAGService.search` | `rag.search` | `query`(截断), `mode` |
| `RAGService.ingest` | `rag.ingest` | `doc_hash` |
| `milvus_search` 回调 | `rag.milvus_search` | `hits`, `empty`(bool) |
| `es_search` 回调 | `rag.es_search` | `hits`, `empty`(bool) |
| `kg_search` 回调 | `rag.kg_search` | `hits`, `skipped`(bool) |
| 工具执行入口 | `tool.{name}` | `tool_name`, `success` |
| `MemoryService` 召回 | `memory.recall` | `source`(stm/ltm) |

**理由**：
- `pymilvus` / `neo4j` / `elasticsearch[async]` 无官方 OTel instrumentation，必须手动埋
- 业务属性（hits/empty）是排障核心，OTel span attribute 原生支持，前端可直接渲染
- 空召回标记 `empty=True` 让前端红色标记成为可能

**备选**：只靠 FastAPI/httpx 自动 instrumentation（无法看到 RAG 三路召回内部，痛点不解决）。

### D4: 两张表 traces / spans 而非单表 JSONB

**选择**：`traces`（一次 run/请求的根）+ `spans`（嵌套节点，自引用 parent_span_id）

**理由**：
- 列表页查 `traces` 表轻量（只读根 span 元信息），详情页再 join `spans`
- 单表 JSONB 存整棵树：列表页需解析 JSON 才能取根信息，且单条 span 查询要全表扫描 JSON
- `spans.parent_span_id` 自引用天然表达嵌套，`depth` 字段加速前端缩进渲染
- 属性用 JSONB（灵活，不挡 schema）

**表结构**：
```
traces: id, trace_id, kind(agent_run|api), root_name, status, duration_ms,
        agent_id, error, created_at
spans:  id, trace_id(FK), span_id, parent_span_id, name, start_ms(BigInteger),
        end_ms(BigInteger), duration_ms, depth, status, attributes(JSONB),
        span_order, created_at
```

**备选**：单表 `traces` + `tree`(JSONB)（列表页解析成本高）；OTel 标准 OTLP 格式直接存（查询复杂）。

**注意**：`start_ms`/`end_ms` 用 BigInteger（记忆 `PostgreSQL时间戳字段需用BigInteger避免int32溢出`）。

### D5: 自研瀑布流前端组件

**选择**：Next.js 16 + tailwind 自研 `<TraceWaterfall>`，`div` + `left:%/width:%` 绝对定位

**理由**：
- trace 瀑布流交互特定（缩进层级 / hover 看 span 属性 / 空召回红标 / 错误高亮），现成图表库不贴合
- `mermaid` gantt 是静态渲染，不支持 hover 交互与动态筛选
- `recharts`/`visx` 处理瀑布流绕路，自研反而更直接
- 项目已有 tailwind 4 + base-ui + lucide-react，组件基建完备

**备选**：mermaid gantt（静态不可交互）；新引 recharts（绕路）。

### D6: 手动刷新而非 SSE 实时

**选择**：REST 轮询 `/api/traces`，前端手动刷新按钮

**理由**：
- 排障场景非实时监控，手动刷新足够
- 不复用 `EventBus/SSE`，避免干扰对话事件流
- 实现实最简，无连接管理负担

**备选**：复用现有 SSE 加 trace 事件类型（干扰对话流）；新建 `/api/trace/stream`（过度工程）。

### D7: 全量记录 + 内存/DB 双写 + 保留策略

**选择**：所有 span 全量写 PG，配置保留窗口（默认 7 天），定时清理

**理由**：
- 桌面端/SaaS 早期流量不大，全量记录无压力
- 采样会漏掉偶发空召回，违背排障初衷
- 保留策略避免无限膨胀

**备选**：只记慢请求/错误（漏掉正常但需复盘的链路）；只存内存（重启丢失，违背持久化目标）。

## Risks / Trade-offs

- **[OTel 依赖体积]** 4 个 opentelemetry-* 包增加后端依赖体积 → 缓解：相比 Jaeger 全家桶已极小，且 SaaS 转型必经
- **[痛点库手动埋点遗漏]** 埋点清单可能漏掉新增工具/召回路径 → 缓解：`instrumentation.py` 提供统一装饰器 `@traced("tool.{name}")`，新工具一行装饰即可接入
- **[PG 写入压力]** 每次 agent run 产生 20+ span 全量写库 → 缓解：`BatchSpanProcessor` 批量异步写，不阻塞主链路；SaaS 期可改采样
- **[span 属性 schema 漂移]** JSONB 无强 schema，不同版本属性名可能不一致 → 缓解：`instrumentation.py` 集中定义属性 key 常量，埋点统一引用
- **[trace_id 与 run_id 关系]** `run_id` 已是天然 trace_id，但 B 类浅链路无 run_id → 缓解：B 类用 OTel 自动生成的 trace_id，`traces.kind` 字段区分两类
- **[未来切 Jaeger 的属性兼容]** 自研 JSONB 属性可能与 Jaeger tag 语义不完全对齐 → 缓解：属性 key 对齐 OTel semantic conventions（如 `db.system`/`http.method`），自定义业务属性加 `agenthub.` 前缀
