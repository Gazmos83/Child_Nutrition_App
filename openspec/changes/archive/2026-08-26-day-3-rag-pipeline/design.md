## Context

See proposal.md — Why. The state this design starts from:

- Day 2 shipped `KnowledgeStore` (abstract), `MilvusKnowledgeStore` (partial: no
  collection creation, `search()` raises `NotImplementedError`, row ids come from Python's
  per-process-randomised `hash()`, `count()` calls a method `MilvusClient` does not have,
  hits are read as flat dicts when pymilvus nests fields under `entity`), `EmbeddingProvider`
  (points at `openrouter.io` — the real host is `openrouter.ai` — and silently falls back
  to a 384-dimension local model when no key is set), loaders (glob `**/*.{md,txt}` is not
  expanded by the underlying matcher, so `.md` files are missed), chunker (fine), hashing
  (fine), and `scripts/ingest.py` (embeds everything every run; change detection and
  atomic replace are not implemented). `knowledge-base/` does not exist. 97 of 101 tests
  pass; the 4 failures are the loader glob.
- `sentence-transformers` was removed from the project (torch + CUDA pulled ~650 lock
  entries); the uncommitted `uv.lock` reflects the removal. There is no local embedding
  model and this design does not want one.
- OpenRouter serves embeddings at `/api/v1/embeddings` (33 models, including
  `openai/text-embedding-3-small`, verified 2026-08-26), so Day 2 Decision 3 — one
  provider, one credential — holds without the fallback.
- `pymilvus` 3.0.1 with in-process Milvus Lite. `MilvusClient.search()` returns
  `list[list[dict]]` where each hit is `{"id", "distance", "entity": {...fields}}`;
  filters are string expressions; `get_collection_stats()["row_count"]` gives counts.
- LangChain 1.x / `langchain-openai` 1.x. `ChatOpenAI(base_url=..., api_key=...)` works
  against OpenRouter's OpenAI-compatible API; `OpenAIEmbeddings` likewise (with
  `check_embedding_ctx_length=False`, since OpenRouter does not accept pre-tokenised
  input).
- `Settings` requires `DATABASE_URL`, and `get_settings()` raises without it. RAG must not
  inherit that requirement: unit tests for retrieval should run with no database and no
  network, and the app must boot with no RAG configuration.
- Day 5 will call this pipeline from a router and render citations + "tool activity";
  Day 6 will run RAGAs over both strategies. Those two consumers fix the output shape and
  require the generation step (prompt, tone, model) to be frozen today.

## Goals / Non-Goals

**Goals:**

- One pipeline entry point, `answer(question, strategy) -> RagResponse`, with the two
  strategies differing *only* in retrieval, so Day 6's A/B isolates the retrieval variable.
- Deterministic where possible: age extraction, filter construction, fusion, dedup, and
  context budgeting are plain Python with unit tests; the LLM is used for exactly two
  things — paraphrasing the query (advanced path) and writing the answer.
- Unit-testable without network: the embedder, the knowledge store, and the chat model
  are all injected, with in-memory fakes under `tests/fixtures/`.
- Verifiable against real data: the corpus is committed, ingestion is run, and a
  committed validation set proves retrieval quality before any LLM is involved.

**Non-Goals:**

- Retrieval techniques beyond multi-query + fusion + metadata filtering (no BM25, no
  cross-encoder reranking, no HyDE, no parent-document retrieval). Candidates for Day 6
  follow-up if evaluation shows a gap.
- Prompt-injection hardening of the retrieved content or the question — Day 6 security.
- Caching of embeddings or answers.
- Token-accurate context budgeting (a character budget is sufficient and tokenizer-free).

## Decisions

### 1. Two retrievers behind one protocol; answer generation shared

**Decision:** `backend/rag/` defines a `Retriever` protocol with
`retrieve(question) -> RetrievalResult` (ordered chunks with scores, queries issued,
filters applied, filter-dropped flag, counts). `BasicRetriever` embeds the question and
takes top-K. `AdvancedRetriever` runs analysis → translation → multi-query search → RRF
fusion → dedup → filter fallback. A single `RagPipeline` takes a retriever and a chat
model, applies the relevance floor, builds context and citations, and generates the
answer. `strategy` selects the retriever.

