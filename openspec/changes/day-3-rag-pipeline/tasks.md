Groups 1–4 close out Day 2 (corpus, store, ingestion) and need `OPENROUTER_API_KEY` in
`.env` only from task 4.2 onward. Groups 5–8 build Day 3's RAG pipeline and are
unit-testable offline; group 9 is the live verification. No task touches user-scoped data:
`/api/ask` reads no profile, persists nothing, and takes no identity (see ask-api spec).

## 1. Dependencies and configuration

- [x] 1.1 Run `uv add pyyaml` (manifest parsing is a direct import) and verify `uv run python -c "import yaml, pymilvus, langchain_openai; print('OK')"` succeeds and `git diff uv.lock` shows only the pyyaml addition on top of the already-recorded sentence-transformers removal
- [x] 1.2 Add `RAGSettings` + `get_rag_settings()` to `backend/core/config.py` (design Decision 11: `openrouter_api_key: str | None`, `openrouter_model`, `embedding_model`, `milvus_db_path`, `corpus_dir`, `rag_min_similarity`, `rag_context_char_budget`) and verify new tests in `tests/test_config.py` cover defaults, `.env` isolation, and that `get_rag_settings()` succeeds with no `DATABASE_URL` set
- [x] 1.3 Update `.env.example` with the new variables (commented, defaults shown) and add `milvus.db` to `.gitignore`; verify `git check-ignore milvus.db` prints the path
- [x] 1.4 Generalise the `integration` pytest marker description in `pyproject.toml` to "requires live external services (PostgreSQL, OpenRouter, a populated milvus.db)" and verify `uv run pytest --markers | grep integration` shows it

## 2. Knowledge store and embeddings (Day 2 defects)

- [x] 2.1 Rewrite `backend/knowledge/embeddings.py` around one explicit OpenRouter model (Decision 3): correct base URL `https://openrouter.ai/api/v1`, `check_embedding_ctx_length=False`, `RuntimeError` naming `OPENROUTER_API_KEY` when unset, no local fallback, `dimension` property; verify unit tests assert the error message without a key and that the provider is constructed lazily (no network at import)
- [x] 2.2 Add `SearchFilter` Pydantic model (`age_min_months`/`age_max_months` bounded 0–60 with `min ≤ max`, `authorities` from the `Literal` vocabulary WHO | AAP | CDC | USDA/HHS | NIH | FDA/EPA) and `age_min_months`/`age_max_months`/`section`/`chunk_index`/`content_hash` fields on `Document` in `backend/db/knowledge_store.py`; extend `search()` signature to `search(query, top_k, filter: SearchFilter | None)`; verify tests reject out-of-range ages, min > max, and unknown authorities
- [x] 2.3 Implement collection creation in `MilvusKnowledgeStore` with the typed schema of Decision 4 (VARCHAR deterministic `id`, FLOAT_VECTOR(dim), metadata columns, FLAT/COSINE index) and record `embedding_model` + `dimension` in the collection description; verify a test against a temp `milvus.db` creates the collection once and re-opening with a different model name raises a `RuntimeError` naming both models and `uv run scripts/ingest.py`
- [x] 2.4 Implement `search()` (embeds the query via the injected embedder), `search_by_embedding()` reading hits from `hit["entity"]`, filter rendering from `SearchFilter` only (Decision 5), and `count()` via `get_collection_stats()["row_count"]`; verify tests with a stub embedder against a temp `milvus.db` return `Document`s with scores, honour the age-overlap filter, and never interpolate raw strings into the expression
- [x] 2.5 Implement deterministic ids (`sha256(document_id:chunk_index)[:32]`), `upsert()` as delete-by-`document_id` then insert, `delete()`, and `list_document_hashes() -> dict[document_id, content_hash]`; verify a test ingests a document twice and the id set and row count are unchanged, and a shrunken re-ingest leaves no stale trailing chunks

## 3. Corpus and loader

