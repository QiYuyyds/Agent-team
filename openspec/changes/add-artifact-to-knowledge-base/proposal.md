## Why

产物库（Artifact）和知识库（RAG Document）目前是两个互不连通的系统：Agent 产出的报告/文档沉淀在某次会话的产物库里，无法被后续会话的知识检索复用。用户希望把有价值的产物「收进」知识库，让它成为可被 `rag_search` 检索的长期知识。

但「AI 产物自动回灌 RAG」存在已被研究刻画的 **检索坍缩（Retrieval Collapse）** 风险——合成内容主导语料、源多样性下降、且表面质量「假性健康」难以察觉（NAVER, ACM Web Conference 2026）。因此本变更采取最保守的切入：

1. **手动触发**——只有用户在产物库点击「加入知识库」才入库，天然过滤垃圾产物，杜绝自动污染。
2. **只入 `document` 类型**——它本身就是 markdown，与知识库现有 ingest 管道格式完全一致，零转换成本；其余类型（web_app/image/diagram/ppt/code_file/project）本期一律不入。
3. **来源可治理**——入库文档标记 `source='artifact_import'`，为日后「按来源筛选/降权未审 AI 内容」留出治理抓手。

## What Changes

### 1. 前端 — 产物库新增「加入知识库」入口（仅 document 类型）
- `artifact-library.tsx`：当 `artifact.type === 'document'` 时，产物项显示「加入知识库」按钮（复用现有删除按钮的 hover 操作区样式）
- 点击 → `fetchArtifact(id)` 取完整内容 → 调用新封装 `ingestArtifactToKnowledgeBase(artifact)`
- 成功 / 已存在 / 失败均给 toast 反馈
- 其余 7 种类型不显示按钮

### 2. 前端 — API 薄封装
- `lib/api.ts`：新增 `ingestArtifactToKnowledgeBase(artifact)`，内部调用现有 `createDocument()`，传：
  - `title: artifact.title`
  - `contentMd: artifact.content.content`（document 类型正文）
  - `docType: 'document'`
  - `source: 'artifact_import'`
  - `ingestToRag: true`
  - `metadata: { artifactId, conversationId }`

### 3. 后端 — 复用现有入库管道 + 防重复分支
- **不新增 API 端点**：复用 `POST /api/documents`（带 `ingestToRag: true`）这条已完整的「传内容 + 同步 ingest」链路
- `document_service.py` `write_document()`：当 `source === 'artifact_import'` 且 `metadata.artifactId` 存在时，先按 artifactId 查是否已导入过同一产物：
  - 已存在 → 不重复建文档，返回 `{ created: false, document, alreadyImported: true }`
  - 不存在 → 正常创建 + ingest

## Capabilities

### Modified Capabilities
- `document-knowledge-base`: 新增「从产物导入文档」入库路径与按 artifactId 的幂等防重复要求
- `artifacts`: 产物库新增「手动加入知识库」用户操作（仅 document 类型可用）

## Impact

- **前端**：`src/components/artifact-library.tsx`、`src/lib/api.ts`
- **后端**：`backend/app/services/document_service.py`（仅 `write_document` 加防重分支）
- **数据库**：无 schema 变更（artifactId 存入 `document_versions.metadata` 现有 JSON 列；防重查询基于 metadata）
- **范围限定**：仅 `document` 类型；web_app(html)/image/diagram/ppt/code_file/project 本期不支持
- **向后兼容**：纯增量，不改动现有产物/知识库行为；不影响已有 `source` 值（`agent_generated` / `user_upload`）
