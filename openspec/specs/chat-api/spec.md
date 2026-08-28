# chat-api Specification

## Purpose

The `POST /api/chat` contract: a validated request carrying the message, optional child
context, and bounded history; an ordered stream of routing, tool-activity, answer, and
citation events; and an equivalent non-streaming JSON response.

## Requirements

### Requirement: The request is validated before any work

`POST /api/chat` SHALL accept a JSON body with a required non-blank `message` (at most
2000 characters), an optional `child_id` (a UUID naming one of the caller's children), an
optional `history` of at most twelve prior turns, an optional IANA `timezone` (default
UTC), an optional retrieval `strategy` (`basic` or `advanced`, default `advanced`), and
`stream` (default `true`). Unknown fields — including `child` and `feeding_log` — SHALL be
rejected. Invalid requests SHALL return HTTP 422 before any model call, retrieval, or tool
runs.

#### Scenario: Blank message rejected

- **WHEN** the body is `{"message": "   "}`
- **THEN** the response is 422 and no model call is made

#### Scenario: Unknown field rejected

- **WHEN** the body includes a field the contract does not define
- **THEN** the response is 422

#### Scenario: Invalid child context rejected

- **WHEN** the body carries a child context — of any shape, valid or with an age of 61
  months, a non-positive weight, or an allergy outside the controlled vocabulary
- **THEN** the response is 422, because the child's details are no longer accepted in the
  body at all

#### Scenario: Client cannot supply the child

- **WHEN** the body carries a `child` object or a `feeding_log`
- **THEN** the response is 422 and no model call is made

#### Scenario: Invalid child id rejected

- **WHEN** `child_id` is not a UUID
- **THEN** the response is 422

### Requirement: The streaming response is an ordered sequence of typed events

When `stream` is true the endpoint SHALL respond with `text/event-stream` and SHALL emit,
in this order: exactly one `route` event (intent and planned capabilities); zero or more
`tool` events, one per tool invocation, each carrying the tool name, status (`ok` or
`error`), the validated arguments, which arguments came from the child context, and the
result or error message; zero or more `token` events carrying answer text; exactly one
`final` event carrying citations, retrieval statistics (when retrieval ran), the
disclaimer, the intent, and a summary of tool outcomes; and exactly one terminal `done`
event. All `tool` events SHALL precede the first `token` event.

#### Scenario: Ordered stream for a tool answer

- **WHEN** a message routes to a tool and streams
- **THEN** the events are `route`, then one `tool` per invocation, then `token`s, then
  `final`, then `done`, with no `token` before any `tool`

#### Scenario: Knowledge-base answer carries citations

- **WHEN** a message routes to the knowledge base and retrieval passes the relevance floor
- **THEN** the `final` event's citations are non-empty and each carries a source title and,
  where known, a publication year

#### Scenario: Failure mid-stream is a terminal error event

- **WHEN** an unrecoverable error occurs after streaming has begun
- **THEN** the stream ends with a single `error` event carrying a warm, direct
  parent-facing message that says what happened and what to do next — never an exception
  string — and no `done` event follows

### Requirement: The non-streaming response carries the same content

When `stream` is false the endpoint SHALL return HTTP 200 with a JSON body containing the
answer text, the intent, the list of tool activities, the citations, retrieval statistics
(when retrieval ran), and the disclaimer — the same information the stream delivers.

#### Scenario: JSON shape

- **WHEN** `stream` is false
- **THEN** the body has exactly the fields `answer`, `intent`, `tools`, `citations`,
  `retrieval`, and `disclaimer`

### Requirement: Every response carries the disclaimer

The endpoint SHALL attach the fixed not-medical-advice disclaimer to every response,
streamed or not, including no-answer and tool-failure outcomes.

#### Scenario: Disclaimer on a tool failure

- **WHEN** every tool invocation for a message fails
- **THEN** the response still carries the disclaimer

### Requirement: Missing configuration is reported as unavailability

When the language-model provider or the knowledge base is not configured, the endpoint
SHALL return HTTP 503 with a message naming what is missing, without exposing secrets.

#### Scenario: No provider key

- **WHEN** the provider API key is not configured
- **THEN** the response is 503 and the message names the missing configuration

### Requirement: The endpoint answers for the authenticated account's child

`POST /api/chat` SHALL require a valid session and SHALL fill the child context and the
feeding log from the account's stored rows: the profile `child_id` names when given; the
account's only profile when omitted; no child context when the account has none. It SHALL
reject an omitted `child_id` with 422 naming the field when the account has several
children, and SHALL refuse a `child_id` the account does not own exactly as it refuses a
nonexistent one. The log read SHALL be bounded to the last fourteen days and two hundred
entries. Nothing about the conversation SHALL be stored.

#### Scenario: Unauthenticated chat refused

- **WHEN** the request carries no valid session
- **THEN** the response is 401 and no model call is made

#### Scenario: Child and log come from the rows

- **WHEN** the account has one child with a logged formula feed and asks a question
- **THEN** the resolved request carries that child's age, sex, and allergies and a feeding
  log containing that feed, and neither came from the body

#### Scenario: No child yet

- **WHEN** the account has no child profile
- **THEN** the request proceeds without child context and the existing side-panel hint
  applies to profile-backed tools

#### Scenario: Several children need a name

- **WHEN** the account has two children and `child_id` is omitted
- **THEN** the response is 422 and the message names `child_id`

#### Scenario: Unowned child id

- **WHEN** `child_id` names another account's child, and separately a nonexistent id
- **THEN** both responses are 404 with identical bodies and no model call is made

### Requirement: Responses carry a request identifier

Every `POST /api/chat` response SHALL carry an `X-Request-ID` header. A terminal streaming
`error` event SHALL include a `request_id` field alongside its message, and an unhandled
failure before streaming SHALL return 500 with `detail` and `request_id` and no traceback.

#### Scenario: Header on success

- **WHEN** a message is answered
- **THEN** the response carries `X-Request-ID`

#### Scenario: Request id in the streaming error

- **WHEN** an unrecoverable error occurs after streaming has begun
- **THEN** the terminal `error` event's data has `message` and `request_id`
