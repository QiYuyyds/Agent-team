## 1. 数据模型与迁移

- [x] 1.1 `backend/app/db/models.py`：`Agent` 新增 `skill_names` JSONB 列（默认 `[]`），并加 `skill_names_list` property（复刻 `tool_names_list`）
- [x] 1.2 新增迁移脚本为 `agents` 表添加 `skill_names` 列，运行 `pnpm db:push` 验证
- [x] 1.3 同步 `specs/01-core-entities.md`（Agent 实体加 `skill_names`）与 `specs/08-db-schema.md`

## 2. Skill 存储与 Registry（后端核心）

- [x] 2.1 新建 `backend/app/services/skill_service.py`：定义 `<data_dir>/skills/` 根路径（取自 `config.data_dir`）
- [x] 2.2 实现 `parse_skill_md(text)`：解析 frontmatter，校验 `name` / `description` 非空，缺失则报错
- [x] 2.3 实现 `slugify(name)`：kebab-case + 清除 Windows 非法字符 `\ / : * ? " < > |` 与空白；空结果报错
- [x] 2.4 实现 `save_skill(files, ...)`：契约校验 → slugify → 重名检查（已存在则拒绝并提示）→ 按相对路径写入 `<slug>/`
- [x] 2.5 实现 `list_skills()`：扫描 skills 根，解析每个合法目录的 frontmatter，返回 `(slug, name, description)`；跳过损坏目录
- [x] 2.6 实现 `read_skill_body(slug)`：返回该 skill `SKILL.md` 的正文（去 frontmatter），缺失返回 not-found
- [x] 2.7 实现 `delete_skill(slug)`：删除磁盘目录
- [x] 2.8 为 skill_service 写单元测试（slugify / 契约校验 / 重名拒绝 / registry 扫描跳过损坏目录）

## 3. 工具：load_skill 与 write_skill

- [x] 3.1 新建 `backend/app/tools/skills.py`：`load_skill(name)` 工具，handler 调 `read_skill_body`，遵循 `ToolDef` 契约（zod/pydantic 校验、err/ok 包装）
- [x] 3.2 同文件实现 `write_skill(name, description, body, files?)` 工具，handler 组装 `SKILL.md` 并调 `save_skill`（重名返回 err）
- [x] 3.3 `backend/app/tools/registry.py` 注册 `load_skill` 与 `write_skill`
- [x] 3.4 确认 `write_skill` 为 opt-in：不进任何自动注入列表（对照 `web_search` 处理）

## 4. 运行时注入（agent_runner + custom_adapter）

- [x] 4.1 `agent_runner.execute_simple_run`：custom agent 时，若 `skill_names` 非空，按 registry 解析并对每个选中 slug 自动注入 `load_skill`（缺失 slug 跳过）
- [x] 4.2 `agent_runner.build_adapter_input`（`:1103`）：在 system prompt 追加「可用技能」块，仅含选中 skill 的 `name + description`（不含正文）
- [x] 4.3 确认 SDK agent（claude-code / codex）路径不消费 `skill_names`；create/update 时强制存空（仿 `tool_names` 强制 `[]`）
- [x] 4.4 验证渐进式披露：选中多 skill 时 prompt 只含元数据，正文仅经 `load_skill` 返回

## 5. 上传 API（后端）

- [x] 5.1 新建 `backend/app/api/skills.py`：`POST /skills/upload`（接收单文件或多文件带相对路径），调 `save_skill`
- [x] 5.2 `GET /skills`：返回 registry 列表（slug/name/description）
- [x] 5.3 `DELETE /skills/{slug}`：调 `delete_skill`
- [x] 5.4 在 `app/main.py` 挂载 skills router
- [x] 5.5 错误路径返回结构化提示（缺 SKILL.md / 缺字段 / 重名）

## 6. 前端：Skills 入口与上传

- [x] 6.1 新建 `src/components/skill-library.tsx`：左侧独立「Skills」入口（与知识库平级，不复用 RAG 上传路径）
- [x] 6.2 单一上传入口：点「上传技能」选多文件 + 拖入文件/文件夹（drop 用 webkitGetAsEntry 递归收集，带相对路径提交），后端自行解析结构
- [x] 6.3 列表展示已有 skill（name / description）+ 删除操作
- [x] 6.4 接入 `GET /skills` / `POST /skills/upload` / `DELETE /skills/{slug}`
- [x] 6.5 在 sidebar 注册「Skills」Tab/入口
- [x] 6.6 上传旁加搜索框，按 name/slug/description 过滤已上传 skill

## 7. 前端：Agent 技能勾选

- [x] 7.1 agent 前端类型新增 `skillNames: string[]`
- [x] 7.2 `create-agent-dialog.tsx`：新增独立「技能」Tab（与「工具与提示词」并列），内含技能勾选区，数据源为 `GET /skills`
- [x] 7.3 SDK agent 时禁用/清空技能勾选（仿 `toolNames: isSdkAgent ? [] : ...`）
- [x] 7.4 创建/编辑 agent 时将 `skillNames` 提交到后端并持久化
- [x] 7.5 `message-input.tsx`：输入 `/` 时在斜杠浮层列出会话 agent 已装备的 skill，选择后插入「使用技能 <slug>：」引导文本

## 8. 验证与文档

- [ ] 8.1 端到端：上传文件夹 skill → custom agent 勾选 → 对话中模型调 `load_skill` → 经 `bash` 跑附带脚本（确认过黑名单/沙箱）
- [x] 8.2 验证 `write_skill`：装备后 agent 自建 skill → 出现在 registry 与勾选列表
- [x] 8.3 验证重名拒绝（上传与 `write_skill` 两条路径）与缺字段拒绝
- [x] 8.4 `pnpm typecheck` 与 `pnpm lint` 通过；后端测试通过
- [x] 8.5 在 CLAUDE.md / OVERVIEW.md / `specs/07-tools.md` 补 skill 能力与 `load_skill` / `write_skill` 工具条目
