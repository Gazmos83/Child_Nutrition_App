## MODIFIED Requirements

### Requirement: The parent supplies child context through a controlled form

The UI SHALL provide a form for the child's date of birth (from which the age is derived
and shown in **months**), weight in kilograms, sex, optional height in centimetres (marked
as required from 36 months), diet preference chosen from the controlled vocabulary,
allergies chosen from the controlled vocabulary, an optional doctor's note, and activity
level. The form SHALL save these values to the signed-in account with an explicit Save,
SHALL show whether the form matches what is saved, and SHALL load the saved profile on
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

### Requirement: The chat opens as a popup over the page

The UI SHALL present the tabbed page (Child, Feeding log, Daily targets, Growth) as the
full page and the chat as a panel opened by a floating launcher button fixed to the
bottom-right of the viewport. The panel SHALL cover only part of the screen on desktop,
leaving the page usable behind it (full-screen on small viewports is acceptable), and SHALL
offer a close control. Closing and reopening the panel SHALL NOT lose the conversation or a
draft message. The launcher and panel SHALL NOT obscure the popup lists of the page's own
controls.

#### Scenario: Chat starts out of the way

- **WHEN** the parent opens the app
- **THEN** the tabs fill the page, no chat panel is shown, and the launcher button is
  visible at the bottom-right

#### Scenario: The conversation survives closing

- **WHEN** the parent exchanges messages, types a draft, closes the panel, and reopens it
- **THEN** the messages and the unsent draft are still there

#### Scenario: The page stays usable while chatting

- **WHEN** the panel is open on a desktop viewport
- **THEN** the tabs remain visible and operable beside it

### Requirement: Growth assessments render as a structured card in the direct voice

When a response includes a growth-assessment result the UI SHALL render a card with one
row per indicator showing the measurement, the percentile, a marker on a −3 to +3
standard-deviation track, the WHO reference values (−2 SD, median, +2 SD), and WHO's label
when the result carries one; skipped indicators SHALL appear with their reason. The card
SHALL name the standard and its year and SHALL state that the standard is a reference, not
a diagnosis, that preterm birth, birth size, and family background shift where a healthy
child falls, and that the pediatrician interprets the trend. All copy on the card SHALL be
direct: no wordplay about weight or size, no diagnosis, the next step named.

#### Scenario: Four indicators shown

- **WHEN** a result contains four computed indicators
- **THEN** the card shows four rows, each with a percentile, a marker, and reference values,
  and a source line naming the WHO Child Growth Standards (2006)

#### Scenario: Skipped indicator explained

- **WHEN** a result lists BMI-for-age as skipped because no height was supplied
- **THEN** the card shows a BMI-for-age row with the reason naming the missing length or
  height instead of a percentile

#### Scenario: Reference limits stated

- **WHEN** any growth card renders
- **THEN** its note names preterm birth, birth size, and the pediatrician as the one who
  interprets the trend

#### Scenario: WHO label shown plainly

- **WHEN** an indicator's band is outside the expected range and carries a WHO label
- **THEN** the row shows the label as WHO's term and the sentence that follows names the
  pediatrician as the next step, with no playful wording

## ADDED Requirements

### Requirement: A Growth tab records measurements and shows each one on the WHO standards

The UI SHALL provide a Growth tab with a form for a measurement date (defaulting to today
and bounded between the date of birth and today), weight in kilograms, and optional
length/height in centimetres; a list of the child's measurements newest first, each showing
its date, the child's age in months on that date, the weight and any length/height, one
percentile row per computed indicator with the marker on the −3 to +3 track and the WHO
reference values, a plain note when no length/height was recorded, and a control to remove
it; and, once per tab, the WHO source line and the direct-voice trend note the growth card
uses. Adding or removing a measurement SHALL refresh the Child tab's saved weight and
height and the Daily-targets tab. Without a saved child the tab SHALL say to save the
child's details first. All copy on the tab SHALL be direct, with no wordplay about weight or
size.

#### Scenario: First measurement invited

- **WHEN** a saved child has no measurements
- **THEN** the tab shows the form and an empty state inviting today's weight, with height
  if known

#### Scenario: Measurements listed newest first with percentile rows

- **WHEN** two measurements exist, the newer with a length/height and the older without
- **THEN** the newer appears first with four percentile rows, the older second with one
  percentile row and a note that no length or height was recorded, and the source line and
  trend note appear once

#### Scenario: Adding a measurement updates the other tabs

- **WHEN** the parent adds today's measurement with a new weight
- **THEN** it appears at the top of the list and the Child tab's weight and the
  Daily-targets tab reflect the new weight without a reload

#### Scenario: Server rejections are shown verbatim

- **WHEN** the server refuses a measurement (a date before the birth date, or a second one
  for the same day)
- **THEN** the form shows the server's message and keeps the entered values

#### Scenario: No child yet

- **WHEN** the parent opens the Growth tab before saving a child
- **THEN** the tab explains that the child's details come first and fetches nothing
