## ADDED Requirements

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
