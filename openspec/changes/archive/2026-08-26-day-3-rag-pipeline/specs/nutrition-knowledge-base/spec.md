## ADDED Requirements

### Requirement: Search accepts a natural-language query

The knowledge base SHALL accept a text query and return the most similar passages,
embedding the query itself with the same model used at ingestion. Callers MUST NOT need
to compute embeddings.

#### Scenario: Text query returns ranked passages

- **WHEN** a caller searches for "introducing allergenic foods" with top-K of 5
- **THEN** up to five passages are returned, highest similarity first
- **AND** each passage carries a similarity score

### Requirement: Search supports metadata filtering

The knowledge base SHALL accept an optional filter restricting results to passages whose
applicable age range (in months) overlaps a requested range and/or whose authority is in
a requested set. Filter values MUST be validated integers or controlled-vocabulary
strings; free text MUST be rejected.

#### Scenario: Age-range filter

- **WHEN** a caller searches with an age filter of 6–8 months
- **THEN** every returned passage has an applicable age range overlapping 6–8 months

#### Scenario: Invalid filter value

- **WHEN** a caller supplies an age bound outside 0–60 or an authority not in the
  controlled vocabulary
- **THEN** the search is rejected with a validation error
- **AND** no query is sent to the vector store

### Requirement: Every passage records its applicable age range

Every indexed passage SHALL carry the minimum and maximum age in months (0–60) to which
its source document applies, taken from the document's manifest entry; documents without
a declared range SHALL be recorded as applying to 0–60 months.

#### Scenario: Age range is present on retrieved passages

- **WHEN** any passage is retrieved
- **THEN** it reports an age range with 0 ≤ min ≤ max ≤ 60

### Requirement: Passage identity is stable across ingestion runs

Every passage SHALL have an identifier derived deterministically from its document and
position, so that re-ingesting an unchanged document reproduces the same identifiers and
never creates duplicates.

#### Scenario: Re-ingestion preserves identifiers

- **WHEN** an unchanged document is ingested twice
- **THEN** the set of passage identifiers after the second run equals the set after the
  first
