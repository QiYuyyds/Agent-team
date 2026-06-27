## Why

当前 Document+Version 知识库体系存在三个断裂点，导致"文档版本更新"链路无法闭环：

1. **页数丢失**：`parser.py` 的 pdftotext 降级分支硬编码返回 `pages=0`，导致 PDF 在 pdfplumber/PyPDF2 不可用时即使成功提取文本也显示 0 页，列表与版本历史中页数恒为 0。
2. **无法上传新版本**：前端 `uploadDocument` 只传 `file`，后端 `POST /api/documents/upload` 不接收 `document_id`，`upload_file` 每次都建新文档而非为已有文档创建新版本——版本历史形同虚设。
3. **版本更新数据不闭环**：`write_document` 更新分支入库新内容时不清理旧版本 RAG 数据（PG/Milvus/ES/Neo4j），旧 chunks 残留或重复，检索会同时命中新旧版本。此外全量重处理未变化的 chunk 浪费 embedding 与 LLM 实体抽取 token。

## What Changes

- 修复 pdftotext 解析器页数统计：不再硬编码 0，改为从 PDF 实际页数获取（`pdfinfo` 或页标记计数）。
- 后端 `POST /api/documents/upload` 支持可选 `document_id`/`title`/`doc_type` 表单字段；`upload_file` 透传 `document_id` 给 `write_document`，命中则创建新版本而非新文档。
- 前端 `uploadDocument` API 增加 `documentId` 参数；`UploadDocumentDialog` 支持"上传新版本"模式；`DocumentDetail` 版本历史区新增"上传新版本"入口。
- **BREAKING**：`_ingest_content` 改为"先清旧→再入新"流程——入库新版本前按 `document_id` 清理该文档所有旧版本 RAG 数据（PG + ES + Milvus + Neo4j），再切分入库新内容。
- 新增 `delete_versions_by_document(document_id)`：按 `document_id` 批量清理旧版本数据，复用四路删除回调，供版本更新与重入库调用。
- 新增 chunk 级 content hash 缓存：`rag_chunks` 表增加 `content_hash` 字段；ingest 时按 chunk content 的 sha256 去重，命中已有相同 content_hash 的行则跳过该 chunk 的 embedding 与 KG LLM 抽取，仅回填 version_id 关联，实现未变化 chunk 零 token 消耗。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `document-knowledge-base`：修改 Parser 管道需求（pdftotext 页数）、上传文件需求（支持 document_id 上传新版本）、删除文档需求（拆出按 document_id 清旧逻辑复用），新增"版本更新清理旧数据"与"chunk 级 content hash 缓存"需求，修改前端需求（文档详情新增上传新版本入口）。

## Impact

- 后端：`backend/app/rag/parser.py`（pdftotext 页数）、`backend/app/services/document_service.py`（upload_file 透传、_ingest_content 先清后入、delete_versions_by_document）、`backend/app/api/documents.py`（upload 路由表单字段）、`backend/app/rag/rag_engine.py`（chunk hash 去重）、`backend/app/infra/hybrid.py`（index_chunks 跳过缓存命中）、`backend/app/db/models.py`（rag_chunks 增加 content_hash）。
- 前端：`src/lib/api.ts`（uploadDocument 参数）、`src/components/upload-document-dialog.tsx`（新版本模式）、`src/components/document-detail.tsx`（上传新版本入口）。
- 数据库：`rag_chunks` 表新增 `content_hash VARCHAR(16)` 列（可空，索引）。
