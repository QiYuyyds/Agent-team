# Agent Builder Delta

## MODIFIED Requirements

### Requirement: Agent create/edit form SHALL support Orchestrator designation

The agent builder dialog MUST let users designate an agent as an Orchestrator during creation or editing.

#### Scenario: User toggles Orchestrator on during creation
- **WHEN** the user enables the "设为协调者 (Orchestrator)" toggle in the Basic Info tab
- **THEN** the form automatically adds `plan_tasks` and `ask_user` to the tool set
- **AND** displays a hint explaining the Orchestrator role

#### Scenario: User submits with Orchestrator enabled
- **WHEN** the user submits the create/edit form with `isOrchestrator=true`
- **THEN** the API body includes `isOrchestrator: true`
- **AND** the backend persists `is_orchestrator=true` on the agent row

#### Scenario: User edits an existing Orchestrator agent
- **WHEN** the user opens an existing Orchestrator agent for editing
- **THEN** the toggle is pre-set to enabled
- **AND** `plan_tasks` and `ask_user` appear in the selected tools

### Requirement: API body SHALL include isOrchestrator field

The `CreateAgentBody` and `UpdateAgentBody` interfaces MUST include an optional `isOrchestrator` boolean field.

#### Scenario: Create agent with Orchestrator
- **WHEN** `CreateAgentBody.isOrchestrator` is `true`
- **THEN** the backend creates the agent with `is_orchestrator=true`

#### Scenario: Create agent without specifying
- **WHEN** `CreateAgentBody.isOrchestrator` is absent or `false`
- **THEN** the backend creates the agent with `is_orchestrator=false` (default)

#### Scenario: Update agent Orchestrator status
- **WHEN** `UpdateAgentBody.isOrchestrator` is provided
- **THEN** the backend updates the agent's `is_orchestrator` field
