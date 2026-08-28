# rag-evaluation Specification

## Purpose
How the assistant's retrieval strategies are compared and how its answers are scored: a
reviewed test set spanning every kind of question the product meets, an A/B run of both
retrieval strategies through the public API of the running service, deterministic checks
for retrieval and routing, LLM-judged RAGAs metrics for generation, and a report whose
header lets the numbers be reproduced (reference §12).

## Requirements

### Requirement: The test set covers every category the product meets

The evaluation SHALL use a reviewed, versioned test set of 40 to 60 cases, each tagged with
exactly one category from: basic knowledge-base question, advanced (age- or
multi-condition) knowledge-base question, tool question, knowledge-base plus tool
(hybrid), user-data question (needing a saved child or feeding log), out-of-domain, and
adversarial. Every category SHALL have at least three cases. Each case SHALL carry a
question and the expectations that apply to its category: documents that must be
retrieved, expected intent and tools, a reference answer, phrases that must or must not
appear, or that the fixed no-answer message is the correct outcome.

#### Scenario: Case file validates

- **WHEN** the test set is loaded
- **THEN** it holds 40–60 cases with unique identifiers, every category is represented at
  least three times, every expected document exists in the knowledge-base manifest, and
  every expected tool is one the assistant exposes

#### Scenario: Seed cases retained

- **WHEN** the test set is compared with the Day 3 retrieval-validation questions and the
  out-of-domain probes
- **THEN** every one of those questions appears in it

### Requirement: Both strategies are evaluated through the running service

The evaluation SHALL treat the service as a black box: knowledge-base cases SHALL be sent
to the public question endpoint once per retrieval strategy (`basic`, `advanced`) with
identical inputs, and routing, tool, user-data, and adversarial cases SHALL be sent to the
chat endpoint under an account the evaluation registers for itself, after saving the
case's child and feeding log to that account. The evaluation SHALL NOT import application
code, SHALL NOT read the database directly, and SHALL NOT change prompts, corpus, or
retrieval parameters.

#### Scenario: A/B inputs are identical

- **WHEN** a knowledge-base case runs
- **THEN** the same question is posted twice, differing only in `strategy`, and both answers,
  citation sets, and retrieval statistics are recorded

#### Scenario: Chat cases use a throwaway account

- **WHEN** the chat cases run
- **THEN** the evaluation has registered a fresh account for this run, saved the case's
  child and feeding log to it, and reads nothing belonging to any other account

#### Scenario: Service unchanged by a run

- **WHEN** an evaluation completes
- **THEN** no file under the knowledge base, nutrition data, or application source has
  changed

### Requirement: Retrieval and routing are scored deterministically

For each case and strategy the evaluation SHALL compute, without a model: whether at least
one expected document appears among the citations (hit@K, K = the citations returned);
whether every citation carries a source title and a publication year (hard rule 5);
whether the chat's intent matched the expected intent; whether every expected tool ran with
status `ok`; whether the fixed no-answer message was returned when and only when expected;
whether every must-include phrase appears (a phrase may list alternatives) and no
must-not-include phrase does; and, for cases that forbid foods in a generated meal plan,
whether none of those foods appears among the plan's items — the answer text may still name
them in its explanation of what was excluded and why.

#### Scenario: Retrieval hit

- **WHEN** a case expects `aap-iron-deficiency-2010` and the `advanced` answer cites it
- **THEN** the case scores a retrieval hit for `advanced`

#### Scenario: Out-of-domain handled

- **WHEN** an out-of-domain case receives the fixed no-answer message with no citations
- **THEN** it scores correct; an in-domain case receiving that message scores a miss

#### Scenario: Excluded food named only in the explanation

- **WHEN** a meal plan for a peanut-allergic infant lists "peanut butter" under excluded
  foods and none of its items contain peanut
- **THEN** the plan-items check passes

#### Scenario: Adversarial phrase check

- **WHEN** an adversarial case forbids a phrase (for example, a honey serving suggestion
  for an infant) and the answer contains it
- **THEN** the case fails its must-not-include check and the failure is listed in the report

### Requirement: Generation is scored with RAGAs metrics

For every knowledge-base and hybrid case that received an answer, the evaluation SHALL
compute faithfulness, response relevancy, context precision, and context recall (against
the case's reference answer) using the service's cited passages as the retrieved contexts
and a configurable judge model reached through the same OpenRouter gateway the application
uses. Cases that correctly returned the no-answer message SHALL be excluded from generation
metrics and counted separately.

#### Scenario: Contexts are the service's citations

- **WHEN** a RAGAs sample is built for a case
- **THEN** its retrieved contexts are exactly the citation excerpts the service returned
  for that strategy, in citation order

#### Scenario: Judge is configurable

- **WHEN** a judge model is named in the environment
- **THEN** every RAGAs metric uses it, and the report header records which

### Requirement: The report compares the strategies and can be reproduced

The evaluation SHALL write a Markdown report containing: a header with timestamp, case-set
hash, knowledge-base manifest hash, embedding and chat model ids, relevance floor, judge
model, and case count; per-strategy means for every metric; paired per-case deltas
(`advanced` minus `basic`) with win/tie/loss counts per metric; per-category breakdowns;
and a list of every failed deterministic check naming the case. Raw per-case results SHALL
be written alongside as JSON lines. The baseline report SHALL be committed; raw results
SHALL NOT be.

#### Scenario: Report header

- **WHEN** a run completes
- **THEN** the report begins with the reproducibility header and states how many cases ran
  per strategy and how many were excluded from generation metrics

#### Scenario: Paired comparison

- **WHEN** both strategies ran the same 30 knowledge-base cases
- **THEN** each metric shows a mean per strategy and 30 paired deltas summarised as
  wins/ties/losses for `advanced`

#### Scenario: Bounded run

- **WHEN** the evaluation is started with a case limit, a category filter, or a single
  strategy
- **THEN** only the selected cases and strategies run, and the report header says so
