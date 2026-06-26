## MODIFIED Requirements

### Requirement: Conversation metadata SHALL include RAG mode flag

The conversation data model MUST include a `rag_enabled` boolean field that is persisted in the database and exposed through the API.

#### Scenario: Conversation API response includes ragEnabled
- **WHEN** a conversation is fetched via API
- **THEN** the response includes `ragEnabled: boolean` (default `false`)

#### Scenario: RAG mode is toggled via API
- **WHEN** `PATCH /api/conversations/{id}/rag-mode` is called with `{ "ragEnabled": true }`
- **THEN** the conversation's `rag_enabled` field is updated
- **AND** the response returns the updated conversation with `ragEnabled: true`
