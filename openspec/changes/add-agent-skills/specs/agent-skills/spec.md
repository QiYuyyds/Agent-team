## ADDED Requirements

### Requirement: Skill 文件契约

一个 skill SHALL 是一个目录，根目录 MUST 含一个 `SKILL.md` 文件。`SKILL.md` MUST 以 YAML frontmatter 开头，且 frontmatter MUST 同时包含非空的 `name` 与 `description` 两个字段；frontmatter 之后是 Markdown 正文。skill 目录 MAY 含任意附带文件（脚本、模板、参考文档），系统对附带文件不做内容解析，仅原样存储。

#### Scenario: 合法 skill
- **WHEN** 一个目录根含 `SKILL.md`，其 frontmatter 含非空 `name` 和 `description`
- **THEN** 系统判定该 skill 合法并接受存储

#### Scenario: 缺少 SKILL.md
- **WHEN** 上传内容的根目录不含 `SKILL.md`
- **THEN** 系统拒绝，并返回「缺少 SKILL.md」的错误

#### Scenario: frontmatter 缺字段
- **WHEN** `SKILL.md` 的 frontmatter 缺少 `name` 或 `description`，或其值为空
- **THEN** 系统拒绝，并返回指明缺失字段的错误

### Requirement: 本地存储与命名

skill 内容 SHALL 存于本地磁盘 `<data_dir>/skills/<slug>/`，MUST NOT 写入数据库。`<slug>` SHALL 由 `SKILL.md` frontmatter 的 `name` 经 slugify 得到：转 kebab-case、移除前述 Windows 非法字符（`\ / : * ? " < > |`）与空白。当目标 `<slug>` 目录已存在时，系统 MUST 拒绝写入并提示该 skill 已存在，MUST NOT 静默覆盖或自动追加后缀。

#### Scenario: 由 name 生成目录
- **WHEN** 一个 skill 的 `name` 为 "PPT Builder"
- **THEN** 其内容被写入 `<data_dir>/skills/ppt-builder/`

#### Scenario: 重名拒绝
- **WHEN** 待写入的 `<slug>` 在 `<data_dir>/skills/` 下已存在
- **THEN** 系统拒绝写入并返回「skill 已存在」错误，不修改已存在目录

#### Scenario: 不入库
- **WHEN** 任一 skill 被存储
- **THEN** skill 的正文与附带文件只存在于文件系统，数据库中不出现 skill 内容记录

### Requirement: Skill Registry

系统 SHALL 提供 skill registry，扫描 `<data_dir>/skills/` 下每个含合法 `SKILL.md` 的目录，解析其 frontmatter，输出 `(slug, name, description)` 列表。registry MUST 跳过不含合法 `SKILL.md` 的目录而非报错。registry 是绑定选择与运行时注入的唯一 skill 来源。

#### Scenario: 列出可用 skill
- **WHEN** `<data_dir>/skills/` 下有 2 个合法 skill 目录和 1 个无 `SKILL.md` 的目录
- **THEN** registry 返回 2 个条目，每条含 slug、name、description

#### Scenario: 损坏目录被跳过
- **WHEN** 某子目录缺少合法 `SKILL.md`
- **THEN** registry 跳过该目录，其余 skill 仍正常列出

### Requirement: 通过上传创建 Skill

系统 SHALL 提供独立于知识库/RAG 的 skill 上传入口。该入口 SHALL 是**单一上传控件**，可接受单个 `SKILL.md` 文件、多个文件、或含 `SKILL.md` 及附带文件的整个文件夹（后端自行解析所传内容的结构）。无论投递形态，MUST 经过相同的文件契约校验与相同的命名/重名规则，并归一到相同的 `<data_dir>/skills/<slug>/` 落盘结构。上传入口旁 SHALL 提供搜索框，按 name / slug / description 过滤已上传的 skill。

#### Scenario: 上传单文件
- **WHEN** 用户通过该入口上传单个合法 `SKILL.md` 文件
- **THEN** 系统按其 `name` 创建 `<slug>` 目录，将该文件存为目录内的 `SKILL.md`

#### Scenario: 上传文件夹
- **WHEN** 用户通过该入口上传含 `SKILL.md` 与 `scripts/build.py` 的文件夹
- **THEN** 系统创建 `<slug>` 目录并按原相对路径保留 `SKILL.md` 与 `scripts/build.py`

#### Scenario: 搜索已上传 skill
- **WHEN** 用户在搜索框输入关键词
- **THEN** 列表只展示 name / slug / description 命中该关键词的 skill

#### Scenario: 与知识库隔离
- **WHEN** 用户通过 skill 入口上传内容
- **THEN** 该内容不进入 RAG 知识库、不触发文档 ingest，仅作为 skill 存储

