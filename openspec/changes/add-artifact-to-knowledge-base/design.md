## Context

知识库入库管道（`DocumentService.write_document` → `RAGEngine.ingest` → 切块/embedding/索引）已完整，前端 `createDocument()` 也现成。产物库（`artifact-library.tsx`）已能列出产物、按 type 渲染图标、按需 `fetchArtifact(id)` 取完整内容。本变更只是在两者之间架一座**用户手动触发**的单向桥，范围严格限定在 `document` 类型。

## Goals / Non-Goals

**Goals**
- 用户在产物库点击即可把 document 产物收进知识库，被后续 `rag_search` 检索
- 重复点击同一产物不产生重复文档（幂等）
- 入库内容带可治理的来源标记，为防自我污染留抓手

**Non-Goals（本期明确不做）**
- 不做自动入库（产物一生成就 ingest）—— 自我污染风险高，留待后续评估
- 不支持 document 以外的类型（ppt 展平、code/project 读盘、image OCR 等均不做）
- 不做来源降权/审核门的检索期治理（只先打标记，治理逻辑后续提案）
- 不新增后端 REST 端点

## Decisions

### 决策 1：复用 `POST /api/documents`，不新增端点
`createDocument({ ..., ingestToRag: true })` 已经一步完成「建文档 + 切块 + embedding + 索引」。新增端点只会重复这条逻辑。前端只需一个薄封装把 artifact 字段映射成 `WriteDocumentRequest`。

### 决策 2：来源标记 `source='artifact_import'`
`Document.source` 现有值为 `agent_generated` / `user_upload`。新增第三个值 `artifact_import`，语义明确（既非 Agent 运行时自动产生，也非用户上传文件，而是从产物显式导入）。这是上一轮调研「来源治理」结论的最小落点——本期只打标记，不实现降权。

### 决策 3：防重复用 `metadata.artifactId`，不动 DB schema
方案对比：

| 方案 | 防重依据 | DB 改动 | 取舍 |
|---|---|---|---|
| A. Document 加 `artifact_id` 列 | 列等值查询 | 需迁移 | 最规范但要改 schema |
| **B. metadata.artifactId（选用）** | JSON 字段查询 | 无 | 零迁移，metadata 列已存在 |
| C. doc_hash 内容哈希 | 内容相同才命中 | 无 | 产物被二次编辑后哈希变，会漏判 |

选 **B**：`document_versions.metadata` 是现成 JSON 列，把 `artifactId` 写进去，`write_document` 在 `source==='artifact_import'` 时按 artifactId 查已有文档。doc_hash 作为兜底（内容完全相同时 RAGEngine 仍会去重），但主判据是 artifactId——它能正确处理「同一产物点两次」这一核心场景。

### 决策 4：按钮可见性严格按 `type === 'document'`
在 `TypeIcon`/列表项渲染处加条件，仅 document 项渲染按钮。其余类型连入口都不出现，从 UI 层强制执行范围。

## Risks / Trade-offs

- **内容漂移**：产物被二次编辑生成新版本后再次「加入知识库」，按 artifactId 会判为「已存在」而不更新知识库内容。**本期接受**——手动语义下用户可先删知识库旧文档再重新加入；自动同步版本留待后续。
- **自我污染（已缓解）**：手动触发 + 来源标记已把风险压到最低；真正的检索期治理（降权/审核）是后续独立提案的事。
- **document 正文取值**：依赖 `artifact.content.content` 为 markdown 字符串。需在封装层校验 `content.format === 'markdown'` 与 `content.content` 非空，缺失则报错而非静默入空文档。

## Migration Plan

无数据库迁移。纯增量功能，上线即用；已有产物与知识库不受影响。

## Open Questions

- 是否需要在知识库文档列表里反向显示「来源产物」链接（点回原产物）？—— 本期不做，可作为后续增强。
