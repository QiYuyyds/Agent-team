## ADDED Requirements

### Requirement: Conversations SHALL have a persistent RAG enabled flag

Each conversation MUST store a `rag_enabled` boolean field (default `false`) that controls whether RAG tools are available to responding agents.

#### Scenario: New conversation defaults to RAG disabled
- **WHEN** a conversation is created
- **THEN** `rag_enabled` is `false`

#### Scenario: User enables RAG for a conversation
- **WHEN** the user sends `PATCH /api/conversations/{id}/rag-mode` with `{ "ragEnabled": true }`
- **THEN** the conversation's `rag_enabled` is updated to `true`
- **AND** the updated conversation object is returned

#### Scenario: User disables RAG for a conversation
- **WHEN** the user sends `PATCH /api/conversations/{id}/rag-mode` with `{ "ragEnabled": false }`
- **THEN** the conversation's `rag_enabled` is updated to `false`

### Requirement: RAG tools SHALL be dynamically injected when conversation RAG is enabled

When a conversation has `rag_enabled=true`, all responding agents in that conversation MUST receive the full set of RAG tools (`rag_search`, `rag_ingest`, `rag_list_documents`, `rag_delete_document`).

#### Scenario: Message sent in RAG-enabled single chat
- **WHEN** a user sends a message in a single chat where `rag_enabled=true`
- **THEN** the responding agent's tool list includes all 4 RAG tools
- **AND** the agent can call any RAG tool during its response

#### Scenario: Message sent in RAG-enabled group chat
- **WHEN** a user sends a message in a group chat where `rag_enabled=true`
- **THEN** each responding agent's tool list includes all 4 RAG tools

#### Scenario: Agent already has RAG tools configured
- **WHEN** a conversation has `rag_enabled=true` and a responder agent already has some `rag_*` tools in its `tool_names`
- **THEN** no duplicate tools are added (deduplication via set union)

#### Scenario: SDK agents are excluded from RAG injection
- **WHEN** a conversation has `rag_enabled=true` and a responder uses `claude-code` or `codex` adapter
- **THEN** RAG tools are NOT injected for that agent

#### Scenario: Orchestrator child tasks inherit RAG tools
- **WHEN** an Orchestrator dispatches child tasks in a RAG-enabled conversation
- **THEN** child agents also receive the full set of RAG tools via `override_tool_names`

### Requirement: RAG toggle SHALL be accessible in the conversation input UI

The message input area MUST display a RAG toggle button that reflects and controls the current conversation's `rag_enabled` state.

#### Scenario: User sees RAG toggle in input toolbar
- **WHEN** a conversation is active (single or group chat)
- **THEN** a RAG toggle button is visible in the message input toolbar
- **AND** the button reflects the current `rag_enabled` state (highlighted when enabled)

#### Scenario: User toggles RAG on
- **WHEN** the user clicks the RAG toggle button while RAG is disabled
- **THEN** the conversation's `rag_enabled` is set to `true`
- **AND** the button becomes highlighted
- **AND** subsequent messages in this conversation will have RAG tools available

#### Scenario: User toggles RAG off
- **WHEN** the user clicks the RAG toggle button while RAG is enabled
- **THEN** the conversation's `rag_enabled` is set to `false`
- **AND** the button becomes unhighlighted
- **AND** subsequent messages will not have RAG tools injected
