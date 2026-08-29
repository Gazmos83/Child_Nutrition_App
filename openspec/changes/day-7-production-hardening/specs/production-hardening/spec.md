## Purpose

What a deployed instance must do that a development instance need not: bound how fast one
client can spend model credit or guess credentials, identify the client correctly behind the
hosting proxy, state the cross-origin policy explicitly, refuse to start in production with
missing secrets, and bring itself to a serving state (schema, knowledge base) from an empty
container.

## ADDED Requirements

### Requirement: Model-spending routes are rate-limited per client

The system SHALL limit the number of requests one client address may make per minute to the
routes that call the language model (the question endpoint and the chat endpoint together),
with a configurable limit that defaults to 30 and can be disabled with 0. A request over the
limit SHALL be answered 429 with a `detail` message and a `Retry-After` header, before any
retrieval or model call, and SHALL still carry the request identifier and produce an access
record.

#### Scenario: Under the limit

- **WHEN** a client has made fewer requests than the limit in the current minute
- **THEN** the request is handled normally

#### Scenario: Over the limit

- **WHEN** a client makes one more request than the limit within one minute
- **THEN** the response is 429 with a `detail` message and a `Retry-After` header, and no
  retrieval or model call is made

#### Scenario: Two clients are independent

- **WHEN** one client address is over the limit and another is not
- **THEN** the second client's requests are handled normally

#### Scenario: The window passes

- **WHEN** a client over the limit waits until the minute has elapsed
- **THEN** its next request is handled normally

#### Scenario: Disabled

- **WHEN** the limit is configured as 0
- **THEN** no request is refused for rate

### Requirement: Credential routes are rate-limited per client

The system SHALL limit registrations and sign-in attempts per client address per minute
with a separate configurable limit that defaults to 10 and can be disabled with 0, answering
429 with a `detail` message and a `Retry-After` header before any password work is done. The
refusal SHALL NOT reveal whether an email exists.

#### Scenario: Repeated sign-in attempts

- **WHEN** a client submits one more sign-in attempt than the limit within one minute
- **THEN** the response is 429 and the password is not verified

#### Scenario: Refusal is uniform

- **WHEN** a client over the limit signs in with a known email and, separately, an unknown one
- **THEN** both responses are 429 with identical bodies

### Requirement: The client address is the proxied client behind the hosting proxy

When the system is deployed behind the hosting platform's reverse proxy it SHALL take the
client address for rate limiting from the proxy's forwarded-for header; when it runs
directly on a host it SHALL use the connecting peer's address. The client address SHALL NOT
be written to any log record.

#### Scenario: Behind the proxy

- **WHEN** two requests arrive through the proxy with different forwarded client addresses
- **THEN** they count against two different rate-limit buckets

#### Scenario: Not logged

- **WHEN** a request is rate-limited
- **THEN** the access record and the 429 body carry no client address

### Requirement: Cross-origin access is an explicit allowlist

The system SHALL answer cross-origin browser requests (preflight and actual) with
credentials only for origins in a configured allowlist, and SHALL default to an empty
allowlist so that, unless configured, no cross-origin browser access is granted and the
API is reached through the same-origin frontend proxy.

#### Scenario: Allowed origin

- **WHEN** an origin in the allowlist sends a preflight request for a credentialed POST
- **THEN** the response grants that origin with credentials

#### Scenario: Unknown origin

- **WHEN** an origin not in the allowlist sends a preflight request
- **THEN** the response grants nothing

#### Scenario: Same-origin unaffected

- **WHEN** a request carries no `Origin` header
- **THEN** it is handled as before

### Requirement: Production configuration is validated at startup

When the deployment environment is production, the system SHALL refuse to start — naming
the missing setting — if the session secret or the language-model provider key is absent.
In development and test environments the system SHALL keep booting without them and
reporting through the health endpoint and per-route 503s as before.

#### Scenario: Production without a session secret

- **WHEN** the environment is production and no session secret is configured
- **THEN** the application fails to start with a message naming the setting

#### Scenario: Production without a provider key

- **WHEN** the environment is production and no provider key is configured
- **THEN** the application fails to start with a message naming the setting

#### Scenario: Development without either

- **WHEN** the environment is development and neither is configured
- **THEN** the application starts and the health endpoint answers

### Requirement: A container brings itself to a serving state

The system SHALL ship as a container image that, on start, applies every pending schema
migration, then ingests the knowledge base (embedding only documents that are new or
changed), then serves HTTP on the port the platform provides, and SHALL stop with a
non-zero exit if either preparatory step fails. The image SHALL run as a non-root user,
SHALL install dependencies only from the committed lockfile, and SHALL contain no secret,
no environment file, and no vector-store data.

#### Scenario: Fresh start on an empty disk

- **WHEN** the container starts against an empty database and no vector-store file
- **THEN** the schema is at head, every corpus document is embedded, and the health
  endpoint reports the database reachable

#### Scenario: Restart with everything in place

- **WHEN** the container restarts with the schema at head and an unchanged corpus
- **THEN** no migration runs, no document is re-embedded, and serving begins

#### Scenario: Migration fails

- **WHEN** the schema migration fails
- **THEN** the container exits non-zero and never serves HTTP

#### Scenario: Image contents

- **WHEN** the image is inspected
- **THEN** it contains no `.env`, no vector-store file, no frontend build, and runs as a
  non-root user
