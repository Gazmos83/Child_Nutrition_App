## Why

Days 1 and 2 built the data model and the knowledge-base plumbing (loaders, chunker,
embedding provider, Milvus store abstraction, ingestion script). Nothing yet answers a
question. Day 3 turns the knowledge base into a grounded question-answering pipeline:
a user asks "how much iron does an 8-month-old need?" and gets an answer drawn from WHO /
AAP / national guideline text, with source and publication date cited, and the
not-medical-advice disclaimer attached (hard rule 5).

Two things make today load-bearing for the rest of the week. Day 5's router dispatches to
this RAG path, so its interface (query in → answer + citations out) must be stable. Day
6's A/B evaluation compares *basic* against *advanced* retrieval with RAGAs, so both
strategies must exist as selectable, otherwise-identical paths — not one strategy that
evolved in place.

Day 2's implementation stopped at group 5: the corpus was never written, the ingestion
script was never run, and the Milvus store has gaps (no collection creation, `search()`
unimplemented, non-deterministic row ids). A RAG pipeline cannot be verified against an
empty knowledge base, so closing that out is the first, prerequisite step of this change
rather than a separate one.

**Scope: [MVP]. Day 3 of 7.**

## What Changes

- **Knowledge base populated and ingestion verified** (Day 2 close-out). A curated corpus
  of ~15–20 Markdown documents in `knowledge-base/`, each hand-condensed from a recognized
  pediatric guideline (WHO complementary feeding and growth standards, AAP clinical
  guidance, CDC/USDA Dietary Guidelines for Americans 2020–2025, NIH DRI tables), with a
  `manifest.yaml` carrying source, publication year, topic, authority, and the age range in
  months each document covers. The ingestion script is run against it and its idempotency /
  change-detection behaviour is verified with tests.
- **Day 2 defects fixed.** `MilvusKnowledgeStore` gains explicit collection creation with
  a typed schema, a working text `search()` (embeds the query internally), metadata
  filtering, deterministic chunk ids, and a working `count()`. The embedding provider is
  pinned to a single explicit OpenRouter model (the fallback-on-missing-key behaviour is
  removed — it would silently switch embedding dimension between ingestion and query
  time). The loader reads manifest metadata and the `.md`/`.txt` glob is fixed.
- **Basic RAG** — query → embed → top-K vector search → prompt with numbered context
  blocks → LLM (LangChain `ChatOpenAI` pointed at OpenRouter) → answer. The answer is
  returned with a structured citation list (source, year, topic, section) and the
  disclaimer. If nothing relevant is retrieved above a similarity floor, the pipeline
  says so instead of answering from the model's own knowledge.
- **Tone and voice**, fixed today because the answer prompt is shared by both strategies
  and must stay constant through Day 6's A/B evaluation. Answered questions use
  plain language and are concise and direct: lead with the answer, then the supporting
  context; explain a term like "complementary feeding" on first use; no clinical jargon
  for its own sake. Questions the knowledge base cannot cover get a warm, calm, concise
  message that explains *why* — the assistant's sources are pediatric nutrition
  guidelines for children from birth to about four years, and this question falls
  outside them — and points the parent to their pediatrician. The disclaimer is one
  fixed sentence, never rephrased by the model. UI copy and tone iteration driven by
  real answers are deferred to Days 5 and 7; the principles are what is locked now.
- **Advanced RAG** — the same pipeline with a retrieval stage that adds: (1) query
  analysis, extracting the child's age in months and topic from the question into a
  Pydantic structure (hard rules 1 and 7); (2) query translation into 2–3 alternative
  phrasings; (3) multi-query retrieval fused with reciprocal rank fusion; (4) metadata
  filtering on age-range overlap and, optionally, authority; (5) deduplication of
  near-identical chunks; (6) context construction within a character budget, preserving
  citation order. Strategy is selected by a single `strategy: basic | advanced` parameter
  so Day 6 can A/B them on the same test set.
- **`POST /api/ask`** — the first route on the `/api` router. Pydantic-validated request
  (`question`, `strategy`), server-sent-event streaming response carrying answer tokens,
  then a final citations + metadata event; a non-streaming JSON variant for tests and
  evaluation. **Not user-scoped**: it reads no child profile, persists no conversation,
  and takes no user identity, so exposing it before Day 6's auth does not violate hard
  rule 9.
