## MODIFIED Requirements

### Requirement: Parser 管道 SHALL 三级降级解析 PDF 并检测 OCR 需求

系统 MUST 实现 `parse_bytes(filename, content_type, data)` 函数，返回 `ParseResult`（filename, content_type, parser, content, pages, text_chars, needs_ocr）。PDF 解析按精度依次尝试 pdfplumber → PyPDF2 → pdftotext；非 PDF 走编码检测（UTF-8 → GBK → Latin-1）+ 文本规范化（修复 \r\n、去 \x00、修复断行连字符、压缩空行）。pdftotext 分支 MUST 通过统计输出中 `\x0c`（form feed）分隔符出现次数 +1 得到真实页数，不再硬编码为 0。当 PDF 的 text_chars < 80 且 pages > 0 时，needs_ocr MUST 置为 true。

#### Scenario: pdfplumber 成功解析 PDF
- **WHEN** parse_bytes 收到一个 PDF 文件且 pdfplumber 可用
- **THEN** parser 字段为 "pdfplumber"
- **AND** content 为提取的文本，pages 为页数，text_chars 为字符数，needs_ocr 为 false

#### Scenario: pdfplumber 缺失时降级到 PyPDF2
- **WHEN** pdfplumber 不可用但 PyPDF2 可用
- **THEN** 使用 PyPDF2 解析，parser 字段为 "pdf_text"
- **AND** pages 为 len(reader.pages)

#### Scenario: pdftotext 降级解析返回正确页数
- **WHEN** pdfplumber 和 PyPDF2 均不可用但 pdftotext 可用
- **THEN** parser 字段为 "pdftotext"
- **AND** pages 为输出文本中 `\x0c` 出现次数 +1（不再为 0）
- **AND** content 为提取的文本，text_chars 为字符数

#### Scenario: 扫描件 PDF 触发 OCR 需求检测
- **WHEN** PDF 解析后 text_chars < 80 且 pages > 0
- **THEN** needs_ocr 置为 true
- **AND** content 为提取到的少量文本

#### Scenario: 非 PDF 文件编码检测
- **WHEN** parse_bytes 收到一个 .md 文件（UTF-8 编码）
- **THEN** parser 字段为 "plain_text"
- **AND** content 为解码并规范化后的文本，pages 为 0

#### Scenario: GBK 编码文本文件降级解码
- **WHEN** parse_bytes 收到一个 GBK 编码的 .txt 文件
- **THEN** UTF-8 解码失败后尝试 GBK 成功
- **AND** content 为正确解码的文本

### Requirement: 上传文件 SHALL 一条龙完成解析建文档入库

`POST /api/documents/upload` 接收 multipart/form-data（字段 file，可选字段 document_id / title / doc_type），MUST 依次执行：parse_bytes → 判断 needs_ocr → write_document → ingest_to_rag=true。若 needs_ocr=true 则提前返回 success=false 且不建文档。当请求携带非空 `document_id` 时，MUST 透传给 `write_document`，为已有文档创建新版本而非新建文档；未携带或为空时新建文档。`title` 与 `doc_type` 非空时 MUST 透传覆盖默认值。

#### Scenario: 上传 PDF 一条龙成功
- **WHEN** POST /api/documents/upload 收到一个 PDF 文件且未携带 document_id
- **AND** 解析成功且 needs_ocr=false
- **THEN** 创建 Document + Version（source='user_upload'）
- **AND** 自动入库 RAG 并回填溯源字段
- **THEN** 返回 `{ filename, content_type, parser, pages, text_chars, needs_ocr: false, chunk_count, doc_hash, document, version, success: true }`

#### Scenario: 上传新版本到已有文档
- **WHEN** POST /api/documents/upload 携带 document_id 指向一个已存在的文档
- **AND** 解析成功且 needs_ocr=false
- **THEN** 不新建文档，而为该文档创建新 Version（version = 当前最大 version + 1）
- **AND** 更新 documents.latest_version 和 latest_version_id 指向新版本
- **AND** 入库前先清理该文档所有旧版本的 RAG 数据
- **THEN** 返回的 document.id 与传入的 document_id 一致，version.version 为新版本号

#### Scenario: 上传携带 title 和 doc_type 覆盖默认值
- **WHEN** 上传时携带非空 title 和 doc_type 表单字段
- **THEN** write_document 使用传入的 title 和 doc_type
- **AND** 不使用从文件名推导的默认标题

#### Scenario: 上传扫描件 PDF 需 OCR
- **WHEN** 上传的 PDF 解析后 needs_ocr=true
- **THEN** 不创建文档，不入库
- **AND** 返回 `{ filename, needs_ocr: true, pages, text_chars, chunk_count: 0, message: "PDF 文本抽取结果过少，可能是扫描件，需要 OCR 后再入库", success: false }`

## ADDED Requirements

### Requirement: 文档版本更新 SHALL 先清理旧版本 RAG 数据再入库

