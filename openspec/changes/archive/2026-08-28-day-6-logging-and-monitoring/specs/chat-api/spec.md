## ADDED Requirements

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
