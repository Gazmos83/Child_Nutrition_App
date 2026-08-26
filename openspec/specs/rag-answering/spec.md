# rag-answering Specification

## Purpose

A grounded answer to a child-nutrition question, generated only from retrieved
knowledge-base passages, written in plain, concise, direct language, carrying source
citations with publication dates and the not-medical-advice disclaimer — or, when the
knowledge base has nothing relevant, a warm, calm explanation of why it cannot answer.

## Requirements

### Requirement: Answers are grounded in retrieved passages

The system SHALL generate answers only from knowledge-base passages retrieved for the
question, and SHALL instruct the language model not to draw on knowledge outside those
passages. The system SHALL NOT compute or invent per-child nutrient quantities; numeric
figures in an answer MUST appear in the retrieved passages.

#### Scenario: Answer reflects retrieved guideline text

- **WHEN** a user asks "How much iron does a 9-month-old need each day?" and a retrieved
  passage states the daily iron recommendation for 7–12 months
- **THEN** the answer states that figure
- **AND** the answer attributes it to the passage's source

#### Scenario: Model is constrained to the provided context

- **WHEN** an answer is generated
- **THEN** the prompt sent to the language model contains the retrieved passages as
  numbered context blocks
- **AND** the prompt instructs the model to answer only from those blocks and to say when
  they do not contain the answer

### Requirement: Every answer carries citations with source and publication date

The system SHALL return, alongside the answer text, a structured list of citations. Each
citation MUST include the source title and publication year, and SHALL include the topic
and section reference when the knowledge base has them (hard rule 5).

#### Scenario: Citations accompany a grounded answer

- **WHEN** an answer is generated from three retrieved passages drawn from two documents
- **THEN** the response includes a citation for each passage used as context
- **AND** each citation has a non-empty source title and a publication year

#### Scenario: Citations are numbered to match the answer

- **WHEN** the answer text refers to a context block by number (e.g., "[2]")
- **THEN** the citation list contains an entry with that number
- **AND** the numbering in the citation list matches the order of context blocks given to
  the model

### Requirement: Every answer carries the not-medical-advice disclaimer

The system SHALL attach a disclaimer to every response — grounded answer or no-answer
message — stating that the information is not medical advice and that a pediatrician
should be consulted. The disclaimer text SHALL be a fixed string that the language model
never generates or rephrases.

#### Scenario: Disclaimer on a grounded answer

- **WHEN** any answer is returned
- **THEN** the response includes a disclaimer field with the fixed not-medical-advice text

#### Scenario: Disclaimer on a no-answer response

- **WHEN** the system cannot answer because nothing relevant was retrieved
- **THEN** the response still includes the same fixed disclaimer

### Requirement: The system explains when it cannot answer

The system SHALL apply a minimum relevance threshold to retrieved passages. When no
passage meets it, the system SHALL return a fixed no-answer message with an empty
citation list, and SHALL NOT ask the language model to answer. The message MUST be warm,
calm, and concise; MUST explain why the question cannot be answered — the assistant's
sources are pediatric nutrition guidelines covering birth to about four years, and the
question falls outside what they cover; and MUST point the parent to their pediatrician.

#### Scenario: Out-of-domain question

- **WHEN** a user asks "What is the capital of France?"
- **THEN** the response is the fixed no-answer message
- **AND** the message explains that the assistant's sources cover child nutrition from
  birth to about four years
- **AND** the citation list is empty
- **AND** no answer-generation call is made to the language model

#### Scenario: In-domain question with sufficient context

- **WHEN** a user asks about complementary feeding and at least one passage meets the
  threshold
- **THEN** an answer is generated from the passages that meet it

### Requirement: Answers use plain, concise, direct language

The system SHALL instruct the language model to write for a parent, not a clinician: lead
with the answer, then the supporting context; use short paragraphs and lists for
enumerations; explain a technical term (e.g., "complementary feeding") the first time it
is used; state safety points firmly without alarm or judgment; omit filler and
restatement of the question.

#### Scenario: Answer-first structure

- **WHEN** an answer is generated
- **THEN** the prompt sent to the language model instructs it to state the answer first
  and keep the response concise
- **AND** the prompt instructs it to explain technical terms on first use

#### Scenario: Prompt is identical across strategies

- **WHEN** the same passages are used as context under the `basic` and `advanced`
  strategies
- **THEN** the prompt sent to the language model is identical

### Requirement: Two retrieval strategies produce comparable answers

The system SHALL expose a strategy selector with the values `basic` and `advanced`. Both
strategies SHALL share the same answer-generation step, differing only in how passages
are retrieved, so that differences in answer quality are attributable to retrieval.

#### Scenario: Strategy is selectable per question

- **WHEN** the same question is asked once with `basic` and once with `advanced`
- **THEN** each response reports which strategy produced it
- **AND** both responses have the same shape (answer, citations, disclaimer, metadata)

#### Scenario: Default strategy

- **WHEN** no strategy is specified
- **THEN** the system uses `advanced`

### Requirement: Retrieval activity is reported

The system SHALL return, with each answer, retrieval metadata sufficient for evaluation
and for Day 5's tool-activity display: the strategy used, the queries issued to the
knowledge base, any filters applied, the number of passages retrieved, and the number kept
as context.

#### Scenario: Metadata on a basic-strategy answer

- **WHEN** a question is answered with the `basic` strategy
- **THEN** the metadata lists exactly one query (the original question)
- **AND** no filters

#### Scenario: Metadata on an advanced-strategy answer

- **WHEN** a question is answered with the `advanced` strategy
- **THEN** the metadata lists the original question and every translated query issued
- **AND** it lists any metadata filters applied
