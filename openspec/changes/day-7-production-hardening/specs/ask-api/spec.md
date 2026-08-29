## MODIFIED Requirements

### Requirement: The endpoint is not user-scoped

The endpoint SHALL require a valid session and SHALL refuse a request without one with 401
and the fixed unauthenticated message before any retrieval or model call. It SHALL NOT read
child profiles, meals, or conversations; SHALL NOT persist the question or answer; and
SHALL NOT accept an identity from the request body. The session exists to bound who can
spend model credit, not to personalise the answer: the same question from two accounts
yields the same retrieval.

#### Scenario: Unauthenticated question refused

- **WHEN** a question is posted without a valid session
- **THEN** the response is 401 and no knowledge-base search or model call is made

#### Scenario: Stateless request

- **WHEN** the same question is posted twice by a signed-in account
- **THEN** neither request reads child data from or writes to the application database

#### Scenario: Identity is not in the body

- **WHEN** a signed-in account posts a question with an extra `user_id` field
- **THEN** the response is 422
