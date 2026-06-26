## ADDED Requirements

### Requirement: Custom agents SHALL automatically receive memory_recall tool at runtime

All custom adapter agents MUST have the `memory_recall` tool available during execution, regardless of their configured `tool_names`.

#### Scenario: Custom agent without memory_recall in tool_names
- **WHEN** an agent with `adapterName="custom"` runs and its `tool_names` does not include `memory_recall`
- **THEN** the runtime automatically appends `memory_recall` to the resolved tool list
- **AND** logs an INFO message indicating the implicit injection

#### Scenario: Custom agent with memory_recall already in tool_names
- **WHEN** an agent with `adapterName="custom"` runs and its `tool_names` already includes `memory_recall`
- **THEN** no duplicate injection occurs
- **AND** the tool is resolved normally

#### Scenario: SDK agent is not affected
- **WHEN** an agent with `adapterName="claude-code"` or `adapterName="codex"` runs
- **THEN** `memory_recall` is NOT injected
- **AND** the agent uses only its SDK-provided tool set
