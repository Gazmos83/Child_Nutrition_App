# chat-api Specification

## Purpose

The `POST /api/chat` contract: a validated request carrying the message, optional child
context, and bounded history; an ordered stream of routing, tool-activity, answer, and
citation events; and an equivalent non-streaming JSON response.

## Requirements

### Requirement: The request is validated before any work

`POST /api/chat` SHALL accept a JSON body with a required non-blank `message` (at most
2000 characters), an optional `child` context, an optional `history` of at most twelve
prior turns, an optional retrieval `strategy` (`basic` or `advanced`, default
`advanced`), and `stream` (default `true`). Unknown fields SHALL be rejected. Invalid
requests SHALL return HTTP 422 before any model call, retrieval, or tool runs.

#### Scenario: Blank message rejected

- **WHEN** the body is `{"message": "   "}`
- **THEN** the response is 422 and no model call is made

#### Scenario: Unknown field rejected

- **WHEN** the body includes a field the contract does not define
- **THEN** the response is 422

#### Scenario: Invalid child context rejected

- **WHEN** the child context has an age of 61 months, a non-positive weight, or an
  allergy outside the controlled vocabulary
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

### Requirement: The endpoint reads and writes no user data

The endpoint SHALL NOT read or write any stored user, child, or conversation record and
SHALL take no user identity. Child context and history exist only in the request.

#### Scenario: No persistence

- **WHEN** a message with child context and history is processed
- **THEN** no database read or write occurs and a second identical request produces the
  same result independent of the first

### Requirement: The request may carry the client-held feeding log

`POST /api/chat` SHALL accept an optional `feeding_log` of at most two hundred validated
feeding entries and an optional IANA `timezone` (default UTC). Log-backed tool arguments
(entries, today's entries, time zone) SHALL be filled from the request, never from the
model, and the tool activity SHALL record that they came from the feeding log. An invalid
entry or time zone SHALL reject the request with HTTP 422 before any work.

#### Scenario: Log-backed arguments come from the request

- **WHEN** the router selects `detect_nutrient_gaps` and the request carries a feeding log
- **THEN** the tool runs over the request's entries and the activity lists `entries` as
  taken from the feeding log

#### Scenario: Invalid entry rejected

- **WHEN** the feeding log contains a `solid` entry without a food identifier
- **THEN** the response is 422 and no model call is made

#### Scenario: No log, tools still run

- **WHEN** the request carries no feeding log and the router selects `detect_nutrient_gaps`
- **THEN** the tool runs over an empty log and reports `insufficient_data`

### Requirement: Feedings and foods endpoints are stateless

`POST /api/feedings` SHALL validate a single feeding entry, return it normalised with its
identifier and table-derived nutrients, and store nothing. `GET /api/foods` SHALL return
the food-composition table listing. Neither SHALL take a user identity or read user data.

#### Scenario: Valid feeding returned with nutrients

- **WHEN** a valid `formula` entry of 150 ml is posted
- **THEN** the response is 200 with the entry, a generated identifier, and 100.5 kcal

#### Scenario: Unknown food named in the error

- **WHEN** a `solid` entry with an unknown food identifier is posted
- **THEN** the response is a validation error whose message contains that identifier
