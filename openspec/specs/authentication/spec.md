# authentication Specification

## Purpose
How a parent proves who they are and how that proof travels with each request. This
capability exists so that `user-account`'s ownership boundary has an identity to bind to:
every user-scoped route reads the account from the session, never from the request body.

## Requirements

### Requirement: An account is created from an email and a password

The system SHALL create an account from an email address and a password of 8 to 128
characters, SHALL retain the password only as a salted, memory-hard one-way hash, SHALL
never return or log the hash or the password, and SHALL reject a second account whose email
matches an existing one ignoring case with a conflict response.

#### Scenario: Registration signs the parent in

- **WHEN** a valid email and password are submitted to register
- **THEN** the response is 201 with the account's id and email, sets the session cookie,
  and contains neither the password nor its hash

#### Scenario: Duplicate email is a conflict

- **WHEN** registration is attempted with an email that differs from an existing account's
  only in case
- **THEN** the response is 409 and no second account is persisted

#### Scenario: Malformed credentials are rejected before any work

- **WHEN** the email is not an email address, the password is shorter than 8 or longer
  than 128 characters, or the body carries an unknown field
- **THEN** the response is 422 and nothing is hashed or stored

### Requirement: Sign-in does not reveal which credential was wrong

The system SHALL sign in an active account whose email (compared ignoring case) and
password match, and SHALL answer an unknown email, a wrong password, and a deactivated
account with the same status and the same message, taking the same time within the
precision of a password verification.

#### Scenario: Correct credentials

- **WHEN** an active account's email and password are submitted
- **THEN** the response is 200 with the account's id and email and sets the session cookie

#### Scenario: Wrong password and unknown email are indistinguishable

- **WHEN** a wrong password is submitted for an existing email, and separately any password
  is submitted for an unknown email
- **THEN** both responses are 401 with identical bodies and neither sets a cookie

#### Scenario: Deactivated account cannot sign in

- **WHEN** an account marked inactive submits its correct credentials
- **THEN** the response is 401

### Requirement: The session is a signed, expiring token in a cookie script cannot read

A session SHALL be a token signed with a server secret naming exactly one account and an
expiry, carried in a cookie marked `HttpOnly` and `SameSite=Lax`, marked `Secure` outside
development, and never present in a response body. A request whose token is absent,
tampered with, expired, or names a deleted or deactivated account SHALL be refused with 401
and one fixed message. Without a configured secret, authenticated routes SHALL answer 503
naming the missing setting rather than admitting anyone.

#### Scenario: Cookie attributes

- **WHEN** a sign-in or registration succeeds
- **THEN** the `Set-Cookie` header carries `HttpOnly`, `SameSite=lax`, and `Path=/`

#### Scenario: Tampered or expired token

- **WHEN** a request carries a token signed with a different secret, or one whose expiry
  has passed
- **THEN** the response is 401 with the fixed message and no record data

#### Scenario: Deactivation takes effect on the next request

- **WHEN** an account with a valid session is marked inactive
- **THEN** its next authenticated request is refused with 401

#### Scenario: Missing secret is loud

- **WHEN** no session secret is configured and an authenticated route is called
- **THEN** the response is 503 and the message names the setting

### Requirement: Sign-out clears the cookie

The system SHALL clear the session cookie on sign-out. The token itself remains valid until
its expiry (sessions are stateless); revocation before expiry is achieved by deactivating
the account.

#### Scenario: Logout

- **WHEN** a signed-in parent signs out
- **THEN** the response is 204 and clears the session cookie

### Requirement: The signed-in account is readable

The system SHALL return the signed-in account's id, email, and whether it is an
administrator (see `food-table-admin`), and nothing else about it, to a request with a valid
session.

#### Scenario: Who am I

- **WHEN** a request with a valid session asks for the current account
- **THEN** the response is 200 with exactly the id, the email, and the administrator flag

#### Scenario: Ordinary accounts are not administrators

- **WHEN** an account whose email is not configured as an administrator asks for the
  current account
- **THEN** the administrator flag is false
