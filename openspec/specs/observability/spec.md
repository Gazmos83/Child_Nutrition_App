# observability Specification

## Purpose
What the application writes to its logs and how one record is tied to another: a single
structured record format, per-request correlation and identity, latency on every request,
records for tool invocations and retrieval, one quotable identifier for any failure, and
the list of things that are never written. This is what lets an operator answer "what did
the app do for this request?" from the logs alone (reference §14).

## Requirements

### Requirement: Every log record is one structured line

The system SHALL emit every application log record as a single line in one configurable
format: JSON (one object per line) or human-readable text. A JSON record SHALL carry at
least a timestamp, level, logger name, message, and the request correlation fields below,
and SHALL include any structured fields attached to the record. The format and the minimum
level SHALL be configurable through the environment, with JSON the default.

#### Scenario: JSON record is parseable and complete

- **WHEN** the format is JSON and any record is emitted
- **THEN** the line parses as a JSON object containing `ts`, `level`, `logger`, `message`,
  `request_id`, `user_id`, and `child_profile_id` (the last three null outside a request)

#### Scenario: Text format remains available

- **WHEN** the format is set to text
- **THEN** records are emitted as readable lines containing the timestamp, level, logger,
  request id, and message

#### Scenario: Level is configurable

- **WHEN** the minimum level is set to WARNING
- **THEN** informational records are not emitted

### Requirement: Every request carries a correlation identifier

The system SHALL assign each HTTP request a request identifier — honouring a well-formed
incoming `X-Request-ID` header and otherwise generating one — SHALL return it in the
`X-Request-ID` response header on every response, including error responses, and SHALL
stamp it on every log record emitted while handling that request.

#### Scenario: Identifier generated and returned

- **WHEN** a request arrives without `X-Request-ID`
- **THEN** the response carries an `X-Request-ID` header holding a new identifier, and every
  record logged during the request carries the same value

#### Scenario: Well-formed incoming identifier is honoured

- **WHEN** a request arrives with a well-formed `X-Request-ID`
- **THEN** the response echoes that value and records carry it

#### Scenario: Malformed incoming identifier is replaced

- **WHEN** a request arrives with an `X-Request-ID` that is not a well-formed identifier
- **THEN** a new identifier is generated and used instead

### Requirement: Every request produces one access record with latency

The system SHALL emit exactly one access record per request when the response completes,
carrying the method, the matched route path (not the raw URL), the status code, the
latency in milliseconds, and the account identifier when the request authenticated. The
liveness probe's access record SHALL be emitted at debug level so probes do not drown the
log.

#### Scenario: Authenticated request

- **WHEN** a signed-in parent lists their children
- **THEN** one access record is emitted with method `GET`, route `/api/children`, status
  200, a latency, and the account's identifier

#### Scenario: Unauthenticated request

- **WHEN** a request without a session is refused
- **THEN** the access record has status 401 and a null account identifier

#### Scenario: Streaming response

- **WHEN** a chat answer streams
- **THEN** exactly one access record is emitted when the stream ends, with the full latency

#### Scenario: Probe is quiet

- **WHEN** the liveness endpoint is called
- **THEN** its access record is at debug level

### Requirement: Identity and child correlation come only from the server

Log records SHALL carry the account identifier only as resolved from the session, and the
child profile identifier only as resolved from the account's stored profile for that
request; neither SHALL ever be taken from the request body. Records SHALL carry
identifiers, never email addresses.

#### Scenario: Chat for a stored child

- **WHEN** a signed-in parent asks the assistant about their saved child
- **THEN** the routing, retrieval, tool, and audit records for that request all carry the
  same request id, the account id, and that child profile's id

#### Scenario: No child yet

- **WHEN** the account has no saved child
- **THEN** records carry the account id and a null child profile id

### Requirement: Tool invocations and retrieval are recorded with latency

The system SHALL emit one record per nutrient-tool invocation carrying the tool name, the
outcome (ok or error), the latency in milliseconds, and which arguments were filled from
the child's stored details or feeding log, and SHALL record for each knowledge-base
retrieval the strategy, the queries issued, the counts retrieved and kept, the best score,
and the latency in milliseconds.

#### Scenario: Tool record

- **WHEN** the router runs `calculate_protein_target` with the age and weight taken from the
  stored profile
- **THEN** a record names the tool, status `ok`, a latency, and lists `age_months` and
  `weight_kg` as taken from context

#### Scenario: Failed tool is recorded, not hidden

- **WHEN** a tool invocation fails validation
- **THEN** a record names the tool with status `error` and the failure category

#### Scenario: Retrieval record

- **WHEN** a knowledge-base search runs
- **THEN** a record carries the strategy, the queries, retrieved and kept counts, the top
  score, and a latency

### Requirement: Failures produce one structured error record and a quotable identifier

An unhandled failure SHALL produce exactly one error-level record carrying the request id
and the exception details, and the client SHALL receive a 500 response whose body names a
fixed message and the request id and never contains a traceback. A failure after a stream
has begun SHALL end the stream with an error event that carries the request id.

#### Scenario: Unhandled exception

- **WHEN** a route raises an unexpected exception
- **THEN** one error record with the traceback and request id is emitted, and the response is
  500 with `detail` and `request_id` fields only

#### Scenario: Mid-stream failure

- **WHEN** a streaming answer fails after events were sent
- **THEN** the terminal error event carries the parent-facing message and the request id

### Requirement: Some things are never logged

The system SHALL NOT write to any log record: passwords, password hashes, session tokens,
cookies, request headers, email addresses, or the text of the parent's chat message or the
assistant's answer. The doctor's note SHALL remain in the meal-plan and gap-detection audit
snapshots (hard rule 8).

#### Scenario: Sign-in leaves no credential trace

- **WHEN** a parent registers or signs in
- **THEN** no record contains the password, its hash, the session token, or the email

#### Scenario: Chat message text stays out

- **WHEN** a message is processed
- **THEN** records carry the message's length and the routing decision, not its text

### Requirement: Audit records have a deliberate sink

The system SHALL allow the audit records (meal plan, gap detection) to be directed to their
own JSON-lines file by configuration; when not configured they SHALL be emitted with the
rest of the log. Either way each audit record SHALL carry the request correlation fields.

#### Scenario: Audit file configured

- **WHEN** an audit file path is configured and a meal plan is generated through the chat
- **THEN** the audit record is appended to that file as one JSON line carrying `request_id`,
  `user_id`, and `child_profile_id`, and is not duplicated in the main log

#### Scenario: Audit file not configured

- **WHEN** no audit file path is configured
- **THEN** the audit record appears in the main log with the same correlation fields
