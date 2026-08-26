## 1. Dependency baseline

- [x] 1.1 Add dependencies with `uv add pymilvus langchain langchain-community sentence-transformers langchain-openai` and verify `uv run python -c "import pymilvus, langchain; print('OK')"` succeeds
- [x] 1.2 Add dev deps `uv add --dev pytest-asyncio` (already present) and verify test infrastructure is ready
- [x] 1.3 Configure pytest markers for integration tests in `pyproject.toml` (e.g., `@pytest.mark.integration` for ingestion tests that need Milvus); verify marker is recognized

## 2. Knowledge store abstraction and implementation

- [x] 2.1 Implement `backend/db/knowledge_store.py` with abstract `KnowledgeStore` interface: `search(query, top_k) -> List[Document]` and `upsert(documents, document_id)` (design.md Decision 8); verify abstract methods are present
- [x] 2.2 Implement `backend/db/milvus_knowledge_store.py` wrapping `pymilvus.MilvusClient` against an in-process Milvus Lite instance persisting to `milvus.db` (Decision 4); verify it creates the collection and can upsert a test chunk
- [x] 2.3 Implement lazy initialization of the Milvus connection (only on first use, not at import time) so the app can still boot with no vector DB configured; verify `uv run python -c "from backend.main import app; print('OK')"` succeeds

## 3. Document loading and chunking

- [x] 3.1 Implement `backend/knowledge/loaders.py` with a `load_corpus(corpus_dir)` function using LangChain's `DirectoryLoader` and `TextLoader` (design.md Decision 1); verify it loads Markdown files from a test directory and returns LangChain `Document` objects with metadata
- [x] 3.2 Implement `backend/knowledge/chunker.py` with a `chunk_documents()` function using `RecursiveCharacterTextSplitter` with `chunk_size=512`, `chunk_overlap=50` (Decision 2); verify a 2000-character document is split into ~4 chunks, each with preserved section headers
- [x] 3.3 Implement `backend/knowledge/hashing.py` with a `content_hash(doc_text)` function computing MD5 or SHA256 (Decision 5); verify the same content produces the same hash twice and different content produces a different hash

## 4. Embedding infrastructure

- [x] 4.1 Implement `backend/knowledge/embeddings.py` with an `embed_documents(chunks)` function using OpenRouter embeddings via LangChain (design.md Decision 3); verify it accepts a list of strings and returns a list of embedding vectors
- [x] 4.2 ~~Add a fallback to `sentence-transformers`~~ **Superseded** by day-3-rag-pipeline design.md Decision 3: a silent fallback to a different embedding model mixes incomparable vectors, so the provider is one explicit OpenRouter model with no fallback. Original text: Add a fallback to `sentence-transformers` (all-MiniLM-L6-v2) when OpenRouter is unavailable; verify the function gracefully switches on network error
- [x] 4.3 Write a test that embeds a small set of pediatric nutrition queries and verifies embeddings are non-zero vectors; verify embeddings are deterministic (same input → same vector)

## 5. Ingestion orchestrator

- [x] 5.1 Implement `scripts/ingest.py` as the main entrypoint; orchestration: load corpus → chunk → hash → detect changes → embed new/changed → upsert; verify the script runs without error on an empty corpus
- [x] 5.2 Implement change detection: compute hashes for all loaded docs, query the Milvus collection for existing hashes, and identify documents that are new or changed (Decision 5); verify a re-run with unchanged input skips re-embedding
- [x] 5.3 Implement atomic upsert: delete old chunks for a changed document, insert new chunks (Decision 7); verify a document update replaces all its chunks and no duplicates remain
- [x] 5.4 Implement logging: log document load count, chunk count, embedding times, and upsert results; verify logs are emitted to stdout and include counts (design.md Decision 2)
- [x] 5.5 Implement configuration via environment variables: `MILVUS_DB_PATH` (default: `milvus.db`), `EMBEDDING_MODEL` (default: fallback to sentence-transformers), `CORPUS_DIR` (required); verify the script reads and uses these settings

## 6. Corpus acquisition and population

- [x] 6.1 Acquire and stage curated sources: WHO Child Growth Standards (publicly available), AAP Pediatric Nutrition Handbook (excerpts from public resources), national dietary guidelines (e.g., CDC/USDA guidance); verify at least 15–20 source documents are obtained
- [x] 6.2 Convert documents to Markdown format (by hand if necessary; PDFs can stay as-is if using PDFPlumberLoader); verify all documents are in `knowledge-base/` directory
- [x] 6.3 Write `knowledge-base/manifest.yaml` with entries for each document (source, date, topic, authority); verify YAML is valid and all documents listed in the manifest exist
- [x] 6.4 Run `uv run scripts/ingest.py` on the corpus; verify `milvus.db` is created and the ingestion log reports all documents embedded and upserted

## 7. Test and validation baseline

- [x] 7.1 Create `tests/test_knowledge_base.py` with a small curated set of 10–15 queries and expected retrieval outcomes (e.g., "How much iron should an 8-month-old consume?" should retrieve WHO iron guidelines); verify at least one relevant document is in the top-3 results for each query
- [x] 7.2 Implement a `test_ingestion_is_idempotent()` test: run ingestion, verify results; run again with unchanged input, verify results are identical (same chunk counts, same vectors); verify the test passes
- [x] 7.3 Implement a `test_change_detection()` test: add a new document to the corpus, re-run ingestion, verify only the new document was embedded (not the others); verify the test passes
- [x] 7.4 Write a smoke test that embeds a query and retrieves top-5 results; verify retrieval works end-to-end and results carry source metadata
- [x] 7.5 Verify no duplicate chunks exist in the collection after ingestion; query for chunk count and verify it matches the expected number (roughly corpus_doc_count × 50)

## 8. Integration and smoke tests

- [x] 8.1 Create an integration test that calls `knowledge_store.search()` with a nutrition query and verifies the results are Document objects with `content`, `source`, `date`, and `topic` fields; verify Day 3's retriever can use this interface without modification
- [x] 8.2 Run the full test suite (`uv run pytest`) and verify all tests pass; verify ingestion tests run with `@pytest.mark.integration`
- [x] 8.3 Document the ingestion process in a README or docstring: how to add new sources, how to re-run ingestion, what environment variables are needed; verify documentation is clear enough for Day 3 developer to follow

## 9. Verification and handoff

- [x] 9.1 Verify `milvus.db` is `.gitignored` so it's never committed (it's data, not code); update `.gitignore` if needed
- [x] 9.2 Verify Day 1's PostgreSQL schema and app still work; run `GET /health` and verify it still reports database status correctly
- [x] 9.3 (done in commit 7d099dd, Day 2 close-out) Final commit: code, corpus manifest, tests; verify `git status` shows all expected files and nothing unexpected
