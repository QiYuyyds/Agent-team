## MODIFIED Requirements

### Requirement: Custom agents SHALL provide tool presets

The agent builder MUST provide one-click tool presets for common custom-agent roles, including all-purpose, local-code, artifact, and review workflows. The `local-code` preset MUST include the full set of local code-editing primitives (`fs_read`, `fs_write`, `fs_edit`, `fs_grep`, `fs_glob`, `bash`) so that custom agents match Claude Code agent capabilities in local code scenarios.

#### Scenario: User selects local-code preset
- **WHEN** the user clicks the local-code tool preset
- **THEN** the selected tools include `deploy_workspace`, `read_artifact`, `fs_read`, `fs_write`, `fs_edit`, `fs_grep`, `fs_glob`, and `bash`
- **AND** artifact creation tools are not selected unless the user adds them manually.

#### Scenario: User creates a custom agent
- **WHEN** the create dialog opens for a Custom adapter agent
- **THEN** the default preset is all-purpose
- **AND** both artifact tools and local workspace file/command tools are selected.
