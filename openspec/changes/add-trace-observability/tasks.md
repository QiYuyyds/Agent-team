## 1. OTel 采集基建

- [ ] 1.1 添加后端依赖：`opentelemetry-api`、`opentelemetry-sdk`、`opentelemetry-instrumentation-fastapi`、`opentelemetry-instrumentation-httpx` 到 `backend/requirements.txt`
- [ ] 1.2 创建 `backend/app/observability/__init__.py`，导出 `init_observability`、`get_tracer`、`traced` 装饰器
- [ ] 1.3 创建 `backend/app/observability/tracer.py`：`init_observability(settings)` 初始化 TracerProvider，注册 SpanProcessor + 自研 exporter；提供 `get_tracer(name)` 返回 OTel tracer；配置项读取采样率/开关
- [ ] 1.4 创建 `backend/app/observability/instrumentation.py`：定义 `@traced(span_name, **attrs)` 装饰器（同步/异步兼容，自动捕获异常并设 span status）；定义属性 key 常量（`AGENTHUB_HITS`、`AGENTHUB_EMPTY`、`AGENTHUB_MODEL` 等，统一 `agenthub.` 前缀）
- [ ] 1.5 在 `backend/app/main.py` 的 `lifespan` 启动阶段调用 `init_observability(settings)`，关闭阶段 shutdown provider

## 2. 自研 PG SpanExporter 与存储

- [ ] 2.1 创建 `backend/app/db/models/trace.py`：定义 `Trace` 模型（id, trace_id, kind, root_name, status, duration_ms, agent_id, error, created_at）与 `Span` 模型（id, trace_id FK, span_id, parent_span_id, name, start_ms BigInteger, end_ms BigInteger, duration_ms, depth, status, attributes JSONB, span_order, created_at）
- [ ] 2.2 确保新模型导入到 `Base`（记忆 `SQLAlchemy create_all需确保模型已导入Base`），在 `backend/app/db/engine.py` 或模型 `__init__` 中注册
- [ ] 2.3 创建 alembic 迁移 `backend/alembic/versions/xxxx_add_traces_spans.py`：建 `traces` + `spans` 两表，`spans` 上建 `trace_id` 索引、`parent_span_id` 索引、`created_at` 索引（清理用）
- [ ] 2.4 创建 `backend/app/observability/exporter.py`：实现 OTel `SpanExporter` 协议，`export(spans)` 批量将 OTel SpanData 转换为 `traces`/`spans` 行写入 PG；`shutdown()` 刷新缓冲
- [ ] 2.5 在 `tracer.py` 中用 `BatchSpanProcessor(PgSpanExporter(...))` 注册，批量异步写避免阻塞主链路
- [ ] 2.6 验证：启动后端，发一个 `/health` 请求，查 PG 确认 `traces`/`spans` 有 FastAPI 自动生成的根 span

## 3. 自动 Instrumentation（B 类浅链路）

- [ ] 3.1 在 `init_observability` 中调用 `FastAPIInstrumentor.instrument_app(app)`，自动包裹所有路由
- [ ] 3.2 调用 `HTTPXClientInstrumentor().instrument()`，自动包裹 httpx 客户端（覆盖 LLM API 外部调用）
- [ ] 3.3 验证：调用 `/api/conversations`、`/api/agents` 等接口，确认每个请求在 `traces` 表有一条记录，`kind=api`
- [ ] 3.4 验证：触发一次 agent run（含 LLM 调用），确认 httpx 自动生成的 LLM 调用 span 出现，记录了 url/duration

## 4. A 类深链路手动埋点

