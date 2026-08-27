## Purpose

The browser application a parent uses: a child-context form, a streamed chat, and for every
assistant message the sources it cites, the tools it ran, any meal plan it produced, and the
not-medical-advice disclaimer.

## ADDED Requirements

### Requirement: The parent supplies child context through a controlled form

The UI SHALL provide a form for the child's age in **months** (0–60, labelled as months),
weight in kilograms, sex, optional height in centimetres (marked as required from 36
months), diet preference chosen from the controlled vocabulary, allergies chosen from the
controlled vocabulary, an optional doctor's note, and activity level. The form SHALL send
these values with every message and SHALL remember them in the browser between visits.
Free-text entry for allergies or diet preference SHALL NOT be possible.

#### Scenario: Age is entered in months

- **WHEN** the parent views the age field
- **THEN** it is labelled in months, accepts 0–60, and offers no years entry

#### Scenario: Allergies are a fixed list

- **WHEN** the parent records allergies
- **THEN** they choose from the nine controlled-vocabulary allergens and cannot type a
  custom one

#### Scenario: Context persists across reloads

- **WHEN** the parent fills the form and reloads the page
- **THEN** the form shows the same values

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
- **THEN** the side panel invites them to tell us about their child and the chat invites a
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
