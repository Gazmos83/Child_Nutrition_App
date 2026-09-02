## MODIFIED Requirements

### Requirement: Age is represented in months

The system SHALL store a child's date of birth and SHALL derive the child's age from it as
a whole number of completed months — as of the current UTC date for the profile, and as of
a given date wherever a dated record needs the age on that day. Every age the system
returns or reasons with SHALL be an integer count of months; the system SHALL NOT persist
or return age in years in any form, and SHALL NOT accept a typed age. A date of birth
later than one day after the current UTC date, or one that puts the child past 60 months,
SHALL be rejected. Completed months SHALL be counted by calendar month, with a birthday
that falls on a day the current month does not have treated as the last day of that month.

#### Scenario: Age accepted in months

- **WHEN** a profile is created with a date of birth eight calendar months before today
- **THEN** the returned age is the integer `8`, derived from the stored date of birth

#### Scenario: Newborn boundary accepted

- **WHEN** a profile is created with today's date as the date of birth
- **THEN** the profile is accepted and its age is `0`

#### Scenario: Negative age rejected

- **WHEN** a profile is created with a date of birth two days after today, which would make
  the age negative
- **THEN** the system rejects the profile as invalid

#### Scenario: Age beyond the supported range rejected

- **WHEN** a profile is created with a date of birth more than `60` months before today
- **THEN** the system rejects the profile as outside the supported range of newborn through
  ~4 years

#### Scenario: Fractional age rejected

- **WHEN** a profile is submitted with a typed age such as `8` or `8.5` months instead of a
  date of birth
- **THEN** the system rejects the request as invalid; age is only ever derived as whole
  completed months

#### Scenario: Month-end birthday counted by calendar month

- **WHEN** a child born on 31 January is assessed on 28 February and on 31 March of a
  non-leap year
- **THEN** the ages are `1` month and `2` months respectively

### Requirement: A profile can reproduce the full chat context

A profile SHALL carry, in addition to the date of birth (from which age in months is
derived), weight, sex, diet preference, allergies, and doctor's note, an optional height in
centimetres (required from 36 months of derived age) and an activity level from the
controlled vocabulary, so that the stored profile alone is sufficient to fill every
profile-backed tool argument, with the age supplied as completed months as of the request.
A stored profile whose derived age has passed 60 months SHALL be refused as out of range
wherever the chat context is built, with a message naming the supported range, rather than
failing the request.

#### Scenario: Height required from 36 months

- **WHEN** a profile with a date of birth 40 months ago is submitted without a height
- **THEN** the system rejects it with a validation error naming height

#### Scenario: Activity level is a controlled vocabulary

- **WHEN** a profile names an activity level outside the vocabulary
- **THEN** the system rejects it with a validation error

#### Scenario: Derived age reaches the tools

- **WHEN** a chat request is made for a profile born eight months ago
- **THEN** every profile-backed tool argument receives `age_months` of `8`

#### Scenario: A child who has aged out is refused, not crashed

- **WHEN** a stored profile's derived age is above 60 months and the owner requests daily
  targets or a chat answer
- **THEN** the response is a validation error naming the supported range
