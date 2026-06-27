## 1. 后端 — write_document 防重复分支

- [x] 1.1 `services/document_service.py`: `write_document()` 中，当 `source == 'artifact_import'` 且 `metadata` 含 `artifactId` 时，经 `_find_imported_artifact()` 查 `document_versions.metadata->>'artifactId'` 是否已有 active 文档
- [x] 1.2 命中已存在 → 返回 `{ created: False, already_imported: True, ingest: None }`，不重复 ingest
- [x] 1.3 未命中 → 走原有创建 + ingest 流程，`artifactId` 经 metadata 落入 version
- [ ] 1.4 编写测试：同一 artifactId 调两次，第二次返回 alreadyImported 且不新增 RagChunk

## 2. 后端 — schema / route 透传 alreadyImported

- [x] 2.1 `schemas/document.py`: `WriteDocumentResponse` 加 `already_imported`（alias `alreadyImported`）
- [x] 2.2 `api/documents.py`: 路由透传 `already_imported`

## 3. 前端 — API 薄封装

- [x] 3.1 `lib/api.ts`: 新增 `ingestArtifactToKnowledgeBase(artifact)`，映射 title / contentMd / docType='document' / source='artifact_import' / ingestToRag=true / metadata={ artifactId, conversationId }
- [x] 3.2 封装层校验 `content.type==='document'` 且 `format==='markdown'` 且正文非空，否则抛出明确错误
- [x] 3.3 复用现有 `createDocument()`，透传返回值（含 alreadyImported 标志）；`shared/types.ts` 加 `alreadyImported?`

## 4. 前端 — 产物库按钮

- [x] 4.1 `components/artifact-library.tsx`: 仅当 `latest.type === 'document'` 时渲染 `IngestButton`（BookPlus 图标）
- [x] 4.2 点击 → 按需 `fetchArtifact(id)` 取完整内容 → 调 `ingestArtifactToKnowledgeBase()`
- [x] 4.3 按钮内联状态反馈：loading→spinner / done·exists→绿色 Check / error→红色（无 toast 库，用内联态）
- [x] 4.4 loading 态 disabled，防重复点击

## 5. 验证

- [x] 5.1 确认仅 document 类型出现按钮（其余类型无入口）
- [x] 5.2 `pnpm typecheck` 通过
- [x] 5.3 `pnpm lint` 通过（0 errors；3 个 warning 为预存、与本改动无关）
- [ ] 5.4 端到端验证：会话产出 document 产物 → 产物库点击加入 → 新会话开 RAG → `rag_search` 能检索到该内容
- [ ] 5.5 验证重复点击幂等（知识库不出现两份）
