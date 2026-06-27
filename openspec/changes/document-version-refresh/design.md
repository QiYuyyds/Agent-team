## Context

`document-knowledge-base` 体系已实现文档 CRUD、版本管理、四路 RAG 入库（PG/Milvus/ES/Neo4j）。但版本更新链路断裂：`upload_file` 不接收 `document_id`，每次建新文档；`write_document` 更新分支入库时不清理旧版本数据；`_ingest_content` 只追加不清理；`RAGEngine.ingest` 对整篇文档算一个 `doc_hash`，无 chunk 级去重，全量重处理浪费 embedding 与 LLM 实体抽取 token。此外 `parser.py` 的 pdftotext 分支硬编码 `pages=0`。

入库链路现状：`upload_file → write_document → _ingest_content → RAGEngine.ingest → HybridStore.index_chunks`，四路写入。`doc_hash = sha256(content)[:16]`，整篇共享。KG 抽取在 `index_chunks` 末尾以 `asyncio.create_task` fire-and-forget，每个 chunk 调一次 LLM。

## Goals / Non-Goals

**Goals:**
- 闭环版本更新：上传新版本 → 按 `document_id` 清旧四路数据 → 切分入新，保证检索只命中当前版本。
- 修复 pdftotext 页数，使 PDF 降级解析时页数正确。
- chunk 级 content hash 缓存：未变化 chunk 跳过 embedding API 与 KG LLM 抽取，零 token 消耗。
- 前端可对已有文档上传新版本。

**Non-Goals:**
- 不做真·增量 diff（新旧版本逐 chunk 比对）。插入文字会导致切分边界整体偏移，实现复杂且收益不明显。
- 不改 `doc_hash` 算法（整篇 sha256[:16] 保留，用于 KG 清理键）。
- 不改检索/RRF 融合链路。
- 不保存上传的原始文件（继续只存解析后的 `content_md`）。

## Decisions

### D1: pdftotext 页数 — 用 `\x0c` form-feed 计数

`pdftotext -layout` 输出中，页与页之间用 `\x0c`（form feed）分隔。统计输出中 `\x0c` 出现次数 +1 即页数，无需额外子进程或依赖。

**替代方案**：调用 `pdfinfo` 获取页数。否决：`pdfinfo` 同属 poppler-utils，可能同样不可用；且多一次子进程调用。`\x0c` 计数是 pdftotext 的标准输出契约，零额外依赖更可靠。

### D2: 上传新版本 — upload 路由增加可选 `document_id` 表单字段

`POST /api/documents/upload` 增加可选 Form 字段 `document_id`/`title`/`doc_type`。`upload_file` 接收后透传给 `write_document`——后者已支持"传 `document_id` 则创建新版本"逻辑（[document_service.py:100-134](file:///d:/java/project/bitdance-agenthub-main/backend/app/services/document_service.py#L100-L134)），最小改动复用既有分支。

### D3: 版本更新清理 — 按 `document_id` 批量，不按 `doc_hash` 逐版本

新增 `delete_versions_by_document(document_id)`：`SELECT id, doc_hash FROM rag_chunks WHERE document_id = ?` 一次查询拿到所有 pg_ids + doc_hashes 集合，然后批量删 PG、按 pg_ids 删 ES/Milvus、按 doc_hash 集合删 KG。

**替代方案**：遍历 `document_versions` 算每个 `doc_hash` 逐个调 `delete_by_doc_hash`。否决：N 次 PG 查询；且 `doc_hash` 基于内容，相同内容版本会重复计算。按 `document_id` 一次批量清理更高效，且 `rag_chunks.document_id` 字段已存在（add-document-knowledge-base 已加）。

### D4: `_ingest_content` 改为先清后入

`_ingest_content` 在调 `rag.ingest` 前，先调 `delete_versions_by_document(document_id)` 清旧。这是 **BREAKING** 但必要：不清旧则残留/重复，检索命中过期内容。

### D5: chunk 级 content hash 缓存 — 只省 embed_fn + KG 抽取，仍新增存储行

`rag_chunks` 增加 `content_hash VARCHAR(16)`（`sha256(chunk.content)[:16]`）。`RAGEngine.ingest` 切分后：
1. 对每个 chunk 算 `content_hash`。
2. 批量查 PG：`SELECT content_hash, embedding FROM rag_chunks WHERE content_hash IN (...) AND embedding IS NOT NULL`，取每个 hash 的首个 embedding。
3. **命中**的 chunk：复用已有 embedding（不调 `embed_fn`），`index_chunks` 时该 chunk 不传给 KG index_fn（相同内容实体已抽取过）。
4. **未命中**的 chunk：正常调 `embed_fn` + KG 抽取。
5. 所有 chunk 仍写入新 PG 行 + Milvus insert + ES index（新 pg_id 关联新 version_id，保证版本隔离与检索正确性）。

**净效果**：省 `embed_fn` API 调用 + 省 LLM 实体抽取调用（最贵的两部分）；PG/Milvus/ES 行数不省（换取版本隔离正确性，值得）。

**替代方案**：命中时不新增行，直接 UPDATE 已有行 version_id。否决：破坏旧版本 chunks 隔离（旧版本应保留自己的行），且 Milvus 按 pg_id 删除会误删。

### D6: `content_hash` 字段 nullable，历史数据不回填

历史 `rag_chunks` 行 `content_hash` 为 NULL，不影响检索；新入库自动填充。加普通索引加速去重查询。

## Risks / Trade-offs

- **[先清后入有空窗期]** 清理与入库之间若失败，文档暂时无 RAG 数据。→ 缓解：知识库更新非高频；失败后可重试 `ingest_version` 重新入库；清理与入库分离使重试安全（幂等清旧）。
- **[chunk 缓存假设相同内容语义不变]** 合理前提：content 相同则 embedding 必然相同，LLM 抽取结果也相同。跨模型切换时历史 embedding 可能不匹配新模型维度。→ 缓解：缓存命中时校验 embedding 维度与 `settings.rag_milvus_dim` 一致，不一致则视为未命中重新生成。
- **[PG/Milvus 行数不省]** 相同内容跨版本会有多行。→ 取舍：换取版本隔离正确性，可接受；后续可加定时任务合并。
- **[pdftotext 不可用时仍返回 0]** pdftotext 未安装则该分支不可用，pages 保持 0。→ 与现状一致，非回归。

## Migration Plan

1. `rag_chunks` 表 `ALTER TABLE ADD COLUMN content_hash VARCHAR(16)`（可空 + 索引）。SQLAlchemy `create_all` 不更新已有表，需手动迁移脚本或 `ALTER`。
2. 部署后端代码（parser、document_service、rag_engine、hybrid、models）。
3. 部署前端代码（api.ts、upload-document-dialog、document-detail）。
4. 历史数据无需回填 `content_hash`；下次重入库时自动填充。
5. 回滚：后端代码回滚即恢复旧行为；`content_hash` 列保留无害（nullable）。

## Open Questions

无。方案已明确，依赖现有字段与回调，无新增外部依赖。
