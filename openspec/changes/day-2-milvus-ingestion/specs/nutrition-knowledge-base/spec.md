## Purpose

A curated corpus of pediatric nutrition guidance indexed and retrievable by semantic
similarity, with full source provenance. This capability is the foundation for the RAG
pipeline that answers nutrition questions and generates meal plans on Days 3 and 4.

## ADDED Requirements

### Requirement: Documents are indexed and retrievable by semantic similarity

The system SHALL embed documents into a vector space and store those embeddings so that
a query can retrieve the most semantically similar documents without requiring keyword
matching.

#### Scenario: Relevant document is retrieved for a nutrition query

- **WHEN** a query "How much iron should an 8-month-old consume?" is submitted
- **THEN** the system retrieves documents about infant iron requirements
- **AND** the top result comes from a recognized source (WHO, AAP, or national guideline)

#### Scenario: Irrelevant documents are ranked low

- **WHEN** a query about infant nutrition is submitted
- **THEN** documents about adult sports nutrition are ranked much lower than relevant ones
- **AND** if adult nutrition is returned at all, it appears beyond the top 5 results

#### Scenario: Query retrieves multiple documents, ranked by relevance

- **WHEN** a query about weaning/complementary feeding is submitted
- **THEN** the system returns multiple documents
- **AND** they are ordered by semantic similarity score
- **AND** the score is available to the caller for confidence assessment

### Requirement: Documents carry full source provenance

The system SHALL store and return enough metadata to construct a complete citation: the
document's original source, publication date, topic/section reference, and authority
level.

#### Scenario: Retrieved document includes citation metadata

- **WHEN** a document is retrieved
- **THEN** the response includes:
  - source title (e.g., "WHO Child Growth Standards 2006")
  - publication date (year at minimum)
  - specific section or page reference (if available)
  - authority level (e.g., "WHO official guideline", "national standard")

#### Scenario: Provenance is not lost during chunking

- **WHEN** a document is split into chunks for embedding
- **THEN** every chunk carries the original document's metadata
- **AND** chunks from different sources are distinguishable

### Requirement: The knowledge base covers the supported age range

The system SHALL include guidance for child nutrition from newborn (0 months) through
approximately 4 years (60 months).

#### Scenario: Guidance exists for every covered age band

- **WHEN** a query is submitted for any age from 0 to 60 months
- **THEN** at least one relevant document is retrievable
- **AND** the document applies to that age range or overlaps it

#### Scenario: Age-specific guidance is retrievable

- **WHEN** a query specifies an age (e.g., "6-month-old")
- **THEN** documents targeted at that age are ranked higher than general guidance

### Requirement: Sources are from recognized pediatric guidelines

The system SHALL accept documents only from authoritative sources: WHO Child Growth
Standards, AAP Pediatric Nutrition, national infant dietary guidelines, and published
pediatric nutrition research.

#### Scenario: Recognized sources are included

- **WHEN** the knowledge base is queried
- **THEN** retrieval results reference at least WHO, AAP, or national guidelines
- **AND** fringe or unvetted sources do not appear in the top results

### Requirement: The knowledge base does not contain contradictions at odds with hard rules

The system SHALL not include documents that recommend practices violating hard rule 4
(no honey under 12 months, no choking hazards, no unpasteurized products), hard rule 5
(citation of source and date), or hard rule 9 (user-scoped data isolation).

#### Scenario: No unsafe recommendations are indexed

- **WHEN** the knowledge base is ingested
- **THEN** no document recommends honey for infants under 12 months
- **AND** no document recommends known choking hazards without appropriate warnings

### Requirement: Retrieval is reasonably fast

The system SHALL return the top-K results within a time budget suitable for inclusion
in a streaming response pipeline.

#### Scenario: Retrieval latency is acceptable for a streaming chat

- **WHEN** a query is embedded and submitted to the knowledge base
- **THEN** the top 5 results are returned within 500ms
- **AND** the latency is consistent across repeated queries