**Why:** Day 6 compares strategies. If the strategies also differed in prompt, context
size, or model, a RAGAs delta could not be attributed to retrieval. Sharing everything
downstream of `RetrievalResult` makes the comparison clean and keeps the prompt in one
place.

**Alternative considered:** Two independent chains (simpler to write today). Rejected —
they drift apart by Day 6, and the router on Day 5 would need to know about both.

### 2. Deterministic age extraction; LLM only for paraphrase

**Decision:** Query analysis is a pure-Python parser: regexes for `N month(s)`,
`N-month-old`, `N year(s)`, `N week(s)`, and a small vocabulary (`newborn` → 0–1,
`infant`/`baby` → 0–12, `toddler` → 12–36, `preschooler` → 36–60), always producing an
`AgeRange(min_months, max_months)` Pydantic model bounded to 0–60, or `None`. Years map
to the full year span (`2 year old` → 24–35). Query translation — producing 1–3 alternative
phrasings — is the one LLM call in the retrieval stage, and any failure (network, parse,
empty) degrades to the original question alone.

**Why:** The architecture principle is deterministic code first. Age parsing is a closed
problem with testable edge cases and zero latency/cost; an LLM extraction would need
validation anyway (hard rule 7) and would add a failure mode to *every* advanced query.
Paraphrasing is genuinely open-ended, which is where a model earns its cost.

**Alternative considered:** `with_structured_output` on a Pydantic `QueryAnalysis` for
both age and paraphrases in one call. Cheaper by one call, but couples the deterministic
part to the flaky part; if the model errors we lose the age filter too.

### 3. Embeddings: `openai/text-embedding-3-small` via OpenRouter, explicit, no fallback

**Decision:** `EmbeddingProvider` is rewritten around a single configured model
(`EMBEDDING_MODEL`, default `openai/text-embedding-3-small`, 1536 dimensions) served by
OpenRouter at `https://openrouter.ai/api/v1` through `langchain_openai.OpenAIEmbeddings`.
No key → `RuntimeError` naming `OPENROUTER_API_KEY`. The collection stores the model name
and dimension in its description; `MilvusKnowledgeStore` checks them when it opens the
collection and refuses to search with a mismatched model.

**Why:** A silent fallback to a different model is a correctness bug, not resilience:
vectors from two models in one collection are incomparable, and the failure surfaces as
"retrieval quality is mysteriously bad" rather than an error. One provider also honours
Day 2 Decision 3 (one credential) and CLAUDE.md's "never call OpenAI directly".

**Alternative considered:** `fastembed` (ONNX, torch-free) as a local option. Viable, but
a second code path to keep consistent, another ~150 MB model download in CI, and no
advantage while every request already needs OpenRouter for the LLM.

### 4. Milvus collection: explicit schema, deterministic ids, FLAT/COSINE

**Decision:** Collection `nutrition_knowledge` is created on first open with a typed
schema: `id` VARCHAR primary key = first 32 hex chars of `sha256(document_id + ":" +
chunk_index)`; `embedding` FLOAT_VECTOR(dim); `content` VARCHAR; `document_id`, `source`,
`topic`, `authority`, `section` VARCHAR; `year`, `age_min_months`, `age_max_months`,
`chunk_index` INT64; `content_hash` VARCHAR. Unknown year is stored as `0`, unknown
strings as `""` (no reliance on nullable-field support in Milvus Lite). Index is FLAT
with COSINE metric; scores returned to callers are cosine similarity in [−1, 1].