- **Configuration** — `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `EMBEDDING_MODEL`,
  `MILVUS_DB_PATH`, `CORPUS_DIR` read through `pydantic-settings`, resolved lazily so the
  app still boots (and `/health` still answers) with none of them set.
- **Retrieval validation set** — 12–15 curated questions with expected source documents,
  used by tests today and reused as the seed of Day 6's RAGAs test set.

## Capabilities

### New Capabilities

- `rag-answering`: A grounded answer to a child-nutrition question, generated only from
  retrieved knowledge-base passages, written in plain, concise, direct language, carrying
  citations (source + publication date) and the not-medical-advice disclaimer; when
  retrieval finds nothing relevant, a warm, calm, concise message explains why the
  question cannot be answered from the knowledge base.
- `advanced-rag-retrieval`: The retrieval stage that analyses and translates the query,
  runs multi-query retrieval with fusion, applies metadata (age-range, authority)
  filters, deduplicates, and constructs a bounded context — selectable alongside the
  basic strategy for A/B comparison.
- `ask-api`: The `POST /api/ask` HTTP contract — validated input, streamed answer with a
  terminal citations event, non-streaming variant, and explicit non-user-scoped
  boundary.

### Modified Capabilities

- `nutrition-knowledge-base`: search accepts a text query (the store embeds it) and an
  optional metadata filter (age range in months, authority); every chunk records the
  age range it applies to.
- `knowledge-ingestion-pipeline`: document metadata comes from `knowledge-base/manifest.yaml`;
  a document in the corpus but absent from the manifest is ingested with a warning, not
  rejected; the embedding model is a single explicit configuration value with no silent
  fallback.

## Impact

- **New code**: `backend/rag/` (LLM client factory, prompts, basic retriever, advanced
  retriever with query analysis / translation / fusion / filtering / dedup / context
  builder, answer chain), `backend/schemas/rag.py`, `backend/api/ask.py`,
  `tests/test_rag_*.py`, `tests/fixtures/` (a fake embedder and a fake chat model so the
  pipeline is unit-testable without network access).
- **Modified code**: `backend/db/milvus_knowledge_store.py`, `backend/knowledge/embeddings.py`,
  `backend/knowledge/loaders.py`, `scripts/ingest.py`, `backend/core/config.py`,
  `backend/api/router.py` (gains its first route), `.env.example`, `.gitignore`
  (`milvus.db`).
- **New data**: `knowledge-base/*.md` and `knowledge-base/manifest.yaml`, committed.
  `milvus.db` is generated and gitignored.
- **Dependencies**: `pyyaml` (manifest parsing; currently only a transitive dependency,
  must be declared since we import it). No new vector-store or LLM libraries — LangChain,
  `langchain-openai`, and `pymilvus` are already present. `sentence-transformers` stays
  removed (the uncommitted `uv.lock` already reflects this).
- **Tests**: existing 97 passing tests unchanged; `test_app.py`'s assertion that the
  documented surface is exactly `/health` is updated to include `/api/ask`, with its
  user-scoped-path guard left intact.
- **Cost**: embedding the corpus once with `openai/text-embedding-3-small` via OpenRouter
  is fractions of a cent; each question is one embedding call (plus one small LLM call
  for query analysis in the advanced path) and one answer-generation call.
- **No breaking changes** to Day 1's schema or routes.

## Non-goals

Deliberately deferred to keep Day 3 a strong, measurable retrieval baseline:

- **Intent routing** (RAG vs. tool vs. hybrid) — Day 5. Today every request is RAG.
- **Deterministic tools, personalized nutrient numbers, meal plans, infant-safety filter,
  doctor's-note override** — Day 4. The answer chain is instructed to quote guideline
  figures only as they appear in retrieved text and never to compute per-child targets.
- **Child-profile-aware answers and conversation persistence** — both user-scoped; they
  land after auth on Day 6. `/api/ask` is stateless.
- **Conversational memory / multi-turn context** — Day 5 with the chat UI.
- **Hybrid (BM25 + vector) retrieval and cross-encoder rerankers** — multi-query fusion is
  the advanced technique for MVP; these are candidates if Day 6's evaluation shows a gap.
- **RAGAs evaluation itself** — Day 6. Today only makes the two strategies comparable.
- **Full AI-safety boundary handling** (emergency symptoms, eating-disorder requests,
  medication interactions) — Day 6. Today's prompt carries the disclaimer and the
  "answer only from context" constraint.
- **Tone iteration and UI copy** — Days 5 and 7. Today locks the tone principles in the
  prompt and the no-answer message; wording is refined once real answers can be read in
  the chat UI.
- **LangGraph, LangSmith tracing, multi-model routing** — [Stretch].
- **Frontend** — Day 5.
