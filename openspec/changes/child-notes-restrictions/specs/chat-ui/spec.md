## MODIFIED Requirements

### Requirement: The parent supplies child context through a controlled form

The UI SHALL provide a form for the child's date of birth (from which the age is derived
and shown in **months**), weight in kilograms, sex, optional height in centimetres (marked
as required from 36 months), diet preference chosen from the controlled vocabulary,
allergies chosen from the controlled vocabulary, a list of note rows under the heading
"Doctor's note and personal preferences" — each row a kind chosen from `doctor` |
`preference` and one instruction as text, with controls to add and remove rows — and
activity level. The form SHALL save these values to the signed-in account with an explicit
Save, SHALL show whether the form matches what is saved, and SHALL load the saved profile on
every visit. Free-text entry for allergies or diet preference SHALL NOT be possible, and
there SHALL be no field for typing an age.

#### Scenario: Age is entered in months

- **WHEN** the parent views the age information
- **THEN** it is a date-of-birth field with the derived age shown in months beside it, and
  the form offers no age or years entry

#### Scenario: Impossible birth dates are explained

- **WHEN** the parent enters a date of birth in the future or more than 60 months ago
- **THEN** the form shows an error on the date-of-birth field and does not save

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

#### Scenario: Notes are rows with a kind

- **WHEN** the parent adds a row, picks "Preference", types "no pork", and saves
- **THEN** the saved profile carries one preference row reading "no pork"
- **AND** a blank row or two identical rows block the save with an error on the rows

### Requirement: Meal plans render as a structured card

When a response includes a meal-plan result the UI SHALL render a card showing the items
grouped by meal slot with servings and serving size, coverage of calorie, protein, and
iron targets, the excluded foods with their reasons, and — for each nutrient a doctor's row
overrode — a prominent conflict banner naming both values (hard rule 3). When any note row
could not be applied, the card SHALL list each such row with its reason under a "Not
applied, and why" heading. A no-safe-plan outcome SHALL display the plan's explanatory
message prominently.

#### Scenario: Override conflict is unmissable

- **WHEN** the meal-plan result reports a doctor's-row override conflict
- **THEN** the card shows a distinct banner titled "Your doctor's note takes priority
  here" stating the row's value and the general value it replaced, for the nutrient
  concerned, one banner per overridden nutrient

#### Scenario: No safe plan

- **WHEN** the meal-plan result's outcome is no-safe-plan
- **THEN** the card shows the headline "We couldn't build a safe plan with these details —
  here's why, and what you might want to check", a "Here's why" section listing the
  exclusions with reasons, and a "Worth checking" section naming age in months, recorded
  allergies, diet preference, and the pediatrician, instead of items

#### Scenario: Rows the plan could not apply are listed

- **WHEN** the meal-plan result reports a row that was not applied
- **THEN** the card lists that row's text with the reason under "Not applied, and why"
- **AND** a result whose rows were all applied shows no such section

### Requirement: The panel says when a doctor's note is on file but not applied to it

Because the Daily-targets tab reports general reference targets rather than note-adjusted
ones, the UI SHALL state when doctor's rows, preference rows, or both are on file for the
child and that they are applied when meal plans are generated, so a parent is never left to
infer that the rows were ignored (hard rule 3).

#### Scenario: A note on file is disclosed

- **WHEN** the child's profile carries a doctor's row and the parent opens the Daily-targets
  tab
- **THEN** the tab states that a doctor's note is on file and that it is applied when
  planning meals

#### Scenario: No note, no claim

- **WHEN** the child's profile carries no note rows
- **THEN** the Daily-targets tab makes no statement about notes

#### Scenario: Preferences are disclosed as preferences

- **WHEN** the child's profile carries only preference rows
- **THEN** the tab states that preferences are on file and are applied when planning meals,
  without calling them a doctor's note

## ADDED Requirements

### Requirement: The Child tab marks a row the last plan could not apply

When the most recent meal plan in the chat session reports a note row as not applied, the
Child tab SHALL mark the matching row (same kind and text) with the reason, so the parent
can correct it where they typed it. Editing the row's text SHALL clear the mark until the
next plan.

#### Scenario: An unmatched row is marked where it was typed

- **WHEN** the last plan reported the preference row "no kale chips" as not applied because
  no such food is in the table
- **THEN** that row on the Child tab carries a mark quoting that reason

#### Scenario: Editing clears the mark

- **WHEN** the parent changes the marked row's text
- **THEN** the mark disappears until a new plan reports on the edited row