**Why:** Deterministic ids are what make re-ingestion idempotent and let `upsert` be
delete-by-`document_id` then insert without duplicates. FLAT is exact and the corpus is
~1–2k vectors — an ANN index adds nondeterminism (which would muddy Day 6's A/B) for no
latency benefit at this size. COSINE gives a score a relevance floor can be set on.

**Alternative considered:** `MilvusClient.create_collection(dimension=...)` quick schema
with dynamic fields. Fewer lines, but int auto-ids (non-deterministic) and no typed
filterable metadata columns.

### 5. Metadata filters are built from validated values only

**Decision:** `SearchFilter(age_min_months, age_max_months, authorities)` is a Pydantic
model (ints bounded 0–60, `min ≤ max`, authorities from a `Literal` vocabulary matching
the manifest). `MilvusKnowledgeStore` renders it to a Milvus expression —
`age_min_months <= {max} and age_max_months >= {min}` (interval overlap) and
`authority in [...]` — from those validated fields only. User text never reaches the
expression string.

**Why:** Milvus filter expressions are a string language; interpolating user text into
one is the vector-store analogue of LLM-executed SQL (hard rule 6), and hard rule 7 asks
for Pydantic at every input boundary.

### 6. Multi-query fusion by reciprocal rank fusion; dedup by id then by text

**Decision:** Each query returns top-K (K = 8) with scores. Fusion is RRF with k = 60:
`score(chunk) = Σ 1 / (k + rank_q)`. Dedup drops repeated ids, then drops a chunk whose
whitespace-normalised text is ≥ 80 % contained in a higher-ranked chunk from the same
document (chunk-overlap artefacts). The fused list is cut to `top_k_final` (6) before
context construction. The per-chunk cosine score kept for the relevance floor is the
*maximum* similarity that chunk achieved across queries.

**Why:** RRF is rank-based, so it needs no score calibration across paraphrases and is
the standard, well-understood choice; it is a dozen lines and fully deterministic. The
text-containment check targets the specific duplication the 50-character chunk overlap
produces.

**Alternative considered:** Score averaging (needs normalisation; brittle) or an LLM
reranker (cost, latency, nondeterminism — deferred to Day 6 if needed).

### 7. Relevance floor before any LLM call

**Decision:** `RagPipeline` drops chunks with cosine similarity below
`RAG_MIN_SIMILARITY` (default **0.45**; the planning draft said 0.30 — see tuning below). If none remain, it returns the fixed no-answer message
(Decision 14) with empty citations and the disclaimer, without calling the chat model.

**Why:** Hard rule 5 requires every RAG answer to be cited; a question with no relevant
passages has nothing to cite, so the honest output is an explanation, and skipping the
model call removes the chance of an ungrounded answer entirely.

**Tuning (apply phase, 2026-08-26, `openai/text-embedding-3-small`, 230 chunks):**
top-1 cosine similarity for the 15 validation questions ranged **0.581–0.727**; for five
out-of-domain probes ("capital of France", "adult keto diet plan", "car insurance",
"Python list comprehensions", "marathon training") it ranged **0.082–0.368**. 0.30 would
have admitted the keto probe; 0.45 sits mid-gap with ≥0.08 margin on both sides. Re-tune
if the embedding model or corpus changes materially (`tests/test_retrieval_validation.py`
logs the numbers).

**Amendment (apply phase):** the floor is judged against the *original question's* best
similarity, not the maximum across paraphrases. The live run showed "adult keto diet
plan" scoring 0.368 alone (blocked) but 0.497 through a translated query (answered).
`RetrievalResult.question_top_score` carries the original's score; the pipeline returns
the no-answer message when it is below the floor regardless of what paraphrases found.
Chunks that clear the floor via a paraphrase are still kept as context when the question
itself is in-domain.

### 8. Context blocks and citations are the same list

**Decision:** Context is built in fused rank order as numbered blocks —
`[n] {source} ({year}) — {topic}{, section}\n{content}` — until a character budget
(`RAG_CONTEXT_CHAR_BUDGET`, default 6000) would be exceeded. The citation list returned
to the caller is exactly those blocks' metadata, in the same order and numbering. The
answer prompt instructs the model to reference blocks as `[n]`.

**Why:** One list, one ordering: the client can render `[2]` in the answer as a link to
citation 2 without reconciliation, and RAGAs context precision is measured over precisely
the passages the model saw.

### 9. LLM via LangChain `ChatOpenAI` → OpenRouter; model configurable

**Decision:** `backend/rag/llm.py` builds `ChatOpenAI(model=OPENROUTER_MODEL,
base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY, temperature=0,
default_headers={"HTTP-Referer", "X-Title"})`. Default model `openai/gpt-4o-mini`; the
apply phase verifies availability against OpenRouter's model list and adjusts the default
if needed. Temperature 0 for both translation and answering.

**Why:** The OpenAI-compatible SDK is the sanctioned path (CLAUDE.md); LangChain's chat
model gives streaming (`astream`) and fake models for tests for free. Temperature 0 keeps
Day 6's A/B reproducible.

### 10. Streaming: FastAPI `StreamingResponse`, hand-formatted SSE, no new dependency

**Decision:** `POST /api/ask` with `stream: true` returns
`StreamingResponse(media_type="text/event-stream")` yielding
`event: token|citations|done|error\ndata: <json>\n\n` frames. `stream: false` returns
`AskResponse` JSON. The route lives in `backend/api/ask.py`, mounted on `api_router`.

**Why:** SSE framing is a few lines; `sse-starlette` would be a dependency for
convenience only. One route with a `stream` flag keeps tests and Day 6's eval runner on
the JSON path while the UI uses the stream.

### 11. RAG settings are separate from `Settings`

**Decision:** `backend/core/config.py` gains `RAGSettings(BaseSettings)` —
`openrouter_api_key: str | None`, `openrouter_model`, `embedding_model`,
`milvus_db_path` (default `milvus.db`), `corpus_dir` (default `knowledge-base`),
`rag_min_similarity`, `rag_context_char_budget` — resolved via `get_rag_settings()`
(`lru_cache`, same `.env` handling). `/api/ask` returns 503 when `openrouter_api_key` is
`None`. Pipeline objects are built lazily per process on first request.

**Why:** `Settings` making `DATABASE_URL` mandatory is right for the app DB and wrong for
RAG tests and for the ingestion script (which never touches Postgres). Two small settings
classes beat one with everything optional.

### 12. Corpus authoring: hand-condensed Markdown, manifest-declared provenance

**Decision:** 15–20 documents, each 400–900 words, hand-written as condensed paraphrases
of a named guideline (WHO complementary feeding / growth standards / breastfeeding; AAP
guidance on iron, vitamin D, juice, cow's milk, allergen introduction, choking prevention,
honey/botulism; CDC infant & toddler nutrition pages; USDA/HHS Dietary Guidelines
2020–2025 birth-to-24-months chapter; NIH/NASEM DRI tables for energy, protein, iron,
zinc, calcium, vitamin D; FDA/EPA fish advice; food-safety guidance on unpasteurised
products). Every document uses `## Section` headings so chunks carry a heading, and
states its age applicability. `manifest.yaml` entries: `file, source, year, topic,
authority (WHO | AAP | CDC | USDA/HHS | NIH | FDA/EPA), age_min_months, age_max_months,
url`. No document may state anything contradicting hard rule 4.

**Why:** Day 2 Decision 6 chose Markdown + manifest; paraphrase rather than copied text
keeps the corpus redistributable; explicit age ranges are what Decision 5's filter keys
on; a fixed authority vocabulary is what makes the authority filter enum-typed.

### 13. Test strategy: fakes for units, live integration behind a marker

**Decision:** `tests/fixtures/` provides `InMemoryKnowledgeStore` (scores by token
overlap — deterministic, no vectors) and uses LangChain's `GenericFakeChatModel` for
answers/translations. Unit tests cover age parsing, filter validation/rendering, RRF,
dedup, budgeting, no-answer path, prompt content (tone instructions present, identical
across strategies), SSE framing, 422/503 paths. `@pytest.mark.integration` tests (skipped
unless `OPENROUTER_API_KEY` is set and `milvus.db` exists) run the validation set against
the real collection and one end-to-end `/api/ask` call. The existing `integration` marker
description is generalised to "requires live external services".

**Why:** Day 3 must be verifiable offline and in CI; embedding quality is verified once,
against real data, by the validation set, not re-verified in every unit test.

### 14. Tone is fixed in one system prompt and one no-answer string

**Decision:** `backend/rag/prompts.py` holds three constants used by both strategies:

- `SYSTEM_PROMPT` — answer for a parent, not a clinician; lead with the answer, then the
  supporting context; short paragraphs, bullets for lists of foods; explain a technical
  term on first use; state safety points firmly, without alarm or judgment; no filler and
  no restating the question; answer only from the numbered context blocks and cite them
  as `[n]`; if the blocks do not contain the answer, say so plainly; never compute a
  per-child quantity, only report figures as the sources state them.
- `NO_ANSWER_MESSAGE` — warm, calm, concise, explanatory. Working text: *"I wasn't able
  to find this in my sources. I answer from pediatric nutrition guidelines that cover
  children from birth to about four years, and this question falls outside what they
  cover. If it's about your child's health, your pediatrician is the best person to
  ask."*
- `DISCLAIMER` — one fixed sentence attached to every response by code, never produced
  by the model: *"This is general information from published pediatric nutrition
  guidelines, not medical advice. Please consult your pediatrician about your child's
  individual needs."*

**Why:** Tone belongs in the generation step, and the generation step must be frozen
before Day 6's A/B or the comparison measures the prompt change instead of retrieval.
Keeping the no-answer message and disclaimer as code constants means they cannot be
paraphrased, truncated, or dropped by the model. Wording (not principles) may be revised
on Days 5/7 once real answers are visible in the UI; a wording change after Day 6 means
re-running the evaluation, which is recorded as a known cost.

**Spot-check (apply phase, task 9.4):** five validation answers from `openai/gpt-4o-mini`
under both strategies were reviewed against this list — answer-first, plain language,
terms explained on first use ("recommended daily allowance (RDA)"), `[n]` citations on
claims, bulleted food lists, disclaimer attached by code, quantities quoted as the
sources state them. No wording change to `SYSTEM_PROMPT` was needed; it was only
re-wrapped to 100-column lines.

**Alternative considered:** Letting the model write the no-answer message from a tone
instruction. Rejected: it is the one path where there is nothing to ground the model in,
so a fixed string is both safer and cheaper.

## Risks / Trade-offs

- [OpenRouter model ids drift or a model is delisted] → both model ids are configuration;
  the apply phase checks the defaults against `/api/v1/models`; a bad id fails fast with
  the provider's message, not a silent fallback.
- [Relevance floor mis-set: too high triggers the no-answer message on valid questions,
  too low answers junk] → tuned on the validation set plus out-of-domain probes in the
  apply phase; the score of every retrieved chunk is logged and returned in retrieval
  metadata so Day 6 can re-tune.
- [Paraphrase call adds latency/cost to every advanced query] → one small call at
  temperature 0, capped at 3 alternatives; failure degrades to basic behaviour.
- [LLM answers beyond the context or ignores the tone instructions] → cannot be
  eliminated by prompt alone; Day 6's RAGAs faithfulness score measures grounding, and
  the no-answer floor removes the worst case (no context at all). Tone is spot-checked on
  the validation set's answers during apply.
- [Corpus paraphrases introduce a factual error] → every figure is tied to a named source
  and year in the manifest and reviewed on write; the corpus is data, fixable by editing
  a file and re-running ingestion (which is exactly the incremental-update feature).
- [Milvus Lite has no transactions; delete-then-insert has a brief inconsistent window] →
  ingestion is an offline job, not run against a serving process on Day 3; noted for the
  Day 7 migration to Standalone.
- [Interval-overlap age filter over-includes 0–60 "general" documents] → intended: general
  guidance is always eligible; age-specific documents win on similarity when they exist.
  Dropping the filter when it eliminates everything guards the other direction.
- [`test_app.py` asserts the API surface is exactly `/health`] → updated deliberately to
  `{"/health", "/api/ask"}`; the user-scoped-path guard stays.

## Migration Plan

1. `uv add pyyaml`; commit `uv.lock` (which also records the `sentence-transformers`
   removal).
2. Fix Day 2 code: loader glob + manifest metadata; `EmbeddingProvider` rewrite;
   `MilvusKnowledgeStore` schema/search/filter/count; `scripts/ingest.py` change detection
   + atomic replace.
3. Write `knowledge-base/*.md` + `manifest.yaml`; add `milvus.db` to `.gitignore`.
4. `uv run scripts/ingest.py` (requires `OPENROUTER_API_KEY` in `.env`); run twice to
   confirm the second run embeds nothing.
5. Build `backend/rag/` (prompts with tone constants first), `backend/schemas/rag.py`,
   `backend/api/ask.py`; wire the route.
6. Tests: fixtures, unit suites, integration suite; update `test_app.py` surface
   assertion; `uv run pytest`, `uv run ruff check .`.
7. Update `.env.example`, README development section (ingestion + ask), Day 2 `tasks.md`
   check-boxes for groups 6–9.

**Rollback:** remove the `/api/ask` include from `api_router`; delete `milvus.db`. Day 1/2
code paths are otherwise unaffected.

## Open Questions

- Whether `openai/gpt-4o-mini` remains the best default answer model on OpenRouter for
  cost/quality in August 2026. Deferrable: it is a single configuration value; the apply
  phase checks availability and the specs do not depend on the model.
