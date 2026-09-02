# intent-routing Specification

## Purpose

Decides, for each parent message, whether the answer comes from the pediatric-guideline
knowledge base, from the deterministic nutrient tools, or from both, then executes that
decision deterministically with the request-supplied child context as the source of truth.

## Requirements

### Requirement: Each message is routed to knowledge base, tools, or both

The system SHALL classify every message into exactly one intent — `rag` (answer from the
knowledge base), `tool` (answer from deterministic tools), or `hybrid` (both) — using a
single language-model decision that selects zero or more capabilities to invoke. The
selection SHALL be executed by application code; the model SHALL NOT execute anything
itself.

#### Scenario: General guideline question routes to the knowledge base

- **WHEN** a parent asks "What is complementary feeding?"
- **THEN** the intent is `rag`, the knowledge base is searched, and no nutrient tool runs

#### Scenario: Child-specific number routes to a tool

- **WHEN** a parent with child context supplied asks "How much protein does my child need?"
- **THEN** the intent is `tool`, the protein-target tool runs, and the knowledge base is
  not searched

#### Scenario: Number plus reasoning routes to both

- **WHEN** a parent asks "Why is iron important at this age and how much does mine need?"
- **THEN** the intent is `hybrid`, the knowledge base is searched and the relevant tool runs,
  and the answer draws on both

#### Scenario: No capability selected falls back to the knowledge base

- **WHEN** the routing decision selects no capability
- **THEN** the message is answered through the knowledge-base path using the original
  message as the query, so an out-of-domain message receives the existing no-answer
  message rather than an ungrounded reply

### Requirement: Answers are never the model's unsupported free text

The system SHALL compose every answer from retrieved context blocks, validated tool
results, or both. Text the model produces during routing SHALL NOT be returned to the
user as an answer.

#### Scenario: Routing text is discarded

- **WHEN** the routing decision includes free text alongside or instead of capability calls
- **THEN** that text is not present in the answer delivered to the user

#### Scenario: Numbers come only from tools

- **WHEN** an answer states a nutrient quantity for the child
- **THEN** that quantity appears verbatim in a tool result included in the same response

### Requirement: Request-supplied child context is authoritative for tool arguments

When the request carries child context, the system SHALL fill every profile-backed tool
argument (age in months, weight, sex, height, allergies, diet preference, doctor's note,
activity level) from that context, SHALL replace any conflicting value proposed by the
model, and SHALL record which arguments were taken from the context. Ages SHALL be in
months (hard rule 1); allergies and diet preference SHALL be controlled-vocabulary values
(hard rule 2).

#### Scenario: Model-proposed weight is overridden

- **WHEN** the child context says 8.5 kg and the model proposes `weight_kg = 9`
- **THEN** the tool runs with 8.5 kg and the tool activity lists `weight_kg` as taken from
  the child context

#### Scenario: Missing context is reported, not guessed

- **WHEN** no child context is supplied and the model proposes a tool call lacking a
  required argument
- **THEN** the tool is not run with invented values; the tool activity reports a validation
  error with a warm, direct message pointing the parent to the side panel and what to fill
  in — it names the missing information, never "a missing child"

#### Scenario: Off-vocabulary allergy is rejected

- **WHEN** the request's child context names an allergy outside the controlled vocabulary
- **THEN** the request is rejected before routing with a validation error

### Requirement: Tool invocations are bounded and validated

The system SHALL run at most four tool invocations per message in a single routing round,
SHALL validate every invocation's arguments before running it (hard rule 7), and SHALL
treat any dropped invocations as a logged event.

#### Scenario: Excess invocations are dropped

- **WHEN** the routing decision proposes six tool invocations
- **THEN** only the first four run, and the dropped two are recorded in the log

#### Scenario: Invalid arguments never reach a tool

- **WHEN** the routing decision proposes an age of 72 months
- **THEN** the tool does not execute and the activity record shows a validation error

### Requirement: Tool failures are surfaced and do not abort the response

