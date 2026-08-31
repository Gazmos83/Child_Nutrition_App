## MODIFIED Requirements

### Requirement: Answers stream and show their provenance

For each assistant message the UI SHALL show answer text as it streams, an indicator of the
intent (knowledge base, tools, or both), and the work behind the answer: every step the
router planned SHALL appear as soon as routing lands — pending until its result arrives,
then success or failure, and marked as not reached if the stream ends without one — and a
result that arrives without having been planned SHALL still be shown. Each settled step
SHALL be described in words a parent can read as the primary view, with its arguments and
result available on request and a note of which arguments came from the child context. The
step list SHALL stay expanded while work is running or any step failed, and MAY collapse
behind a labelled toggle once a clean answer lands.

Answer text SHALL render the light markdown the answer prompts request — paragraphs,
bulleted and numbered lists, bold, and inline code — without constructing HTML from model
output, staying legible on partial input while streaming. Inline `[n]` markers SHALL anchor
to the Sources list wherever they appear, inside list items and bold text included.

#### Scenario: Tool activity visible before the answer finishes

- **WHEN** a message routes to tools
- **THEN** every planned step appears as pending before any result arrives, and each
  resolves to success or failure as its result lands, before the answer text completes

#### Scenario: Failed tool explained

- **WHEN** a tool invocation failed
- **THEN** its entry is visibly marked failed and shows the failure message, and the step
  list is not collapsed

#### Scenario: Raw data on request

- **WHEN** the parent asks for a settled step's details
- **THEN** the step's arguments and result (or failure detail) are shown, and the primary
  view remains the prose summary

#### Scenario: Lists render as lists

- **WHEN** the answer streams bulleted lines with a citation marker inside one item
- **THEN** the lines render as a real list and the marker anchors to its Sources entry
  exactly as in a paragraph

## ADDED Requirements

### Requirement: Streaming keeps the parent's place

While an answer streams, the UI SHALL keep the view pinned to the newest text only when the
parent is already reading at the bottom of the conversation. When the parent has scrolled
up, arriving tokens SHALL NOT move the view, and a control SHALL be offered to jump back to
the latest message.

#### Scenario: Reading back is not interrupted

- **WHEN** the parent scrolls up while an answer is streaming
- **THEN** the view stays where they are reading as tokens arrive, and a jump-to-latest
  control appears

#### Scenario: Jumping back resumes following

- **WHEN** the parent uses the jump-to-latest control
- **THEN** the view moves to the newest text and follows the stream again
