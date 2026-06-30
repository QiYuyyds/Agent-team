## MODIFIED Requirements

### Requirement: Six new ORM models SHALL be defined
The models module MUST define 6 new ORM models: `LongTermMemory` (content, importance, embedding, created_at, last_accessed, category, tags, slot_hint, score), `UserPreference` (user_id, key, value, updated_at), `RagChunk` (doc_hash, chunk_idx, content, parent_content, embedding, created_at), `ChatHistory` (role, content, created_at), `MemoryNode` (mem_id, content, importance), `MemoryEdge` (from_id, to_id, rel_type, weight).

#### Scenario: New tables are created on startup
- **WHEN** the application starts with `Base.metadata.create_all`
- **THEN** all 6 new tables are created in PostgreSQL alongside existing 9 tables

#### Scenario: LongTermMemory stores embedding as JSONB
- **WHEN** a LongTermMemory row is inserted
- **THEN** the embedding column stores the vector as JSONB array
- **AND** it can be retrieved and used for cosine similarity computation

#### Scenario: ChatHistory is written on every message exchange
- **WHEN** `MemoryService.on_message_end()` processes a message (user or assistant)
- **THEN** a `ChatHistory` row is persisted to PostgreSQL with role, content, and created_at fields

#### Scenario: MemoryNode and MemoryEdge mirror Neo4j graph state
- **WHEN** `GraphMemory` upserts a node or edge to Neo4j
- **THEN** the corresponding `MemoryNode` or `MemoryEdge` row is also written to PostgreSQL as a mirror copy
- **AND** if Neo4j is unavailable, neither Neo4j nor PG mirror is written (consistent no-op degradation)
