## ADDED Requirements

### Requirement: 知识库 SHALL 支持从产物（Artifact）手动导入文档

系统 MUST 支持把 `document` 类型的产物作为内容，通过现有 `POST /api/documents`（`ingestToRag: true`）入库为知识库文档，无需新增 REST 端点。导入产生的文档 MUST 标记 `source = 'artifact_import'`，且其版本 metadata MUST 携带来源 `artifactId`（以及 `conversationId`）。导入仅限 `document` 类型产物；`web_app`、`image`、`diagram`、`ppt`、`code_file`、`project` 类型 MUST NOT 通过此路径入库。

#### Scenario: document 产物导入知识库
- **WHEN** 用户对一个 `type='document'` 的产物触发「加入知识库」
- **THEN** 系统以该产物正文（markdown）创建一个新 Document（`source='artifact_import'`）
- **AND** 该文档版本被 ingest 到 RAG（切块 / embedding / 索引）
- **AND** 版本 metadata 含 `artifactId` 与 `conversationId`
- **AND** 之后的 `rag_search` 可检索到该内容

#### Scenario: 非 document 类型不可导入
- **WHEN** 导入请求的来源产物类型不是 `document`
- **THEN** 系统 MUST 拒绝该导入（前端不暴露入口，后端校验内容格式）
- **AND** 不创建任何文档、不产生任何 RAG chunk

#### Scenario: 产物正文格式校验
- **WHEN** 待导入产物的内容 `format` 不是 `markdown` 或正文为空
- **THEN** 系统 MUST 抛出明确错误，而非创建空文档

### Requirement: 产物导入 SHALL 按 artifactId 幂等防重复

当 `write_document` 收到 `source = 'artifact_import'` 且 metadata 含 `artifactId` 时，系统 MUST 先检查是否已存在来自同一 `artifactId` 的 active 文档；已存在则 MUST NOT 重复创建文档或重复 ingest。

#### Scenario: 同一产物重复导入
- **WHEN** 用户对同一 `artifactId` 的产物第二次触发「加入知识库」
- **THEN** 系统返回已存在的文档并标记 `alreadyImported = true`
- **AND** 不新增 Document、不新增 RagChunk

#### Scenario: 不同产物分别导入
- **WHEN** 两个不同 `artifactId` 的 document 产物先后导入
- **THEN** 系统分别创建两个独立的 Document 并各自 ingest
