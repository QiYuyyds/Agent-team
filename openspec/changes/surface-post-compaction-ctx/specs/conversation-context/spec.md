# Conversation Context

## ADDED Requirements

### Requirement: Compaction SHALL report the post-compaction context size

The compact action MUST return the estimated context size before and after compaction as structured data, not only embedded in the announcement message text.

#### Scenario: Compaction succeeds

- **WHEN** `POST /conversations/{id}/compact` completes successfully
- **THEN** the response body includes numeric `ctxBefore` and `ctxAfter` fields (estimated prompt tokens the next turn would carry, before vs. after compaction).

### Requirement: The usage badge SHALL reflect post-compaction ctx immediately

After a successful compaction, the frontend "当前 ctx" indicator MUST show the post-compaction estimate without waiting for the next real agent turn, and MUST yield back to the actual measured prompt size once a newer run produces usage.

#### Scenario: User compacts a long conversation

- **WHEN** the compact request returns `ctxAfter`
- **THEN** the badge's "当前 ctx" shows `ctxAfter` as an optimistic override keyed by conversation.

#### Scenario: A real agent turn happens after compaction

- **WHEN** a run newer than the override timestamp produces usage
- **THEN** the badge shows that run's measured input tokens and the override no longer applies.
