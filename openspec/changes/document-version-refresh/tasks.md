## 1. 数据库迁移

- [x] 1.1 `backend/app/db/models.py` 的 `RagChunk` 模型新增 `content_hash = Column(String(16), nullable=True, index=True)` 字段
- [x] 1.2 编写并执行 `rag_chunks` 表 `ALTER TABLE ADD COLUMN content_hash VARCHAR(16)` 迁移（SQLAlchemy `create_all` 不更新已有表）

## 2. 后端 — pdftotext 页数修复

- [x] 2.1 修改 `backend/app/rag/parser.py` 的 `_extract_pdf_with_pdftotext`：将硬编码的 `return out.decode(...), 0, "pdftotext"` 改为统计输出中 `\x0c` 出现次数 +1 作为页数

## 3. 后端 — 版本更新清理旧 RAG 数据

- [x] 3.1 `backend/app/services/document_service.py` 新增 `delete_versions_by_document(document_id)` 方法：按 `rag_chunks.document_id` 一次查询 pg_ids + doc_hashes 集合，批量删 PG、按 pg_ids 删 ES/Milvus、按 doc_hash 集合删 KG（复用 RAGService 的四路删除回调）
- [x] 3.2 `document_service.py` `_ingest_content` 在调 `rag.ingest` 前先调 `delete_versions_by_document(document_id)` 清旧
- [x] 3.3 `document_service.py` `ingest_version` 同样在入库前先调 `delete_versions_by_document` 清旧
- [x] 3.4 `backend/app/services/rag_service.py` 新增 `delete_by_document_id(document_id)` 方法（按 document_id 查 pg_ids + doc_hashes 后调四路删除），供 DocumentService 调用

## 4. 后端 — 上传新版本

- [x] 4.1 `backend/app/services/document_service.py` `upload_file` 增加 `document_id`/`title`/`doc_type` 参数，透传给 `write_document`
- [x] 4.2 `backend/app/api/documents.py` `upload_document` 路由从 `Form` 读取可选 `document_id`/`title`/`doc_type`，传给 `upload_file`

## 5. 后端 — chunk 级 content hash 缓存

- [x] 5.1 `backend/app/rag/rag_engine.py` `ingest` 切分后对每个 chunk 计算 `content_hash = sha256(chunk.content)[:16]`
- [x] 5.2 `rag_engine.py` 批量查 PG：`SELECT content_hash, embedding FROM rag_chunks WHERE content_hash IN (...) AND embedding IS NOT NULL`，构建命中映射
- [x] 5.3 `rag_engine.py` 命中 chunk 复用已有 embedding（跳过 `embed_fn`），并校验 embedding 维度与 `settings.rag_milvus_dim` 一致，不一致视为未命中
- [x] 5.4 `backend/app/infra/hybrid.py` `index_chunks` 接收 `content_hashes` 参数，写入 rag_chunks 行的 `content_hash` 字段；命中缓存的 chunk 不传给 KG index_fn
- [x] 5.5 `rag_engine.py` 将命中/未命中标记与复用的 embeddings 传入 `index_chunks`

## 6. 前端 — 上传新版本

- [x] 6.1 `src/lib/api.ts` `uploadDocument` 增加可选 `{ documentId?, title?, docType? }` 参数，FormData 追加对应字段
- [x] 6.2 `src/components/upload-document-dialog.tsx` 支持"新版本模式"：接收 `documentId`/`defaultTitle`/`defaultDocType` props，预填标题与类型，上传时携带 documentId
- [x] 6.3 `src/components/document-detail.tsx` 版本历史区头部新增"上传新版本"按钮，点击打开新版本模式对话框，上传成功后刷新版本列表

## 7. 测试验证

- [x] 7.1 后端单测：`_extract_pdf_with_pdftotext` 用含 `\x0c` 的文本返回正确页数
- [x] 7.2 后端单测：`delete_versions_by_document` 清理 PG/ES/Milvus/KG 四路
- [x] 7.3 后端单测：`upload_file` 携带 document_id 时创建新版本（version+1）且入库前清旧
- [x] 7.4 后端单测：chunk content_hash 命中时跳过 embed_fn 调用
- [x] 7.5 前端验证：文档详情点击"上传新版本"→ 对话框预填 → 上传成功后版本历史刷新（代码已实现，待手动 UI 验证）
