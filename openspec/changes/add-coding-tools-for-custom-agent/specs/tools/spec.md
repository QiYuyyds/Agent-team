## MODIFIED Requirements

### Requirement: File tools SHALL enforce workspace boundaries

`fs_read`, `fs_write`, `fs_edit`, `fs_grep`, `fs_glob`, and `bash` MUST resolve paths under the conversation effective cwd and reject access outside that tree. File search tools (`fs_grep`, `fs_glob`) MUST scope both their search root and their result paths to the workspace subtree.

#### Scenario: Agent attempts path traversal
- **WHEN** a tool receives `../../.ssh/id_rsa`
- **THEN** the path check rejects the operation.

#### Scenario: fs_glob searches outside workspace
- **WHEN** `fs_glob` receives a `path` argument resolving outside the workspace
- **THEN** the tool rejects the operation before scanning.

#### Scenario: fs_grep searches outside workspace
- **WHEN** `fs_grep` receives a `path` argument resolving outside the workspace
- **THEN** the tool rejects the operation before scanning.

## ADDED Requirements

### Requirement: fs_edit SHALL perform unique string replacement

AChat MUST provide an `fs_edit` tool that accepts `path`, `old_string`, and `new_string`, and performs a single precise in-place replacement. The tool MUST verify that `old_string` appears exactly once in the file; zero matches SHALL return an error indicating the string was not found, and multiple matches SHALL return an error asking for more context. In review mode, `fs_edit` MUST reuse the existing pending-write approval flow so the user sees a diff scoped to the actually changed lines.

#### Scenario: Agent edits a unique line
- **WHEN** `fs_edit` receives `path`, `old_string`, and `new_string` where `old_string` appears exactly once
- **THEN** the tool replaces `old_string` with `new_string` in the file
- **AND** returns the path and byte count of the result.

#### Scenario: old_string not found
- **WHEN** `fs_edit` receives an `old_string` that does not appear in the file
- **THEN** the tool returns an error indicating the string was not found
- **AND** does not modify the file.

#### Scenario: old_string matches multiple locations
- **WHEN** `fs_edit` receives an `old_string` that appears more than once
- **THEN** the tool returns an error asking the agent to provide more surrounding context
- **AND** does not modify the file.

#### Scenario: fs_edit in review mode
- **WHEN** `fs_edit` is called in review mode with a valid unique `old_string`
- **THEN** AChat records a pending write with the old and new full content
- **AND** the user approval dialog shows a diff highlighting only the changed lines
- **AND** the tool waits for explicit user approval before writing.

#### Scenario: fs_edit on a large file
- **WHEN** `fs_edit` targets a file exceeding the read size limit
- **THEN** the tool returns an error guiding the agent to use `fs_write` for a full rewrite.

### Requirement: fs_grep SHALL return structured search results

AChat MUST provide an `fs_grep` tool that accepts a `pattern` (regular expression), an optional `path` search root, an optional `glob` file filter, and an optional `max_results` cap. The tool MUST return structured matches as `{ file, line_number, line, match }` entries. The tool MUST skip binary files (detected via null bytes), skip dependency directories such as `node_modules` and `.git`, enforce a per-file match cap, enforce a total result cap, and enforce a search timeout.

#### Scenario: Agent searches for a symbol
- **WHEN** `fs_grep` receives `pattern="useState"` with a valid workspace path
- **THEN** the tool returns a list of matches each with `file`, `line_number`, `line`, and `match` fields
- **AND** truncates results at the configured `max_results` cap.

#### Scenario: fs_grep skips binary files
- **WHEN** `fs_grep` encounters a file containing null bytes
- **THEN** the tool skips that file without returning matches or errors.

#### Scenario: fs_grep skips dependency directories
- **WHEN** `fs_grep` scans a workspace containing `node_modules` or `.git`
- **THEN** the tool does not descend into those directories.

#### Scenario: fs_grep exceeds total result cap
- **WHEN** the number of matches exceeds the default or specified `max_results`
- **THEN** the tool returns only the first `max_results` matches
- **AND** includes a `truncated` flag in the result.

#### Scenario: fs_grep times out
- **WHEN** the search exceeds the timeout threshold
- **THEN** the tool returns the matches found so far with a timeout note
- **AND** does not block the agent run indefinitely.

### Requirement: fs_glob SHALL support recursive pattern matching

AChat MUST provide an `fs_glob` tool that accepts a `pattern` (supporting `**/*.ext` recursive globs) and an optional `path` search root. The tool MUST return matching file entries as `{ path, is_directory, size }` using cross-platform path semantics, guard against symlink cycles via realpath deduplication, and enforce a result cap to protect the agent context.

#### Scenario: Agent finds all TypeScript files
- **WHEN** `fs_glob` receives `pattern="**/*.tsx"`
- **THEN** the tool returns all matching files under the workspace
- **AND** each entry includes `path`, `is_directory=false`, and `size`.

#### Scenario: fs_glob respects result cap
- **WHEN** the number of matching files exceeds the default cap
- **THEN** the tool returns only the first batch
- **AND** includes a `truncated` flag in the result.

#### Scenario: fs_glob handles symlink cycle
- **WHEN** the workspace contains a symlink cycle
- **THEN** the tool deduplicates by realpath and returns without hanging.

#### Scenario: fs_glob scopes to subpath
- **WHEN** `fs_glob` receives `path="src"` and `pattern="**/*.ts"`
- **THEN** the tool returns only matches under the `src` subdirectory.
