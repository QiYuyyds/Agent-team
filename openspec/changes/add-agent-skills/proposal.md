## Why

custom agent 当前的能力边界由 `tool_names` 静态决定，遇到「某类任务怎么做」的可复用流程（带步骤、约定、附带脚本/模板）无处安放：塞进 `system_prompt` 会常驻 context 且无法随任务复用，做成 tool 又只是单次函数调用、装不下流程与资源。Agent Skill（一个含 `SKILL.md` 的文件夹 + 可选附带文件，模型按需加载）正好补上这一层——把「可执行的操作流程 + 资源」打包成模型自主调用、渐进式披露的能力包。

## What Changes

- 新增 **agent-skills** capability：custom adapter 的 agent 可装备 skill，按 description 自主决定何时加载、按需读回 `SKILL.md` 正文与附带文件。
- skill 内容**落本地磁盘**（`<data_dir>/skills/<slug>/`），**不进数据库**；与现有文档/RAG 库相互独立。
- 三条来路归一到同一落盘结构：
  - ① 上传单个 `SKILL.md` 文件（后端按 frontmatter `name` 自动建文件夹）
  - ② 上传含 `SKILL.md` + script 的整个文件夹（前端 `webkitdirectory`）
  - ③ agent 用新工具 `write_skill` 自建（与现有 `rag_ingest` 同构）
- 左侧新增**独立「Skills」入口**（与「知识库」平级，不复用 RAG 上传路径）。
- `Agent` 新增 `skill_names`（JSONB）列记录绑定；`create-agent-dialog` 新增技能勾选区（复刻现有 `tool_names` 勾选交互）。
- 运行时 custom_adapter 注入选中 skill 的 `name + description`（仅元数据，渐进式披露），并装备 `load_skill(name)` 工具按需读回正文；附带 script 走现有 `fs_read` / `bash` 沙箱执行。
- 命名规则：读 `SKILL.md` frontmatter `name` → slugify 成 kebab-case 文件夹名；重名**拒绝并提示**。
- 安全：`write_skill` 为 **opt-in**（默认不注入，需在 agent 上显式勾选）；skill 携带的 script 不自动执行，仅在 `load_skill` 后经 `bash` 调用，且照常过双平台命令黑名单 + workspace 沙箱。
- **范围限定**：仅 custom adapter。SDK agent（claude-code / codex）本期不接入 skill（其 SDK 自带工具集与 context 管理，`skill_names` 强制为空，与现有 `tool_names` 强制 `[]` 一致）。

## Capabilities

### New Capabilities
- `agent-skills`: skill 的文件契约（`SKILL.md` frontmatter + 目录结构）、本地存储与命名/重名规则、skill registry（扫盘出 name+description）、三条来路（上传文件 / 上传文件夹 / agent `write_skill`）、`load_skill` 工具与渐进式披露、`Agent.skill_names` 绑定、custom adapter 注入路径、安全约束（opt-in + 沙箱复用）。

### Modified Capabilities
<!-- 无 spec 级 requirement 变更：tools / adapters / core-domain 的既有契约不修改，仅新增并列项；相关新增行为统一写入 agent-skills 新 capability。 -->

## Impact

- **DB schema**：`agents` 表新增 `skill_names` JSONB 列（默认 `[]`）；需迁移脚本 + `pnpm db:push`。影响 `specs/01-core-entities.md`（Agent 实体）与 `specs/08-db-schema.md`。
- **后端（Python FastAPI）**：新增 `app/services/skill_service.py`（落盘 + slugify + 重名校验 + registry 扫描）、`app/tools/skills.py`（`load_skill` / `write_skill`）、`app/api/skills.py`（上传/列出/删除）；`agent_runner.build_adapter_input` 注入 skill 元数据；`custom_adapter` tool loop 暴露 `load_skill`。
- **前端（Next.js/React）**：新增左侧「Skills」入口与上传组件（文件 + `webkitdirectory` 文件夹）；`create-agent-dialog.tsx` 新增技能勾选区；agent 类型新增 `skillNames`。
- **存储**：新增磁盘目录 `<data_dir>/skills/`（不纳入 workspace 配额；属应用级而非会话级数据）。
- **安全**：复用 `getBannedPatterns` 黑名单与 `assertPathWithinWorkspace` 沙箱，无新增安全原语；新增「agent 可写可执行 skill 脚本」信任边界，于 design 显式说明。
- **不影响**：StreamEvent 协议、MessagePart 结构、Artifact 生命周期、Orchestrator 调度路径均不变。
