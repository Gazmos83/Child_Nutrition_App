## MODIFIED Requirements

### Requirement: Every routing decision is logged

The system SHALL emit one structured log record per message containing the intent, the
proposed and executed capabilities with their outcomes, knowledge-base retrieval
statistics when retrieval ran, the message length, and end-to-end latency, carrying the
request's correlation identifier; and SHALL emit one record per tool invocation with the
tool name, outcome, latency, and which arguments were filled from context. The message
text itself SHALL NOT be logged.

#### Scenario: Log record present

- **WHEN** any message is processed, successfully or not
- **THEN** a log record with intent, capabilities, outcomes, message length, and latency is
  emitted, carrying the request id

#### Scenario: One record per tool invocation

- **WHEN** the router runs two tools for a message
- **THEN** two tool records are emitted, each with its own latency and outcome, before the
  routing summary