The system SHALL report each tool invocation's outcome as success or failure with a
message, SHALL continue composing the answer when one invocation fails, and SHALL make the
failure visible in the answer.

#### Scenario: Unknown food

- **WHEN** a food-lookup invocation names a food that is not in the food table
- **THEN** the activity record marks that invocation failed with the unknown identifier,
  the remaining invocations still run, and the response completes normally

### Requirement: Follow-up messages are resolved from bounded history

The system SHALL accept up to twelve prior turns of conversation history with the message
and SHALL use them to resolve references in the current message when choosing capabilities
and forming the knowledge-base query. History SHALL NOT be persisted by the system.

#### Scenario: Pronoun resolved from history

- **WHEN** the previous turn discussed iron for an 8-month-old and the parent now asks
  "and calories?"
- **THEN** the routing decision addresses calories for the same child rather than asking
  what "and calories" refers to

#### Scenario: Over-long history is rejected

- **WHEN** a request carries thirteen prior turns
- **THEN** the request is rejected with a validation error

### Requirement: Every routing decision is logged

The system SHALL emit one structured log record per message containing the intent, the
proposed and executed capabilities with their outcomes, knowledge-base retrieval
statistics when retrieval ran, the message length, and end-to-end latency, carrying the
request's correlation identifier; and SHALL emit one record per tool invocation with the
tool name, outcome, latency, and which arguments were filled from context. The message
text itself SHALL NOT be logged.

#### Scenario: Log record present

- **WHEN** any message is processed, successfully or not
- **THEN** a log record with intent, capabilities, outcomes, message length, and latency is
  emitted, carrying the request id

#### Scenario: One record per tool invocation

- **WHEN** the router runs two tools for a message
- **THEN** two tool records are emitted, each with its own latency and outcome, before the
  routing summary

### Requirement: Growth questions about the parent's child route to the growth tool

A message asking where the parent's own child sits on a growth chart — their percentile,
their BMI, or whether their weight or length is normal for their age — SHALL route to the
growth-assessment tool (alone, or alongside the guideline search when the parent also
asks what the result means). Child arguments SHALL be filled from the request's child
context as for every other tool; a missing length/height SHALL NOT be treated as a
failure, because the tool computes what it can.

#### Scenario: BMI question with child context

- **WHEN** the parent asks "what's her BMI?" with child context supplied
- **THEN** the routing decision includes the growth-assessment tool

#### Scenario: Growth question without a height

- **WHEN** the parent asks whether their child's weight is normal for their age and the
  child context has no height
- **THEN** the growth-assessment tool runs successfully with weight-for-age only and the
  tool entry reports success, not failure

#### Scenario: Growth question without child context

- **WHEN** the parent asks for their child's percentile and no child context is supplied
- **THEN** the response carries the existing missing-details hint pointing to the side
  panel

### Requirement: A quantified single-food question routes to the food lookup with its amount

When the parent asks about the nutrients of one food, the router SHALL invoke the food
lookup with the food's name alone as the food argument — never an amount or the question's
wording — and, when the parent names an amount, SHALL pass it as a separate quantity with
its unit. The answer SHALL state the figures for the requested amount when the tool returns
them and the per-serving figures otherwise, naming the serving; the model SHALL NOT scale
between the two itself.

#### Scenario: Food with an amount

- **WHEN** the parent asks "what are the nutritional values for 20 g of sweet potato"
- **THEN** the food lookup runs with a food argument naming only the sweet potato and a
  quantity of 20 with unit `g`
- **AND** the answer leads with the figures the tool returned for 20 g

#### Scenario: Food without an amount

- **WHEN** the parent asks "what's in a serving of avocado"
- **THEN** the food lookup runs with no quantity
- **AND** the answer gives the per-serving figures and names the serving size

#### Scenario: Several foods with amounts

- **WHEN** the parent asks about "150 ml of formula plus 30 g of cereal"
- **THEN** the meal-nutrition tool runs with one item per food, each carrying its own
  quantity and unit