DocumentService MUST 提供 `delete_versions_by_document(document_id)` 方法：按 `rag_chunks.document_id` 一次性查询该文档所有版本的 pg_ids 与 doc_hashes 集合，批量删除 PG 行、按 pg_ids 删除 ES 索引与 Milvus 向量、按 doc_hash 集合删除 Neo4j 知识图谱节点。`_ingest_content` 在调用 `RAGEngine.ingest` 入库新内容前 MUST 先调用 `delete_versions_by_document(document_id)` 清理旧数据，保证同一文档在 RAG 中只保留当前版本的数据。`ingest_version`（重入库指定版本）MUST 同样先清旧再入新。

#### Scenario: 上传新版本前清理旧版本四路数据
- **WHEN** 为已有文档入库一个新版本
- **THEN** 入库前该文档所有旧版本的 rag_chunks 行被删除
- **AND** ES 中对应 pg_ids 的索引被删除
- **AND** Milvus 中对应 pg_ids 的向量被删除
- **AND** Neo4j 中对应 doc_hashes 的知识图谱节点被删除

#### Scenario: 清旧后入库新版本只保留当前数据
- **WHEN** 新版本入库完成
- **THEN** rag_chunks 中该 document_id 的行全部关联新 version_id
- **AND** 检索不会同时命中新旧版本内容

#### Scenario: 重入库指定版本同样先清旧
- **WHEN** 调用 ingest_version(document_id, version_id) 对某版本重入库
- **THEN** 入库前先清理该 document_id 的所有旧 RAG 数据
- **AND** 再入库指定版本内容

#### Scenario: 文档无旧 RAG 数据时清理为空操作
- **WHEN** 对一个从未入库的文档调用 delete_versions_by_document
- **THEN** 返回删除数 0，不报错

### Requirement: RAG 入库 SHALL 支持 chunk 级 content hash 缓存

`rag_chunks` 表 MUST 新增 `content_hash VARCHAR(16)` 字段（可空，加普通索引）。`RAGEngine.ingest` 切分后 MUST 对每个 chunk 计算 `content_hash = sha256(chunk.content)[:16]`，并批量查询 PG 中已存在相同 content_hash 且 embedding 非空的行。命中的 chunk MUST 复用已有 embedding 向量（跳过 `embed_fn` 调用），且在 `index_chunks` 时不传给 KG index_fn（相同内容实体已抽取过）；未命中的 chunk 正常调用 `embed_fn` 与 KG 抽取。所有 chunk 仍 MUST 写入新 PG 行、Milvus insert、ES index 以关联新 version_id。缓存命中时 MUST 校验已有 embedding 维度与 `settings.rag_milvus_dim` 一致，不一致则视为未命中重新生成。

#### Scenario: 未变化 chunk 命中缓存跳过 embedding
- **WHEN** 新版本某 chunk 的 content_hash 与 PG 已有行匹配且 embedding 维度一致
- **THEN** 该 chunk 不调用 embed_fn
- **AND** 复用已有 embedding 向量写入新 rag_chunks 行
- **AND** 该 chunk 不触发 KG LLM 实体抽取

#### Scenario: 新增 chunk 未命中缓存正常处理
- **WHEN** 新版本某 chunk 的 content_hash 在 PG 中不存在
- **THEN** 该 chunk 正常调用 embed_fn 生成向量
- **AND** 正常触发 KG LLM 实体抽取

#### Scenario: embedding 维度不匹配视为未命中
- **WHEN** 命中的已有 embedding 维度与 settings.rag_milvus_dim 不一致
- **THEN** 视为未命中，重新调用 embed_fn 生成向量

#### Scenario: 历史数据 content_hash 为空不影响检索
- **WHEN** rag_chunks 历史行的 content_hash 为 NULL
- **THEN** 检索行为不受影响
- **AND** 下次该 chunk 重入库时自动填充 content_hash

### Requirement: 文档详情 SHALL 支持上传新版本

前端文档详情视图（DocumentDetail）的版本历史区 MUST 新增"上传新版本"按钮。点击后 MUST 打开上传对话框（UploadDocumentDialog），以"新版本模式"运行：标题与类型预填为当前文档的值并允许修改，文件选择后调用 `uploadDocument(file, { documentId })` 携带当前文档 ID。上传成功后 MUST 刷新版本历史列表，新版本出现在列表顶部并标记为"最新"。

#### Scenario: 点击上传新版本打开对话框
- **WHEN** 用户在文档详情页点击"上传新版本"按钮
- **THEN** 打开上传对话框
- **AND** 标题预填为当前文档标题，类型预填为当前文档 doc_type

#### Scenario: 上传新版本携带 documentId
- **WHEN** 用户在"新版本模式"对话框中选择文件并上传
- **THEN** 调用 uploadDocument 时携带当前文档的 documentId
- **AND** 请求 POST /api/documents/upload 的表单包含 document_id 字段

#### Scenario: 上传成功后刷新版本历史
- **WHEN** 新版本上传成功
- **THEN** 版本历史列表刷新
- **AND** 新版本出现在列表顶部且标记为"最新"
- **AND** 旧版本保留在列表中
