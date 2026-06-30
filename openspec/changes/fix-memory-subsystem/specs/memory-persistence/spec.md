## ADDED Requirements

### Requirement: chat_history SHALL be persisted to PostgreSQL on every message
`MemoryService.on_message_end()` SHALL write a `ChatHistory` row to PostgreSQL immediately after `stm.add()`, storing role, content, and `time.time()` as created_at.

#### Scenario: User message triggers chat_history write
- **WHEN** `on_message_end("user", "你好")` is called
- **THEN** a `ChatHistory` row is inserted with role="user", content="你好", created_at=current epoch time

#### Scenario: Assistant message triggers chat_history write
- **WHEN** `on_message_end("assistant", "好的，我来帮你")` is called
- **THEN** a `ChatHistory` row is inserted with role="assistant", content="好的，我来帮你", created_at=current epoch time

#### Scenario: chat_history write failure does not block message flow
- **WHEN** PostgreSQL write fails (connection timeout, etc.)
- **THEN** the error is logged as a warning and `on_message_end()` continues normally

### Requirement: MemoryService SHALL receive embed_fn injection at startup
`main.py` lifespan SHALL call `_memory_service.set_embed_fn(embed_fn)` using the same embed_fn instance injected into `_rag_service`, ensuring LTM items have embedding vectors.

#### Scenario: embed_fn is available and injected
- **WHEN** `_make_embed_fn(settings)` returns a valid callable
- **THEN** `_memory_service.set_embed_fn(embed_fn)` is called during lifespan startup
- **AND** subsequent `ltm.add()` calls produce items with non-NULL embedding vectors

#### Scenario: embed_fn is unavailable
- **WHEN** `_make_embed_fn(settings)` returns None (EMBEDDING_API_KEY not set)
- **THEN** `_memory_service` operates without embed_fn, LTM items have NULL embedding (existing TF fallback behavior preserved)

### Requirement: memory_nodes PG mirror SHALL be written alongside Neo4j
`GraphMemory._upsert_memory_node()` SHALL write a `MemoryNode` row to PostgreSQL after successful Neo4j MERGE. If Neo4j is unavailable, PG write is also skipped (no-op degradation preserved).

#### Scenario: Neo4j available — node written to both stores
- **WHEN** `_upsert_memory_node(mem_id=5, content="Python 3.12", importance=0.7)` executes with Neo4j connected
- **THEN** Neo4j `:Memory {mem_id: 5}` node is created/updated
- **AND** a `MemoryNode` row with mem_id=5, content="Python 3.12", importance=0.7 is inserted/updated in PG

#### Scenario: Neo4j unavailable — both stores skipped
- **WHEN** `_upsert_memory_node()` is called with no Neo4j driver
- **THEN** neither Neo4j nor PG `memory_nodes` is written (existing no-op behavior)

### Requirement: memory_edges PG mirror SHALL be written alongside Neo4j
`GraphMemory._add_memory_edge()` SHALL write a `MemoryEdge` row to PostgreSQL after successful Neo4j MERGE.

#### Scenario: FOLLOWS edge written to both stores
- **WHEN** `_add_memory_edge(from_id=3, to_id=5, "FOLLOWS", 1.0)` executes with Neo4j connected
- **THEN** Neo4j `FOLLOWS` edge is created
- **AND** a `MemoryEdge` row with from_id=3, to_id=5, rel_type="FOLLOWS", weight=1.0 is inserted in PG

#### Scenario: SIMILAR_TO edge written to both stores
- **WHEN** `_add_memory_edge(from_id=3, to_id=7, "SIMILAR_TO", 0.85)` executes with Neo4j connected
- **THEN** Neo4j `SIMILAR_TO` edge is created
- **AND** a `MemoryEdge` row with from_id=3, to_id=7, rel_type="SIMILAR_TO", weight=0.85 is inserted in PG

#### Scenario: PG mirror write failure does not affect Neo4j
- **WHEN** PG `MemoryEdge` insert fails
- **THEN** the error is logged as a warning and Neo4j edge remains intact
