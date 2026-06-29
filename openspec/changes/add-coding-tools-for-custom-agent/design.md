## Context

custom agent 走 AgentHub 自有工具表（`backend/app/tools/registry.py`），当前文件操作类工具只有 `fs_read` / `fs_write` / `fs_list` / `bash`。对照 Claude Code 的 6 大核心编程工具，缺失 `EditFile`（精确局部编辑）、`Grep`（正则搜索）、`Glob`（递归模式匹配）。

`local-code` 预设（`AGENT_TOOL_PRESETS`）的文案是"读写 workspace 并运行命令"，但实际装备的工具无法高效完成本地代码编辑任务：改 1 行要全量重写、搜代码要靠 `bash` 跑平台分叉命令、找文件只能列单个目录。

现有基础设施已经具备补齐条件：
- `fs_service.py` 提供 `assert_path_within_workspace` / `read_if_exists` / `get_workspace_for_conversation` 等沙箱 helper
- `fs_write.py` 已实现 `pending_writes.register` + `await_pending_decision` 的 review 流程
- 前端 `react-diff-viewer-continued` 已用于 `fs_write` 的 diff 展示，存的是 `old_content` / `new_content` 全文，自动算行级 diff
- `_scan_workspace_usage` 已有 `realpath-dedup` 防符号链接循环的策略

## Goals / Non-Goals

**Goals:**
- 让 `local-code` 预设的 custom agent 具备与 Claude Code 等价的本地代码编辑/搜索/定位能力
- 最大化复用现有基础设施（`pending_writes`、`react-diff-viewer`、workspace 沙箱）
- 无新二进制依赖（`fs_grep` / `fs_glob` 用 Python stdlib）
- 前端零新增组件（diff 复用、label 加三行）

**Non-Goals:**
- 不实现 `MultiEdit`（批量多文件编辑，Claude Code 有单独工具，可后续补）
- 不引入 `ripgrep` 二进制依赖（`fs_grep` 用 `re` + `pathlib`，workspace 场景性能可接受）
- 不改 SDK adapter（Claude Code / Codex 用各自 SDK 工具，不受影响）
- 不改已存在 agent 的 `toolNames`（已持久化，仅影响新建/重选预设的 agent）
- 不改 `fs_list` 的 API（保持"列单个目录"的简单语义，`fs_glob` 独立工具）

## Decisions

### 决策 1：`fs_edit` 复用 `pending_writes` review 流程，不新建审批流

`fs_edit` 的 handler 先读 `old_content`，在内存中应用 `old_string → new_string` 替换得到 `new_content`，然后走 `fs_write` 完全相同的 review 分支：`auto` 模式直接 `write_file_in_workspace`，`review` 模式 `pending_writes.register(old_content, new_content)`。

**为什么**：`pending_writes` 存的是 `old_content` 与 `new_content` 全文，前端 `react-diff-viewer` 自动算行级 diff。`fs_write` 全量重写时 diff 满屏红绿；`fs_edit` 局部替换时 diff 只高亮真正改的几行——同一个组件，体验天差地别，但前端零改动。

**备选**：新建独立的 `pending_edits` store + 新前端组件。被否决，因为复用成本远低于新建，且前端维护两套 diff 组件是负担。

### 决策 2：`fs_edit` 的 `old_string` 唯一性校验策略

handler 用 `str.count(old_string)` 检查出现次数：0 匹配返回 `err("old_string not found")`，>1 匹配返回 `err("old_string matches N locations; provide more context")`，=1 才执行替换。

**为什么**：与 Claude Code `Edit` 工具同策略。歧义替换会导致 LLM 意图之外的文件损坏，是核心安全点。

### 决策 3：`fs_grep` 用 Python stdlib，不引入 ripgrep

用 `re.compile(pattern)` + `pathlib.Path.rglob()` 逐文件逐行扫描，返回结构化 `{ file, line_number, line, match }`。

**为什么**：无新二进制依赖，跨平台无坑。workspace 场景通常 < 10k 文件，Python 性能可接受。

**备选**：可选检测 `rg` 是否存在，有则 `subprocess` 调，没有则回退 Python。被否决（YAGNI），首版不做，后续性能不达标再加。

### 决策 4：`fs_glob` 新建独立工具，不增强 `fs_list`

新建 `fs_glob({ pattern, path? })`，用 `pathlib.Path.glob(pattern)` 原生支持 `**/*.tsx`。

**为什么**：与 Claude Code `Glob` 命名对齐，LLM 迁移成本低；`fs_list` 保持"列单个目录"的简单语义不被污染；`pathlib.Path.glob()` 原生跨平台。

**备选**：给 `fs_list` 加 `pattern` + `recursive` 参数。被否决，因为 API 变复杂，LLM 要理解参数组合。

### 决策 5：三个工具都过 `assert_path_within_workspace`

**为什么**：与 `fs_read` / `fs_write` / `bash` 同等沙箱约束，复用现成 `fs_service` helper，路径逃逸统一拒绝。

## Risks / Trade-offs

- **`fs_grep` 性能**：Python 逐行扫描比 ripgrep 慢一个数量级 → 10s 超时 + 单文件 50 行命中上限 + 总结果默认 100 上限，避免 LLM context 爆炸和长耗时阻塞。
- **`fs_edit` 大文件**：`read_if_exists` 有 1MB 上限，超了返回 None → handler 友好报错"file too large for edit (max 1 MB); use fs_write for full rewrite"，引导 LLM 回退到 `fs_write`。
- **`fs_glob` 符号链接循环**：复用 `_scan_workspace_usage` 的 `realpath-dedup` 策略，`visited` 集合记录已访问 `os.path.realpath`，重复即跳过。
- **`local-code` 预设变更的影响面**：已存在 custom agent 的 `toolNames` 已持久化在 DB，不受预设变更影响；仅新建 agent 或用户重新点选 `local-code` 预设时才装备新工具。这是预期行为，非风险。
- **`fs_edit` 不支持多文件批量编辑**：Claude Code 有 `MultiEdit` 工具，本变更不实现 → 如果后续有需求，按相同模式新增 `fs_multiedit` 工具，接收 `edits: [{old_string, new_string}]` 数组，逐个校验唯一性后串行应用。
