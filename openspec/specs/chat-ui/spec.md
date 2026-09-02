# chat-ui Specification

## Purpose

The browser application a parent uses: a full-page tabbed layout (child-context form,
feeding log, daily targets), a streamed chat opened as a popup from a floating launcher,
and for every assistant message the sources it cites, the tools it ran, any meal plan it
produced, and the not-medical-advice disclaimer.

## Requirements

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

### Requirement: Answers stream and show their provenance

For each assistant message the UI SHALL show answer text as it streams, an indicator of
the intent (knowledge base, tools, or both), one entry per tool invocation with its
outcome and — on request — its arguments and result, and which arguments came from the
child context.

#### Scenario: Tool activity visible before the answer finishes

- **WHEN** a message routes to tools
- **THEN** tool entries appear before the answer text completes and each shows success or
  failure

#### Scenario: Failed tool explained

- **WHEN** a tool invocation failed
- **THEN** its entry is visibly marked failed and shows the failure message

### Requirement: Citations are shown with source and publication date

The UI SHALL render inline citation markers `[n]` in the answer and a numbered Sources list
beneath it giving each source's title and publication year (hard rule 5), with the cited
passage available on request.

#### Scenario: Sources list

- **WHEN** an answer cites two context blocks
- **THEN** the Sources list has two numbered entries, each with title and year, and the
  answer's `[1]` and `[2]` markers correspond to them

### Requirement: Meal plans render as a structured card

When a response includes a meal-plan result the UI SHALL render a card showing the items
grouped by meal slot with servings and serving size, coverage of calorie, protein, and
iron targets, the excluded foods with their reasons, and — when the doctor's note
overrode a general target — a prominent conflict banner naming both values (hard rule 3).
A no-safe-plan outcome SHALL display the plan's explanatory message prominently.

#### Scenario: Override conflict is unmissable

- **WHEN** the meal-plan result reports a doctor's-note override conflict
- **THEN** the card shows a distinct banner titled "Your doctor's note takes priority
  here" stating the note's value and the general value it replaced, for the nutrient
  concerned

#### Scenario: No safe plan

- **WHEN** the meal-plan result's outcome is no-safe-plan
- **THEN** the card shows the headline "We couldn't build a safe plan with these details —
  here's why, and what you might want to check", a "Here's why" section listing the
  exclusions with reasons, and a "Worth checking" section naming age in months, recorded
  allergies, diet preference, and the pediatrician, instead of items

### Requirement: Every assistant message carries the disclaimer

The UI SHALL display the not-medical-advice disclaimer with every assistant message.

#### Scenario: Disclaimer present

- **WHEN** any assistant message is rendered
- **THEN** the disclaimer text is visible with it

### Requirement: Degraded states are explained

The UI SHALL tell the parent when no child context has been supplied and a tool needed
it, SHALL show the backend's unavailability message when the service reports it is not
configured, and SHALL keep partial answer text and offer a retry when a stream is
interrupted.

#### Scenario: Backend unavailable

- **WHEN** the backend responds that the model provider is not configured
- **THEN** the UI shows a warm "not quite set up yet" message that includes the backend's
  explanation, rather than a generic failure

#### Scenario: Interrupted stream

- **WHEN** the connection drops after some tokens arrived
- **THEN** the received text remains visible, the message is marked incomplete with a warm,
  direct explanation that ends with the next step, and a retry control is offered

#### Scenario: Nothing to show yet

- **WHEN** the parent opens the app with no child details and no messages
- **THEN** the Child tab invites them to tell us about their child and the chat invites a
  first question, each in one warm sentence that ends with what to do

### Requirement: Product copy is warm by default and direct about safety and errors

Every message the product itself writes to the parent — empty states, missing-details
hints, the no-safe-plan headline, the doctor's-note banner, tool failures, interrupted or
unreachable states — SHALL come from a single copy source per side, SHALL address the
parent warmly and without blame, and SHALL end with the next step. Messages about safety,
allergies, a doctor's instruction, or an error SHALL be direct: what happened, what it
means, what to do — with no wordplay. The not-medical-advice disclaimer SHALL remain
verbatim.

#### Scenario: Copy comes from one place

- **WHEN** the frontend is built
- **THEN** no parent-facing string appears outside the copy module, and a snapshot test
  records every string so a change to any one of them is a reviewed change

#### Scenario: Safety stop is direct

- **WHEN** a meal plan was stopped by a safety check
- **THEN** the message says the plan was stopped, that nothing unsafe was shown, that it is
  not the parent's doing, and to try again — without humour