- [x] 3.1 Fix `backend/knowledge/loaders.py`: replace the unexpanded `**/*.{md,txt}` glob with two passes (or `glob` list) and verify the 4 currently failing tests in `tests/test_knowledge_base.py::TestDocumentLoading` pass
- [x] 3.2 Add manifest loading to `loaders.py`: read `manifest.yaml`, validate entries with a Pydantic `ManifestEntry` (`file, source, year, topic, authority, age_min_months, age_max_months, url`), attach metadata to loaded documents, default missing docs to `source=<stem>, 0–60` with a warning, log an error and skip manifest entries whose file is missing; verify tests cover all three cases
- [x] 3.3 Write `knowledge-base/manifest.yaml` and 15–20 Markdown documents per Decision 12 (WHO complementary feeding, exclusive breastfeeding, growth standards; AAP iron, vitamin D, juice, cow's milk, allergen introduction, choking prevention, honey/botulism; CDC infant/toddler feeding; DGA 2020–2025 birth–24 months; NIH DRI energy/protein/iron/zinc/calcium/vitamin D; FDA/EPA fish; unpasteurised-product safety; hydration; vegetarian/vegan infants), each with `## Section` headings and a stated age range; verify `uv run python -c` loads the manifest, every listed file exists, every `.md` is listed, ages are within 0–60, and no document text recommends honey under 12 months
- [x] 3.4 Write `tests/fixtures/retrieval_validation.yaml` with 12–15 questions → expected `document_id`s (any in top-3), covering iron, complementary feeding start, choking hazards, honey, cow's milk timing, juice, vitamin D, allergen introduction, toddler protein, growth charts, fish/mercury, hydration; verify every referenced `document_id` exists in the manifest

## 4. Ingestion pipeline

- [x] 4.1 Rework `scripts/ingest.py`: load via manifest → chunk (carry `section` from the nearest `##` heading) → hash → compare with `store.list_document_hashes()` → embed only new/changed docs → per-document delete-then-insert → summary log (loaded, unchanged, new, changed, chunks embedded, elapsed); read config from `get_rag_settings()`; verify a test with a stub embedder against a temp `milvus.db` shows run 2 embeds 0 chunks and editing one file re-embeds exactly that document
- [x] 4.2 Run `uv run scripts/ingest.py` against the committed corpus with the real key; verify the log reports all documents embedded, `milvus.db` exists, and `count()` equals the logged chunk total
- [x] 4.3 Run `uv run scripts/ingest.py` a second time; verify the log reports 0 new / 0 changed and the row count is unchanged
- [x] 4.4 Add `tests/test_retrieval_validation.py` (`@pytest.mark.integration`, skipped without key + `milvus.db`) that runs the validation set through `store.search(top_k=3)`; verify every question has an expected document in the top 3, and record the min/max top-1 cosine scores in the test log to inform the relevance floor

## 5. RAG core (offline-testable)

- [x] 5.1 Create `backend/rag/prompts.py` with `SYSTEM_PROMPT`, `NO_ANSWER_MESSAGE`, `DISCLAIMER`, `TRANSLATE_PROMPT`, and `build_context(chunks, budget) -> (context_text, citations)` per Decisions 8 and 14; verify tests assert the system prompt contains the tone constraints (answer first, plain language, explain terms, cite `[n]`, only from context, never compute per-child quantities), the no-answer message mentions birth to about four years and the pediatrician, and `build_context` respects the budget with citations 1:1 in order
- [x] 5.2 Create `backend/rag/query_analysis.py`: deterministic `extract_age_range(question) -> AgeRange | None` (Decision 2: months, `N-month-old`, years → full span, weeks, newborn/infant/baby/toddler/preschooler) and verify parametrised tests cover the four spec scenarios plus "18 months", "2-year-old", "3 weeks", "4 year old" (capped at 60), and no false positives on "6 months ago I…" is documented as accepted
- [x] 5.3 Create `backend/rag/retrievers.py`: `RetrievalResult`, `Retriever` protocol, `BasicRetriever` (single query, top-K) and verify tests with `tests/fixtures/InMemoryKnowledgeStore` (token-overlap scoring) show one query in metadata and ranked results
- [x] 5.4 Implement `AdvancedRetriever`: age extraction → `SearchFilter` → translation via the injected chat model (1–3 alternatives, failure → original only) → multi-query search → RRF (k=60) → dedup (id, then ≥80 % containment within a document) → filter-dropped retry → `top_k_final`; verify tests using `GenericFakeChatModel` cover: alternatives recorded, translation failure degrades, RRF ordering scenario (A in two lists beats B in one), duplicate id removed, overlapping chunk removed, filter dropped and flagged when it empties results
- [x] 5.5 Create `backend/rag/pipeline.py`: `RagPipeline.answer(question, strategy) -> RagResponse` and `RagPipeline.stream(question, strategy)` (async generator of tokens then final response) applying the relevance floor → no-answer path (no model call) or context + prompt → model; verify tests show the no-answer path yields `NO_ANSWER_MESSAGE`, empty citations, the disclaimer, and zero fake-model invocations; the answer path returns citations matching context blocks; and the prompt sent to the fake model is byte-identical for both strategies given the same chunks
- [x] 5.6 Create `backend/rag/llm.py` with `build_chat_model(settings)` → `ChatOpenAI` against OpenRouter (Decision 9) and `build_pipeline(strategy)` wiring settings → embedder → `MilvusKnowledgeStore` → retriever → pipeline, lazily cached per process; verify a test with no key raises a `RuntimeError` naming `OPENROUTER_API_KEY` and that importing `backend.rag` performs no network call

## 6. API

- [x] 6.1 Create `backend/schemas/rag.py`: `AskRequest` (`question` 1–2000 chars after strip, `strategy: Literal["basic","advanced"] = "advanced"`, `stream: bool = True`), `Citation`, `RetrievalMeta`, `AskResponse` (exactly answer, citations, disclaimer, strategy, retrieval); verify schema tests reject blank and over-long questions and unknown strategies
- [x] 6.2 Create `backend/api/ask.py` with `POST /api/ask`: 503 naming `OPENROUTER_API_KEY` when unconfigured; `stream: false` → `AskResponse`; `stream: true` → `StreamingResponse(text/event-stream)` emitting `token`* → `citations` → `done`, or `error` on mid-stream failure (Decision 10); mount on `api_router`; verify tests with a dependency-overridden fake pipeline cover 422 (blank, bad strategy), 503, JSON shape, SSE ordering, concatenated tokens == answer, no-answer streamed with empty citations, and `error` without `done`
- [x] 6.3 Update `tests/test_app.py`: documented surface becomes `{"/health", "/api/ask"}`, `test_api_router_is_mounted_but_empty` becomes "mounted with only `/api/ask`", user-scoped-path guard unchanged; verify `uv run pytest tests/test_app.py` passes and `GET /health` still returns 200 with no RAG or DB configuration

## 7. Documentation and Day 2 close-out

- [x] 7.1 Update `README.md` Development section: how to set `OPENROUTER_API_KEY`, run `uv run scripts/ingest.py`, add a corpus document (file + manifest entry + re-run), and call `POST /api/ask` (curl for JSON and for SSE); verify the commands in the README run as written
- [x] 7.2 Tick Day 2 `openspec/changes/day-2-milvus-ingestion/tasks.md` items completed here (1.x, 2.x, 3.x, 4.1, 4.3, 5.x, 6.x, 7.x, 8.x, 9.1, 9.2) and mark 4.2 (local fallback) as superseded by this change's Decision 3 with a one-line note; verify `openspec status --change day-2-milvus-ingestion` reflects the update

## 8. Full offline verification

- [x] 8.1 Run `uv run ruff check .` and `uv run ruff format --check backend scripts tests`; verify zero findings
- [x] 8.2 Run `uv run pytest` with `OPENROUTER_API_KEY` unset and no `milvus.db`; verify all non-integration tests pass and integration tests report as skipped (not failed)

## 9. Live verification (requires key + populated `milvus.db`)

- [x] 9.1 Verify `OPENROUTER_MODEL` and `EMBEDDING_MODEL` defaults exist in `curl https://openrouter.ai/api/v1/models` output; adjust the defaults in `RAGSettings` and `.env.example` if not
- [x] 9.2 Run `uv run pytest -m integration`; verify the validation set passes for both `basic` and `advanced` strategies and one end-to-end `POST /api/ask` (`stream: false`) returns a cited answer with the disclaimer
- [x] 9.3 Tune `rag_min_similarity`: probe 5 out-of-domain questions ("capital of France", "adult keto diet", "car insurance", "Python list comprehension", "marathon training") and verify all return the no-answer message while every validation question still answers; record the chosen floor and the score ranges in `design.md` Decision 7
- [x] 9.4 Spot-check tone on 5 validation answers (answer-first, plain language, term explained on first use, `[n]` citations present, disclaimer attached, no computed per-child quantities); verify against the checklist in Decision 14 and record any prompt wording adjustment in `design.md`
- [x] 9.5 Start the app with `uv run uvicorn backend.main:app` and verify a `curl -N` SSE request to `/api/ask` streams tokens followed by `citations` and `done`, and `GET /health` still answers
