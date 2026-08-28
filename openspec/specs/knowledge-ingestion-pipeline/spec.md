# knowledge-ingestion-pipeline Specification

## Purpose

An idempotent, re-runnable job that loads documents from the curated corpus, embeds them,
and upserts into Milvus. This capability enables real-time knowledge updates: new sources
can be added to the corpus, and the ingestion script can be re-run to pick up changes
without a full rebuild.

## Requirements

### Requirement: Ingestion is idempotent

Running the ingestion pipeline twice with the same input documents SHALL produce the same
final state: all documents are indexed exactly once, and no duplicates or partial state
remain.

#### Scenario: Re-running with unchanged input leaves state unchanged

- **WHEN** the ingestion pipeline is run twice with the same source documents
- **THEN** the Milvus collection contains the same documents both times
- **AND** running a query before and after the second run returns identical results

#### Scenario: Duplicate documents are not double-indexed

- **WHEN** a document already in the collection is ingested again
- **THEN** the collection contains exactly one instance of that document
- **AND** no separate embedding or vector duplicate exists

#### Scenario: Partial ingestion failure does not corrupt the collection

- **WHEN** the ingestion pipeline fails partway through (e.g., a network error during embedding)
- **THEN** the collection is left in a valid state
- **AND** re-running the pipeline completes the work without data loss or duplication

### Requirement: New or changed documents are detected and re-embedded

The pipeline SHALL compare the input corpus against the current collection state and
re-embed only documents that are new or have changed.

#### Scenario: New document is ingested on second run

- **WHEN** a new document is added to the corpus and the pipeline is re-run
- **THEN** only the new document is processed
- **AND** the pipeline completes faster than a full rebuild would

#### Scenario: Changed document is detected and updated

- **WHEN** a document's content changes (e.g., WHO publishes a revision)
- **THEN** the pipeline detects the change (via checksum or modification time)
- **AND** the old embedding is replaced with a new one
- **AND** queries return results using the updated content

#### Scenario: Unchanged documents are not re-processed

- **WHEN** the pipeline is run with 100 documents, 50 of which are unchanged
- **THEN** the unchanged 50 are not re-embedded
- **AND** the pipeline runs faster on the second run than the first

### Requirement: Upserts preserve referential integrity and metadata

When a document is updated, all its chunks SHALL be atomically replaced so queries see a
consistent snapshot.

#### Scenario: Updated document chunks are atomically replaced

- **WHEN** a document is updated and its chunks are re-embedded
- **THEN** queries see either the old document's chunks or the new ones, never a mix

#### Scenario: Metadata is preserved and updated correctly

- **WHEN** a document's metadata (e.g., source date) is updated
- **THEN** all chunks reflecting the new metadata are stored
- **AND** old chunks with the outdated metadata are removed

### Requirement: Ingestion accepts documents from the filesystem

The pipeline SHALL load documents from a directory (or directory tree) without requiring
manual parsing or transformation.

#### Scenario: Markdown documents are loaded

- **WHEN** Markdown files are placed in `knowledge-base/`
- **THEN** the pipeline loads and processes them without manual conversion

#### Scenario: Metadata is extracted from document headers or a manifest

- **WHEN** documents are loaded
- **THEN** the pipeline extracts or reads source, date, and topic metadata
- **AND** missing metadata is flagged as a warning, not an error (so ingestion can proceed with partial metadata)

### Requirement: Ingestion logs actions and failures clearly

The pipeline SHALL emit structured logs identifying which documents were processed,
which failed, and why.

#### Scenario: Successful ingestion is logged

- **WHEN** documents are ingested successfully
- **THEN** logs show document names, embedding times, and counts upserted

#### Scenario: Failures are logged with context

- **WHEN** a document fails to embed (e.g., embedding service unavailable)
- **THEN** the log names the document, the error, and what the operator should do next

#### Scenario: Operator can see the final state

- **WHEN** ingestion completes
- **THEN** logs show the total document count, chunk count, and any skipped/failed documents

### Requirement: Configuration is environment-driven

The pipeline SHALL read Milvus connection details and embedding model configuration from the
environment, so it can adapt to different deployments (local dev, test, prod).

#### Scenario: Ingestion runs with configured Milvus connection

- **WHEN** `MILVUS_URL` is set to a Milvus instance
- **THEN** the pipeline connects and upserts to that instance

#### Scenario: Ingestion uses a configured embedding model

- **WHEN** `EMBEDDING_MODEL` is set (e.g., to an OpenRouter model ID or a local model)
- **THEN** the pipeline uses that model for embedding
- **AND** authentication tokens (if required) are read from the environment

### Requirement: The manifest is the source of document metadata

The pipeline SHALL read `knowledge-base/manifest.yaml` and attach each listed document's
source title, publication year, topic, authority, and applicable age range (months) to
every passage produced from it. A document present in the corpus but absent from the
manifest SHALL be ingested with a warning and default metadata; a manifest entry whose
file is missing SHALL be reported as an error and skipped.

#### Scenario: Manifest metadata reaches passages

- **WHEN** the manifest lists a document with source "WHO Complementary Feeding Guidance",
  year 2023, and age range 6–23 months
- **THEN** every passage from that document carries that source, year, and age range

#### Scenario: Document missing from manifest

- **WHEN** a Markdown file exists in the corpus with no manifest entry
- **THEN** the pipeline logs a warning naming the file
- **AND** ingests it with the file name as source and age range 0–60

#### Scenario: Manifest entry with missing file

- **WHEN** the manifest lists a file that does not exist
- **THEN** the pipeline logs an error naming the file
- **AND** continues with the remaining documents

### Requirement: One embedding model, used consistently

The pipeline SHALL use exactly the configured embedding model and SHALL NOT fall back to a
different model. The collection SHALL record the model name and vector dimension it was
built with; opening the collection with a different configured model MUST fail with a
message instructing the operator to re-run ingestion.

#### Scenario: Provider unavailable

- **WHEN** the embedding provider cannot be reached or is not configured
- **THEN** ingestion stops with an error naming the provider and the required setting
- **AND** no passages are written with vectors from another model

#### Scenario: Model changed since ingestion

- **WHEN** the collection was built with model A and the configured model is B
- **THEN** searching fails with a message naming both models and the re-ingestion command

### Requirement: Ingestion is verifiable end to end

The pipeline SHALL be runnable against the committed corpus by a single command, and the
resulting collection SHALL satisfy a committed validation set of questions, each of which
names the document(s) expected among the top results.

#### Scenario: Validation set passes after ingestion

- **WHEN** ingestion completes against the committed corpus and the validation set is run
- **THEN** for every validation question, at least one expected document appears in the
  top three results
