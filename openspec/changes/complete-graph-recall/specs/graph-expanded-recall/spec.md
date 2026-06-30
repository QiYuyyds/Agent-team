## ADDED Requirements

### Requirement: LTM recall SHALL integrate 1-hop graph expansion
`LongTerm.recall()` SHALL perform a two-phase recall: (1) semantic search for seed items, then (2) graph-based 1-hop expansion from seed IDs using `graph_memory.find_related()`. Expanded items are assigned a fixed score of 0.45, merged with seeds, sorted by score descending, and truncated to `top_k`.

#### Scenario: Graph expansion finds related memories
- **WHEN** `recall("Python 特性", top_k=5)` is called with graph_memory available
- **AND** the seed item (id=3, "Python 3.12 类型参数") has a FOLLOWS edge to item (id=7, "pip 依赖管理")
- **THEN** item id=7 is included in results with score=0.45
- **AND** results are sorted by score descending and truncated to top_k

#### Scenario: No graph memory — pure semantic recall preserved
- **WHEN** `recall(query, top_k)` is called with graph_memory set to None
- **THEN** the recall behaves exactly as before (pure cosine/TF semantic search)
- **AND** no graph expansion is performed

#### Scenario: Graph expansion returns empty — seeds returned unchanged
- **WHEN** `recall(query, top_k)` is called and `find_related()` returns no new IDs
- **THEN** only seed items are returned (same as current behavior)

#### Scenario: Expanded items respect category filter
- **WHEN** graph expansion finds items with category "general" and a category filter is applied
- **THEN** expanded items not matching the filter are excluded from results

### Requirement: Graph expansion SHALL gracefully degrade on failure
If `graph_memory.find_related()` raises an exception during recall, the system SHALL catch the error, log a warning, and return only the seed items without graph expansion.

#### Scenario: Neo4j unavailable during recall
- **WHEN** `find_related()` raises an exception (Neo4j connection failure)
- **THEN** the error is logged as a warning
- **AND** only seed items from semantic search are returned
- **AND** the recall operation completes successfully without the graph expansion

### Requirement: recall_by_filter SHALL also integrate graph expansion
`LongTerm.recall_by_filter()` SHALL apply the same graph expansion logic as `recall()`, expanding seed items found by filtered semantic search with 1-hop graph neighbors.

#### Scenario: Filtered recall with graph expansion
- **WHEN** `recall_by_filter(query, embedding, filter)` is called with graph_memory available
- **THEN** seed items are found via filtered semantic search
- **AND** 1-hop graph expansion is applied to seeds
- **AND** expanded items (score=0.45) are merged with seeds and truncated to top_k
