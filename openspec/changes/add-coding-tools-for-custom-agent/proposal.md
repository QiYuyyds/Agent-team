## Why

custom agent 的 `local-code` 预设缺失 Claude Code 的 3 大核心编程原语：精确局部编辑（EditFile）、正则文本搜索（Grep）、递归模式匹配（Glob）。当前 custom agent 改文件只能 `fs_read` 全读 → `fs_write` 全量重写（token 浪费、diff 噪音、易丢内容）；搜代码只能靠 `bash` 跑平台分叉的 `Select-String`/`grep`；找文件只能列单个目录。这让本应面向"本地代码"场景的 `local-code` 预设在能力上明显弱于 Claude Code agent。补齐这 3 个工具后，custom agent 在本地代码场景可与 Claude Code agent 功能对等。

## What Changes

- 新增 `fs_edit({ path, old_string, new_string })` 工具：精确局部替换，`old_string` 唯一性校验（0 匹配拒、>1 匹配拒、=1 执行），复用现有 `pending_writes` review 流程与前端 `react-diff-viewer`（前端零改动，diff 自动只高亮真正改的行）。
- 新增 `fs_grep({ pattern, path?, glob?, max_results? })` 工具：正则文本搜索，返回结构化 `{ file, line_number, line, match }`，纯 Python stdlib（`re` + `pathlib`）实现，无新二进制依赖，跳过二进制文件与 `node_modules`/`.git`。
- 新增 `fs_glob({ pattern, path? })` 工具：递归模式匹配，用 `pathlib.Path.glob()` 支持 `**/*.tsx`，返回 `{ files: [{ path, is_directory, size }] }`。
- **BREAKING**（预设层面）：`AGENT_TOOL_PRESETS` 的 `local-code` 预设强制加入 `fs_edit`、`fs_grep`、`fs_glob`，使该预设真正具备本地代码编辑能力。已存在的 custom agent 不受影响（其 `toolNames` 已持久化），仅影响新建/重新选预设的 agent。
- `AVAILABLE_AGENT_TOOLS` / `AGENT_TOOL_META` 加入 3 个工具，UI 创建/编辑 Agent 弹窗出现勾选项。
- `tool-display.ts` 的 `AGENTHUB_TOOL_LABELS` 加 `fs_edit→编辑文件`、`fs_grep→搜索文本`、`fs_glob→查找文件` 3 行。
- `registry.py` 注册 3 个工具。
- `specs/07-tools.md` 内置工具清单加 3 行 + 各自详细小节。

## Capabilities

### New Capabilities

无。所有变更都是增强现有 `tools` 与 `agent-builder` 两个 capability 的 requirements。

### Modified Capabilities

- `tools`: 新增 3 个工具的行为要求——`fs_edit` 的 `old_string` 唯一性校验与 review 复用、`fs_grep` 的结构化返回与二进制跳过、`fs_glob` 的递归模式匹配与结果上限；同时把 `fs_edit`/`fs_grep`/`fs_glob` 纳入"File tools SHALL enforce workspace boundaries"要求（与 `fs_read`/`fs_write`/`bash` 同等沙箱约束）。
- `agent-builder`: `local-code` 预设场景加入 `fs_edit`、`fs_grep`、`fs_glob`，使该预设的 custom agent 具备与 Claude Code 等价的本地代码编辑/搜索/定位能力。

## Impact

- **后端**：`backend/app/tools/` 新增 `fs_edit.py`、`fs_grep.py`、`fs_glob.py`；`backend/app/tools/registry.py` 注册 3 个工具；`backend/app/services/fs_service.py` 可选扩展 `replace_in_file` / `search_files` / `glob_files` helper（也可内联在工具文件里）。
- **前端**：`src/shared/agent-builder-config.ts` 的 `AVAILABLE_AGENT_TOOLS`、`AGENT_TOOL_META`、`AGENT_TOOL_PRESETS.local-code` 三处改动；`src/lib/tool-display.ts` 的 `AGENTHUB_TOOL_LABELS` 加 3 行。
- **规格文档**：`specs/07-tools.md` 内置工具清单表加 3 行 + 新增 `### fs_edit` / `### fs_grep` / `### fs_glob` 三节。
- **测试**：`backend/tests/` 新增 `test_fs_edit.py`、`test_fs_grep.py`、`test_fs_glob.py`，覆盖 happy path、沙箱逃逸拒、唯一性校验、二进制跳过、结果截断。
- **依赖**：无新依赖。`fs_grep` / `fs_glob` 用 Python stdlib（`re` + `pathlib`）；`fs_edit` 复用现有 `pending_writes` / `react-diff-viewer-continued`。
- **兼容性**：已存在的 custom agent 的 `toolNames` 已持久化，不受预设变更影响；新工具仅对显式勾选或选 `local-code` 预设的新 agent 生效。
