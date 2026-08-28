## REMOVED Requirements

### Requirement: The endpoint reads and writes no user data

**Reason**: Day 6 binds the chat to the signed-in account; the child's details and the
feeding log are now read from the account's own rows. Replaced by *The endpoint answers for
the authenticated account's child* below.

**Migration**: clients send `child_id` (optional when the account has one child) instead of
`child` and `feeding_log`, and carry the session cookie.

### Requirement: The request may carry the client-held feeding log

**Reason**: the log is stored per child on the account (`feeding-log`) and read
server-side; the request no longer carries it.

**Migration**: log feeds through `POST /api/children/{child_id}/feedings`; the chat reads the
last fourteen days itself.

### Requirement: Feedings and foods endpoints are stateless

**Reason**: `POST /api/feedings` is removed in favour of the child-scoped, authenticated
feeding routes (`feeding-log`). `GET /api/foods` remains public and stateless and is
restated in `feeding-log`'s *Foods are listable for the picker*.

## MODIFIED Requirements

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

## ADDED Requirements

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