#### Scenario: Missing details are named, not the child

- **WHEN** a tool needed child details that were not supplied
- **THEN** the message points to the side panel and names the missing information; the
  wording never suggests a missing child

### Requirement: The parent can log feeds and see today's intake

The UI SHALL provide a Feeding-log tab with a form to log a feed, a list of logged entries
grouped by day with their nutrients and a way to delete one, and "today so far" totals.
The form SHALL ask only which food, how much, and when: it SHALL NOT ask for a feeding
type — the type is derived from the choice (Breastfed → breast milk; a milk-feed food →
breast milk or formula; the Water entry → water; anything else → solid) and stays within
the controlled vocabulary. "When" SHALL be the five named moments Breakfast, Lunch,
Dinner, Snack, and Breastfed — never a date or time control; each moment maps to a
representative local time on the current day (Breastfed to the current time), since the
tools reduce every timestamp to the local calendar day. The food picker SHALL be a search
box suggesting at most seven matches from the food table plus a single Water entry, with
the quantity unit set from the chosen food. The log SHALL be read from and written to the
signed-in account's child; when no child is saved yet the tab SHALL say so instead of
offering the form.

#### Scenario: Picker offers only table foods

- **WHEN** the parent searches for a food
- **THEN** the suggestions are foods returned by the food listing (plus the Water entry),
  at most seven appear, and no free-text food can be submitted

#### Scenario: Breastfed asks the least

- **WHEN** the parent picks the Breastfed moment
- **THEN** the food search is not shown, the amount may stay blank, and adding the feed
  logs an unmeasured breast-milk feed at the current time

#### Scenario: A moment becomes a sensible time

- **WHEN** the parent logs a food under Lunch
- **THEN** the entry is recorded on today's date at the representative lunch time, and no
  calendar or time field was ever shown

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

### Requirement: Gap reports render as a structured card

When a response includes a gap report the UI SHALL render a card showing the confidence
(or that not enough days are logged), the number of complete days and the window, each
nutrient's average against its target with a `below`/`adequate`/`above` indication, the
targets' sources, and the doctor's-note conflict banner when the report shows one.

#### Scenario: Insufficient data

- **WHEN** the report's status is `insufficient_data`
- **THEN** the card says, warmly, that a few full days of feeds are needed before patterns
  can be seen, invites the parent to keep logging, and shows no flags

#### Scenario: Medium-confidence iron gap

- **WHEN** the report flags iron `below` at `medium` confidence over three days
- **THEN** the card shows the confidence, "3 full days", iron marked "a little short of
  target", and a note that this is an average and a nudge toward iron-rich foods, not a
  verdict

#### Scenario: Excluded days are explained without blame

- **WHEN** the report excluded days because of an unmeasured breastfeed
- **THEN** the card says how many days were left out and that this is normal, not a problem

### Requirement: The meal-plan card shows what informed an adjustment

When a plan carries adjustments or already-logged intake the meal-plan card SHALL show
which nutrient it was adjusted for and why, the already-logged totals, and — for the
`targets_met` outcome — a statement that today's logged feeds already meet the targets.

#### Scenario: Adjusted plan

- **WHEN** the plan's adjustments name iron
- **THEN** the card shows an "adjusted for iron" line with the reason

#### Scenario: Targets met

- **WHEN** the plan's outcome is `targets_met`
- **THEN** the card shows that today is already covered and there is nothing more to plan,
  no items, and the disclaimer

#### Scenario: Empty log invites, not nags

- **WHEN** the Feeding-log tab has no entries
- **THEN** it shows one warm sentence inviting the parent to add a feed whenever they like
  and explaining that more days mean more insight, plus a note that the log is kept in this
  browser for fourteen days

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

### Requirement: A Daily-targets tab shows the child's daily nutrient targets

The UI SHALL provide a Daily-targets tab, alongside the Child and Feeding-log tabs, listing
the child's nutrient targets in the order the server returns them, each with its value,
unit, reference type, age band, and source. The tab SHALL read the signed-in account's
saved child; when no child is saved yet it SHALL say so instead of showing numbers. The UI
SHALL NOT compute, reorder, or round any target itself, since no nutrient number a parent
sees may originate in the browser.

#### Scenario: Targets appear in server order

- **WHEN** the parent opens the Daily-targets tab for a saved 9-month-old
- **THEN** the tab lists the targets in the order received, without client-side sorting
- **AND** each row shows its value with unit, its reference type, and its source

