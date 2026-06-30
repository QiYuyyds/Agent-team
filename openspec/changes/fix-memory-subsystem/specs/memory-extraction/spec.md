## ADDED Requirements

### Requirement: Assistant reply SHALL trigger LLM-based memory extraction
When an assistant reply is received via `on_message_end("assistant", content)`, the system SHALL use LLM to extract key-value facts from the reply and store them as classified long-term memories, replacing the current behavior of storing raw assistant text.

#### Scenario: LLM extracts facts from assistant reply
- **WHEN** `on_message_end("assistant", "Python 3.12 引入了类型参数语法和更好的错误信息")` is called with LLM available
- **THEN** the LLM extracts facts like `{"key": "Python 3.12 features", "value": "类型参数语法和更好的错误信息"}`
- **AND** extracted facts are stored via `ltm.store_classified()` with appropriate category and tags

#### Scenario: LLM unavailable — fallback to simple add
- **WHEN** `on_message_end("assistant", content)` is called with no generate_fn
- **THEN** the system falls back to `ltm.add(content, importance)` using the existing importance heuristic

#### Scenario: Short or trivial reply is skipped
- **WHEN** assistant reply is shorter than 10 characters or matches trivial patterns ("好的", "没问题", "OK")
- **THEN** no memory extraction is performed

### Requirement: Memory content SHALL be classified before storage
Extracted facts SHALL be classified using rule-based heuristics (`classify_memory_content`) before storage, assigning category, tags, and slot_hint.

#### Scenario: Identity-related content is classified
- **WHEN** extracted fact mentions user's name, role, or identity information
- **THEN** category is set to "identity", slot_hint to "user_profile"

#### Scenario: Preference-related content is classified
- **WHEN** extracted fact mentions user preference (code style, language, tool choice)
- **THEN** category is set to "preference", slot_hint to "user_prefs"

#### Scenario: Unknown content gets general classification
- **WHEN** no rule matches the extracted fact
- **THEN** category defaults to "general", slot_hint to "general_knowledge"

### Requirement: LongTerm SHALL support store_classified with cosine dedup
`LongTerm` SHALL provide a `store_classified(content, importance, emb, category, tags, slot_hint)` method that performs embedding-based dedup against existing items before inserting.

#### Scenario: New unique fact is inserted
- **WHEN** `store_classified()` is called with embedding that has cosine similarity < 0.95 against all existing items
- **THEN** a new `LongTermMemory` row is inserted with all classified fields
- **AND** the item is appended to in-memory `self.items`

#### Scenario: Duplicate fact triggers update instead of insert
- **WHEN** `store_classified()` is called with embedding that has cosine similarity >= 0.95 against an existing item
- **THEN** the existing item's importance, tags, category, and slot_hint are updated
- **AND** no new row is inserted (only `UPDATE` on existing row)

### Requirement: Memory extraction SHALL run as background task
All LLM extraction and classification operations SHALL execute via `asyncio.create_task()` to avoid blocking the main message flow.

#### Scenario: Extraction runs in background
- **WHEN** `on_message_end("assistant", long_content)` triggers extraction
- **THEN** the extraction coroutine is dispatched as a background task
- **AND** `on_message_end()` returns immediately without waiting for extraction completion

#### Scenario: Extraction task failure is isolated
- **WHEN** the background extraction task raises an exception
- **THEN** the error is logged as a warning and does not affect conversation flow
