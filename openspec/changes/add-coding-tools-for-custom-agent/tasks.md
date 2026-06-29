## 1. fs_glob 工具实现（Phase 1 - 最简单，纯只读）

- [x] 1.1 新建 `backend/app/tools/fs_glob.py`，实现 `fs_glob({ pattern, path? })`，用 `pathlib.Path.glob()` 支持 `**/*.tsx` 递归匹配，返回 `{ files: [{ path, is_directory, size }], truncated }`
- [x] 1.2 实现沙箱校验（`assert_path_within_workspace`）、结果上限 200、符号链接循环防护（复用 `_scan_workspace_usage` 的 realpath-dedup 策略）
- [x] 1.3 在 `backend/app/tools/registry.py` 的 `_build_registry()` 注册 `fs_glob_tool`
- [x] 1.4 新建 `backend/tests/test_fs_glob.py`，覆盖：`**/*.tsx` 匹配、结果上限截断、符号链接循环不挂、沙箱逃逸拒、`path` 子路径 scope

## 2. fs_grep 工具实现（Phase 2 - 纯只读，有性能考量）

- [x] 2.1 新建 `backend/app/tools/fs_grep.py`，实现 `fs_grep({ pattern, path?, glob?, max_results? })`，用 `re.compile()` + `pathlib.Path.rglob()` 逐文件逐行扫描，返回 `{ matches: [{ file, line_number, line, match }], total_matches, truncated }`
- [x] 2.2 实现二进制文件跳过（`\x00` 字节检测）、`node_modules`/`.git` 目录跳过、单文件 50 行命中上限、总结果默认 100 上限、10s 超时保护
- [x] 2.3 在 `backend/app/tools/registry.py` 的 `_build_registry()` 注册 `fs_grep_tool`
- [x] 2.4 新建 `backend/tests/test_fs_grep.py`，覆盖：正则搜索结构化返回、二进制文件跳过、依赖目录跳过、结果截断 `truncated` 标志、超时返回部分结果、沙箱逃逸拒

## 3. fs_edit 工具实现（Phase 3 - 复用 pending_writes，收益最大）

- [x] 3.1 新建 `backend/app/tools/fs_edit.py`，实现 `fs_edit({ path, old_string, new_string })`，handler 先 `read_if_exists` 读 `old_content`
- [x] 3.2 实现 `old_string` 唯一性校验：`str.count(old_string)` 为 0 返回 `err("old_string not found")`，>1 返回 `err("old_string matches N locations; provide more context")`，=1 执行 `old_content.replace(old_string, new_string)` 得到 `new_content`
- [x] 3.3 复用 `fs_write.py` 的 review 分支逻辑：`auto` 模式直接 `write_file_in_workspace`，`review` 模式 `pending_writes.register(old_content, new_content)` + `await_pending_decision`（前端 `react-diff-viewer` 自动只高亮改的行）
- [x] 3.4 实现大文件保护：`read_if_exists` 返回 None（文件 > 1MB）时返回 `err("file too large for edit (max 1 MB); use fs_write for full rewrite")`
- [x] 3.5 在 `backend/app/tools/registry.py` 的 `_build_registry()` 注册 `fs_edit_tool`
- [x] 3.6 新建 `backend/tests/test_fs_edit.py`，覆盖：唯一匹配替换成功、0 匹配拒、多匹配拒、review 模式 pending write 注册、大文件拒、沙箱逃逸拒、run abort 取消

## 4. 前端配置同步

- [x] 4.1 在 `src/shared/agent-builder-config.ts` 的 `AVAILABLE_AGENT_TOOLS` 加入 `fs_edit`、`fs_grep`、`fs_glob`
- [x] 4.2 在 `AGENT_TOOL_META` 加入三个工具的 `label` 和 `desc`（fs_edit→编辑文件、fs_grep→搜索文本、fs_glob→查找文件）
- [x] 4.3 在 `AGENT_TOOL_PRESETS` 的 `local-code` 预设 `tools` 数组加入 `fs_edit`、`fs_grep`、`fs_glob`
- [x] 4.4 在 `src/lib/tool-display.ts` 的 `AGENTHUB_TOOL_LABELS` 加入 `fs_edit: '编辑文件'`、`fs_grep: '搜索文本'`、`fs_glob: '查找文件'`

## 5. 规格文档同步

- [x] 5.1 在 `specs/07-tools.md` 的内置工具清单表加入 `fs_edit`、`fs_grep`、`fs_glob` 三行（名称/用途/副作用/谁该装备）
- [x] 5.2 在 `specs/07-tools.md` 新增 `### fs_edit`、`### fs_grep`、`### fs_glob` 三节详细说明（参数、限制、返回值、与 Claude Code 对应工具的对照）

## 6. 端到端验证

- [x] 6.1 启动后端，创建选 `local-code` 预设的 custom agent，确认三个工具出现在装备列表且可被 LLM 调用
- [x] 6.2 验证 `fs_edit` 在 review 模式下前端 `PendingWriteApprovalDialog` 的 diff 只高亮真正改的行（与 `fs_write` 全量重写对比）
- [x] 6.3 验证 `fs_grep` 搜代码符号返回结构化 `{ file, line_number, line, match }`，二进制和 `node_modules` 被跳过
- [x] 6.4 验证 `fs_glob` 用 `**/*.tsx` 模式递归匹配 workspace 内所有 tsx 文件
- [x] 6.5 验证三个工具的路径逃逸（`../../.ssh/id_rsa`）均被 `assert_path_within_workspace` 拒绝
