## Purpose

The advanced retrieval stage: it analyses the question for age and topic, translates it
into alternative phrasings, retrieves for every phrasing, fuses and deduplicates the
results, applies metadata filters, and assembles a bounded context for answer generation.

## ADDED Requirements

### Requirement: Query analysis extracts age in months

The system SHALL analyse the question and extract, when present, the child's age as a
range in months (hard rule 1). Ages expressed in years, weeks, or as life-stage words
(newborn, infant, toddler) SHALL be converted to a month range. The extraction result
MUST be a validated structure bounded to 0–60 months, never free text (hard rule 7).

#### Scenario: Age given in months

- **WHEN** the question is "What can my 8-month-old eat?"
- **THEN** the extracted age range is 8–8 months

#### Scenario: Age given in years

- **WHEN** the question is "How much milk should a 2 year old drink?"
- **THEN** the extracted age range is 24–35 months

#### Scenario: Life-stage word

- **WHEN** the question is "When can a toddler have peanut butter?"
- **THEN** the extracted age range covers 12–36 months

#### Scenario: No age mentioned

- **WHEN** the question is "What is fiber?"
- **THEN** no age range is extracted
- **AND** no age filter is applied

### Requirement: Query translation produces alternative phrasings

The system SHALL generate between one and three alternative phrasings of the question
that preserve its meaning, and SHALL retrieve for the original question plus each
alternative. Translation failure MUST degrade to retrieving with the original question
only, never to an error.

#### Scenario: Alternatives are generated and used

- **WHEN** a question is retrieved with the advanced strategy
- **THEN** the retrieval metadata lists the original question and 1–3 alternatives
- **AND** each listed query was issued to the knowledge base

#### Scenario: Translation unavailable

- **WHEN** the language model fails to produce alternatives
- **THEN** retrieval proceeds with the original question only
- **AND** the response is still returned

### Requirement: Multi-query results are fused into one ranking

The system SHALL merge the ranked result lists from all queries into a single ranking in
which a passage returned by several queries ranks above a passage returned by one, all
else equal.

#### Scenario: Passage found by multiple queries ranks higher

- **WHEN** passage A is ranked 3rd by two queries and passage B is ranked 3rd by one query
- **THEN** A precedes B in the fused ranking

### Requirement: Metadata filters narrow retrieval by age range

When an age range is extracted, the system SHALL restrict retrieval to passages whose
applicable age range overlaps it. Filters MUST be constructed only from validated values
(integers, controlled-vocabulary strings), never from user text.

#### Scenario: Age filter excludes non-overlapping guidance

- **WHEN** the extracted age range is 8–8 months
- **THEN** passages that apply only to 24–60 months are not retrieved

#### Scenario: Age filter keeps overlapping guidance

- **WHEN** the extracted age range is 8–8 months
- **THEN** passages that apply to 6–12 months and passages that apply to 0–60 months are
  both eligible

#### Scenario: Filter yields nothing

- **WHEN** the age filter eliminates every passage
- **THEN** the system retries the query without the age filter
- **AND** the retrieval metadata records that the filter was dropped

### Requirement: Near-duplicate passages are removed

The system SHALL remove passages that are identical or near-identical to a higher-ranked
passage before constructing context.

#### Scenario: Same chunk retrieved by two queries

- **WHEN** the same passage appears in results for two queries
- **THEN** it appears once in the context

#### Scenario: Overlapping chunk boundaries

- **WHEN** two passages from the same document share the majority of their text because
  of chunk overlap
- **THEN** only the higher-ranked one is kept

### Requirement: Context is bounded and ordered

The system SHALL assemble context from the fused, deduplicated passages up to a
configurable size budget, in rank order, and SHALL stop adding passages when the budget
would be exceeded. Every passage included in context MUST appear in the citation list.

#### Scenario: Budget is respected

- **WHEN** the fused results total more text than the budget
- **THEN** the context contains the highest-ranked passages that fit
- **AND** the number of passages kept is less than the number retrieved

#### Scenario: Context and citations correspond one to one

- **WHEN** five passages are placed in context
- **THEN** the response has exactly five citations, in the same order
