## MODIFIED Requirements

### Requirement: Every gap detection is logged for audit

The system SHALL emit an audit record for every gap detection containing the child input
snapshot, the number of complete and incomplete days, the window, the confidence, each
nutrient's average, target, ratio, flag, and target source, and the override outcome. When
the detection runs inside a request, the record SHALL carry that request's correlation
identifier, the account identifier, and the stored child profile identifier the inputs
came from.

#### Scenario: Audit record present

- **WHEN** gap detection runs, including the `insufficient_data` outcome
- **THEN** an audit record with those fields is emitted

#### Scenario: Audit record is correlated

- **WHEN** gap detection runs for a signed-in parent's saved child through the chat
- **THEN** the audit record carries the request id, the account id, and the child profile id
