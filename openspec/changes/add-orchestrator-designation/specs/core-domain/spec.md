# Core Domain Delta

## MODIFIED Requirements

### Requirement: Group conversation creation SHALL display Orchestrator status

The new conversation dialog MUST inform users about Orchestrator presence when creating group chats.

#### Scenario: Selected agents include an Orchestrator
- **WHEN** the user selects 2+ agents and at least one has `isOrchestrator=true`
- **THEN** the dialog displays "协调者: {agentName} ✓"

#### Scenario: Selected agents have no Orchestrator
- **WHEN** the user selects 2+ agents and none has `isOrchestrator=true`
- **THEN** the dialog displays a warning: "此群聊无协调者，消息须 @ 具体 Agent 才能被响应"
- **AND** does not prevent conversation creation

### Requirement: Group chat message routing SHALL provide feedback when no Orchestrator exists

The message routing logic MUST not silently drop messages when no Orchestrator is available.

#### Scenario: Message sent in group chat without Orchestrator and no @mention
- **WHEN** a user sends a message without @mention in a group chat that has no Orchestrator
- **THEN** the system creates an agent/system message informing the user
- **AND** the message content is: "此群聊没有协调者。请使用 @Agent名 指定回复对象。"
- **AND** the message is broadcast via the event bus so all connected clients see it

#### Scenario: Message sent with @mention in group chat without Orchestrator
- **WHEN** a user sends a message with @mention in a group chat that has no Orchestrator
- **THEN** the mentioned agents respond normally (no change in behavior)
