## MODIFIED Requirements

### Requirement: The parent supplies child context through a controlled form

The UI SHALL provide a form for the child's age in **months** (0–60, labelled as months),
weight in kilograms, sex, optional height in centimetres (marked as required from 36
months), diet preference chosen from the controlled vocabulary, allergies chosen from the
controlled vocabulary, an optional doctor's note, and activity level. The form SHALL save
these values to the signed-in account with an explicit Save, SHALL show whether the form
matches what is saved, and SHALL load the saved profile on every visit. Free-text entry for
allergies or diet preference SHALL NOT be possible.

#### Scenario: Age is entered in months

- **WHEN** the parent views the age field
- **THEN** it is labelled in months, accepts 0–60, and offers no years entry

#### Scenario: Allergies are a fixed list

- **WHEN** the parent records allergies
- **THEN** they choose from the nine controlled-vocabulary allergens and cannot type a
  custom one

#### Scenario: Context persists across reloads

- **WHEN** the parent fills the form, saves, and reloads the page
- **THEN** the form shows the saved values from the account

#### Scenario: Unsaved edits are visible

- **WHEN** the parent changes a saved field and has not pressed Save
- **THEN** the form shows that the details are not saved yet and offers Save

### Requirement: The parent can log feeds and see today's intake

The UI SHALL provide a Feeding-log tab with a form to log a feed (feeding type from the
controlled vocabulary; a food picker offering only foods from the food table, filtered to
milk feeds for breast milk and formula and hidden for water; quantity with the unit set
from the chosen food; time defaulting to now), a list of logged entries grouped by day
with their nutrients and a way to delete one, and "today so far" totals. The log SHALL be
read from and written to the signed-in account's child; when no child is saved yet the tab
SHALL say so instead of offering the form.

#### Scenario: Picker offers only table foods

- **WHEN** the parent logs a solid
- **THEN** the food choices are exactly the foods returned by the food listing, and no
  free-text food can be entered

#### Scenario: Entry appears with nutrients

- **WHEN** the parent logs 150 ml of formula
- **THEN** the entry appears under today with about 100 kcal and today's totals increase
  accordingly

#### Scenario: Log survives a reload

- **WHEN** the parent reloads the page
- **THEN** entries from the last fourteen days are still listed, read from the account

#### Scenario: No child yet

- **WHEN** the account has no saved child and the parent opens the Feeding-log tab
- **THEN** it explains that the child's details come first and shows no log form

## ADDED Requirements

### Requirement: The parent signs in before using the assistant

The UI SHALL show a sign-in / create-account screen to an unauthenticated visitor and
nothing of the chat, the child form, or the log. After sign-in it SHALL show the chat with
the account's email and a Sign out control. When a request is refused for a missing
session, the UI SHALL return to sign-in, keep the conversation on screen, and say that
signing in again and retrying will continue it.

#### Scenario: Signed out sees only sign-in

- **WHEN** a visitor with no session opens the app
- **THEN** they see the sign-in form with a switch to create an account, and no chat

#### Scenario: Sign-in failure shows the server's reason

- **WHEN** sign-in is refused or an email is already taken
- **THEN** the form shows the server's message and stays on screen

#### Scenario: Session ends mid-visit

- **WHEN** a message is sent after the session has expired
- **THEN** the assistant message reports that the parent was signed out and how to
  continue, and the sign-in screen appears with the conversation kept for after sign-in

#### Scenario: Sign out

- **WHEN** the parent signs out
- **THEN** the sign-in screen appears and the child's details and log are no longer shown