#### Scenario: No child yet

- **WHEN** the account has no saved child and the parent opens the Daily-targets tab
- **THEN** the tab explains that the child's details come first and shows no target values

#### Scenario: Unsaved edits do not produce numbers

- **WHEN** the parent edits the child's age in the form without saving
- **THEN** the Daily-targets tab does not show targets for the unsaved age, and says the
  details must be saved first

#### Scenario: Targets refresh after a profile change

- **WHEN** the parent saves a change to the child's age or diet preference
- **THEN** the Daily-targets tab reflects the saved profile without a page reload

### Requirement: Display-only targets and advisories are visually distinct from tracked ones

A target the system does not compare against logged intake SHALL be rendered with its value
and its parent-facing reason, and SHALL NOT be given a progress indicator or a
below/adequate/above badge. An advisory entry SHALL be rendered as guidance text with its
source and publication date, and SHALL NOT be given a value or a progress indicator.

#### Scenario: Vitamin D shows a reason and no progress bar

- **WHEN** the Daily-targets tab renders vitamin D
- **THEN** it shows the target value and a reason explaining that intake comes from
  supplements and sunlight rather than logged food
- **AND** it renders no progress indicator and no flag badge

#### Scenario: A vegan child's B12 and DHA read as guidance

- **WHEN** the Daily-targets tab renders for a vegan child
- **THEN** vitamin B12 shows its value with supplement guidance and no progress indicator
- **AND** the omega-3 DHA entry shows guidance text with its source and publication date,
  and no value

#### Scenario: A tracked target keeps its progress indicator

- **WHEN** the Daily-targets tab renders calcium for a child with complete logged days
- **THEN** calcium shows its progress against target and its flag
- **AND** exactly one progress track is drawn for that row

### Requirement: The panel says when a doctor's note is on file but not applied to it

Because the Daily-targets tab reports general reference targets rather than note-adjusted
ones, the UI SHALL state when a doctor's note is on file for the child and that the note
is applied when meal plans are generated, so a parent is never left to infer that the note
was ignored (hard rule 3).

#### Scenario: A note on file is disclosed

- **WHEN** the child's profile carries a doctor's note and the parent opens the
  Daily-targets tab
- **THEN** the tab states that a note is on file and that it is applied when planning meals

#### Scenario: No note, no claim

- **WHEN** the child's profile carries no doctor's note
- **THEN** the Daily-targets tab makes no statement about a note

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

### Requirement: The Growth tab plots each indicator over the WHO percentile curves

When the child has at least one measurement, the Growth tab SHALL show, above the list,
four line charts — weight-for-age, length/height-for-age, weight-for-length/height, and
BMI-for-age. Each chart SHALL draw the WHO curves for the child's sex at every tenth
percentile from the 10th to the 90th as thin muted lines, with the 50th percentile drawn
thicker and darker, SHALL label the 10th, 50th, and 90th curves directly, and SHALL draw
the child's measurements as a line with a marker per measurement in the product's accent
colour. Age charts SHALL span 0–24 months for a child under 24 months and 0–60 months
otherwise; the weight-for-length/height chart SHALL span the table's centimetre range and
say whether it is the length or the height table. A measurement without a length/height
SHALL appear on the weight-for-age chart only. Hovering or focusing a marker SHALL show
the measurement's date, value, and percentile. Axes and grid SHALL be recessive, text SHALL
use the page's text colours (never the series colour), and the charts SHALL render
correctly in the dark theme. All copy SHALL be direct, with no wordplay about weight or
size. The newest-first list beneath the charts remains the table view.

#### Scenario: Four charts with nine curves each

- **WHEN** a child with two measurements, one of them without a length/height, opens the
  Growth tab
- **THEN** four charts render, each with nine percentile curves of which the 50th is
  thicker, the weight-for-age chart shows two markers, and the other three show one

#### Scenario: Curves match the child's sex and age range

- **WHEN** the child is a 7-month-old girl
- **THEN** the age charts span 0–24 months and the weight-for-length/height chart says it
  shows the length table

#### Scenario: Marker tooltip

- **WHEN** the parent hovers a marker on the weight-for-age chart
- **THEN** the measurement's date, weight, and percentile are shown

#### Scenario: No measurements, no charts

- **WHEN** a saved child has no measurements
- **THEN** the tab shows the form and the empty state and no chart

#### Scenario: Curves unavailable does not hide the list

- **WHEN** the reference curves cannot be loaded
- **THEN** the tab says the charts are unavailable and the measurement list still renders
