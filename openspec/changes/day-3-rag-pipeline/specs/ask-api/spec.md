## Purpose

The HTTP contract for asking the nutrition assistant a question: validated input, a
streamed answer with a terminal citations event or a single JSON response, and an explicit
boundary that the endpoint reads and writes no user-scoped data.

## ADDED Requirements

### Requirement: Questions are submitted to `POST /api/ask`

The system SHALL accept a JSON body with a required `question` string (1–2000 characters
after trimming), an optional `strategy` of `basic` or `advanced` (default `advanced`),
and an optional boolean `stream` (default `true`). Invalid bodies MUST be rejected with
HTTP 422 before any retrieval or model call (hard rule 7).

#### Scenario: Valid question

- **WHEN** a client posts `{"question": "When can babies start solid food?"}`
- **THEN** the response status is 200

#### Scenario: Empty question

- **WHEN** a client posts `{"question": "   "}`
- **THEN** the response status is 422
- **AND** no knowledge-base search or model call is made

#### Scenario: Unknown strategy

- **WHEN** a client posts `{"question": "...", "strategy": "hybrid"}`
- **THEN** the response status is 422

### Requirement: Streamed responses use server-sent events

When `stream` is true, the system SHALL respond with `text/event-stream` and emit, in
order: zero or more `token` events carrying answer text fragments, one `citations` event
carrying the citation list and retrieval metadata, and one `done` event. On failure after
streaming has begun, the system SHALL emit an `error` event with a message and end the
stream.

#### Scenario: Successful stream

- **WHEN** a valid question is posted with `stream: true`
- **THEN** the response content type is `text/event-stream`
- **AND** the concatenated `token` events equal the full answer text
- **AND** exactly one `citations` event precedes exactly one `done` event

#### Scenario: No-answer response is streamed too

- **WHEN** the knowledge base has nothing relevant and `stream` is true
- **THEN** the fixed no-answer message is delivered as `token` events
- **AND** the `citations` event carries an empty citation list

#### Scenario: Failure mid-stream

- **WHEN** the language model call fails after the response has started
- **THEN** the stream ends with an `error` event
- **AND** the client receives no `done` event

### Requirement: Non-streamed responses return a single JSON document

When `stream` is false, the system SHALL return a JSON object with `answer`, `citations`,
`disclaimer`, `strategy`, and `retrieval` (queries, filters, retrieved count, kept count).

#### Scenario: JSON response shape

- **WHEN** a valid question is posted with `stream: false`
- **THEN** the response is JSON with exactly the fields answer, citations, disclaimer,
  strategy, retrieval

### Requirement: The endpoint is not user-scoped

The endpoint SHALL NOT read child profiles, meals, or conversations; SHALL NOT persist
the question or answer; and SHALL NOT accept or infer a user identity. It therefore
exposes no cross-user data path before authentication ships (hard rule 9).

#### Scenario: Stateless request

- **WHEN** the same question is posted twice
- **THEN** neither request reads from or writes to the application database

### Requirement: Missing model configuration is reported, not crashed

When the language-model provider is not configured, the endpoint SHALL return HTTP 503
with a message naming the missing configuration, and the application SHALL still boot
and answer `GET /health`.

#### Scenario: Provider key absent

- **WHEN** the provider API key is not configured and a question is posted
- **THEN** the response status is 503
- **AND** the body names the missing setting

#### Scenario: Application boots without provider configuration

- **WHEN** the application starts with no provider or vector-store configuration
- **THEN** `GET /health` returns 200