- [ ] 4.1 `backend/app/services/agent_runner.py`：在 `execute_run` 外层加 `@traced("agent.run", agent_id=..., run_id=..., conversation_id=...)`；在 `build_adapter_input`、`execute_simple_run`、`consume_stream` 各加子 span
- [ ] 4.2 `backend/app/adapters/base.py`：在 `AgentPlatformAdapter.stream` 实现外层加 span，记录 `adapter_name`、`model_id`；各子类（claude/custom/mock）继承即可
- [ ] 4.3 `backend/app/services/rag_service.py`：在 `search()` 外层加 `@traced("rag.search")`，记录 `query`(截断 100 字)、`mode`；在 `ingest()` 加 `@traced("rag.ingest")`
- [ ] 4.4 `backend/app/main.py` 内联回调：在 `milvus_search` 加 `@traced("rag.milvus_search")` 记录 `hits`、`empty`；`es_search` 同理；`kg_search` 记录 `hits`、`skipped`
- [ ] 4.5 工具执行入口：在 tool registry 的分发函数或各 tool handler 外层加 `@traced("tool.{name}")`，记录 `tool_name`、`success`
- [ ] 4.6 `backend/app/memory/memory_service.py`：召回方法加 `@traced("memory.recall")`，记录 `source`（stm/ltm）
- [ ] 4.7 验证：触发一次含 RAG 工具调用的 agent run，查 PG 确认 span 树嵌套正确：`agent.run > adapter.stream > tool.rag_search > rag.milvus_search / rag.es_search`
- [ ] 4.8 验证空召回场景：构造一个 RAG 查不到的 query，确认 `rag.es_search` span 的 `agenthub.empty=true`，`hits=0`

## 5. REST 查询接口

- [ ] 5.1 创建 `backend/app/api/traces.py`：`GET /api/traces` 支持 query 参数 `kind`(agent_run|api)、`status`(ok|error)、`limit`(默认 50)、`offset` 分页；返回 trace 列表（trace_id, kind, root_name, status, duration_ms, agent_id, created_at）
- [ ] 5.2 `GET /api/traces/{trace_id}`：返回该 trace 的所有 spans，按 `depth`+`span_order` 排序，前端可直接渲染嵌套树；包含 `attributes` JSONB
- [ ] 5.3 在 `backend/app/main.py` 注册 `app.include_router(traces.router, prefix="/api", tags=["traces"])`
- [ ] 5.4 验证：手动触发几次 agent run + 常规 API 调用，用 curl/Postman 验证列表与详情接口返回正确

## 6. 前端监控页

- [ ] 6.1 创建 `src/shared/api/traces.ts`：封装 `fetchTraces(params)` 与 `fetchTraceDetail(traceId)` 客户端
- [ ] 6.2 创建 `src/stores/trace-store.ts`：zustand store 管理列表/详情/筛选条件/加载状态
- [ ] 6.3 创建 `src/app/monitor/page.tsx`：监控页布局，顶部筛选栏（kind/status 下拉 + 刷新按钮）+ 左侧 trace 列表 + 右侧详情
- [ ] 6.4 创建 `src/components/monitor/trace-waterfall.tsx`：自研瀑布流组件，按 `depth` 缩进，`start_ms/end_ms` 计算时间条 `left%/width%`，hover 显示 span 属性，`agenthub.empty=true` 红色标记，`status=error` 高亮
- [ ] 6.5 创建 `src/components/monitor/trace-detail.tsx`：详情面板，展示 span 树 + 选中 span 的全部属性 JSONB
- [ ] 6.6 在前端导航（sidebar/菜单）加入 `/monitor` 入口
- [ ] 6.7 验证：启动前端，打开 `/monitor`，触发一次 agent run 后点刷新，确认瀑布流正确展示嵌套 span，空召回 span 红标可见

## 7. 配置与保留策略

- [ ] 7.1 在 `backend/app/config.py` 新增配置项：`trace_enabled`(bool, 默认 True)、`trace_sample_rate`(float, 默认 1.0 全量)、`trace_retention_days`(int, 默认 7)
- [ ] 7.2 在 `lifespan` 启动一个后台任务（或定时），按 `trace_retention_days` 清理过期 `traces`/`spans`（`DELETE WHERE created_at < now() - retention`）
- [ ] 7.3 验证：临时设 `trace_retention_days=0`，确认清理任务删除了数据；恢复默认值

## 8. 端到端验证

- [ ] 8.1 端到端排障场景验证：构造 RAG 召回为空的情况（如查询知识库中不存在的词），打开 `/monitor`，确认能从瀑布流一眼定位是 Milvus 还是 ES 返回 0 hits
- [ ] 8.2 工具失败排障验证：构造一个工具调用失败（如 fs_grep 搜索不存在的路径），确认 trace 中该 `tool.{name}` span `status=error` 且前端高亮
- [ ] 8.3 编排器多 agent 场景验证（若 orchestrator 可用）：触发一次 orchestrator run，确认 span 树正确反映多子 agent 调度顺序与并发
- [ ] 8.4 性能验证：确认 span 采集与写库（BatchSpanProcessor 异步）对 agent run 主链路延迟影响 < 5%
