## ADDED Requirements

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