### Requirement: 通过 Agent 工具创建 Skill

系统 SHALL 提供 `write_skill` 工具，供 agent 自建 skill。`write_skill` MUST 接受 skill 的 `name`、`description`、正文及可选附带文件，产出符合文件契约的 `SKILL.md`，并写入与上传相同的 `<data_dir>/skills/<slug>/`，遵守相同的命名与重名规则。`write_skill` SHALL 为 opt-in：仅当 agent 的 `tool_names` 显式包含它时才注入，MUST NOT 默认装备。

#### Scenario: agent 自建 skill
- **WHEN** 装备了 `write_skill` 的 agent 调用它并提供合法 name/description/正文
- **THEN** 系统在 `<data_dir>/skills/<slug>/` 写入 `SKILL.md`，此后该 skill 出现在 registry 列表中

#### Scenario: 默认不装备
- **WHEN** agent 的 `tool_names` 不含 `write_skill`
- **THEN** 该 agent 的运行上下文中不存在 `write_skill` 工具

#### Scenario: 自建重名拒绝
- **WHEN** agent 调用 `write_skill` 且目标 `<slug>` 已存在
- **THEN** 工具返回「skill 已存在」错误结果，不覆盖已存在目录

### Requirement: Agent 绑定 Skill

`Agent` 实体 SHALL 新增 `skill_names` 字段（字符串数组，默认空），记录该 agent 装备的 skill slug。绑定方式与 `tool_names` 一致：在创建/编辑 agent 时从 registry 列表中勾选。仅 custom adapter 的 agent SHALL 消费 `skill_names`；SDK adapter（claude-code / codex）的 agent 的 `skill_names` MUST 强制为空。

#### Scenario: custom agent 装备 skill
- **WHEN** 一个 custom agent 的 `skill_names` 含 `ppt-builder`
- **THEN** 该 agent 运行时可加载 `ppt-builder` skill

#### Scenario: SDK agent 不装备
- **WHEN** 创建或编辑 claude-code / codex adapter 的 agent
- **THEN** 其 `skill_names` 被强制保存为空数组

#### Scenario: 引用已删除 skill
- **WHEN** agent 的 `skill_names` 含一个在 registry 中已不存在的 slug
- **THEN** 运行时忽略该缺失 slug，其余 skill 正常注入，不报错中断

### Requirement: 渐进式披露与运行时注入

对装备了 skill 的 custom agent，custom adapter SHALL 在 system prompt 中仅注入选中 skill 的 `name + description`（元数据），MUST NOT 默认注入 `SKILL.md` 正文全文。系统 SHALL 提供 `load_skill(name)` 工具，agent 调用时按需读回对应 skill 的 `SKILL.md` 正文。skill 附带文件 SHALL 通过现有 `fs_read` / `bash` 工具按需访问，本变更不新增文件读取原语。

#### Scenario: 仅注入元数据
- **WHEN** 一个 custom agent 装备了 3 个 skill 并发起 run
- **THEN** system prompt 含这 3 个 skill 的 name+description，不含任一 skill 的正文全文

#### Scenario: 按需加载正文
- **WHEN** agent 调用 `load_skill('ppt-builder')`
- **THEN** 工具返回 `ppt-builder` 的 `SKILL.md` 正文

#### Scenario: 加载不存在的 skill
- **WHEN** agent 调用 `load_skill` 传入未装备或不存在的 name
- **THEN** 工具返回错误结果，说明该 skill 不可用

#### Scenario: 在输入框用 / 调用技能
- **WHEN** 用户在对话输入框输入 `/`
- **THEN** 斜杠命令浮层 SHALL 列出当前会话各 agent 已装备的 skill；选择某项后向输入框插入引导文本，使该 custom agent 在发送后 `load_skill` 并使用该技能

### Requirement: Skill 脚本执行安全

skill 携带的脚本 MUST NOT 在加载或上传时自动执行；其执行仅能经由 agent 显式调用 `bash` 发生。所有此类执行 SHALL 继续受现有平台命令黑名单（`getBannedPatterns`）与 workspace 沙箱（`assertPathWithinWorkspace` + effective cwd）约束，本变更 MUST NOT 放宽任何既有安全约束。

#### Scenario: 脚本不自动运行
- **WHEN** 一个含 `scripts/x.py` 的 skill 被上传或被 `load_skill` 加载
- **THEN** 系统不执行 `scripts/x.py`

#### Scenario: 执行仍受黑名单约束
- **WHEN** agent 试图通过 `bash` 运行命中命令黑名单的 skill 脚本命令
- **THEN** 该命令被黑名单拦截，与普通 `bash` 调用一致
