## Why

Day 1 landed the app infrastructure and data model. Day 2 builds the knowledge foundation:
a curated corpus of pediatric nutrition guidance from authoritative sources, embedded
and indexed in Milvus Lite. Days 3 and 4 will build retrieval and tools on top of this
knowledge base, so getting the sources and ingestion pipeline right today is critical.

The reference doc flags this as "Medium bonus task" (re-runnable updates), but it's an
[MVP] commitment here — a knowledge base that can only be rebuilt in full is fragile,
and the ingestion logic will be reused on Day 3 (advanced RAG), so it's worth building
as a reproducible, triggerable job rather than a one-off script.

**Scope: [MVP]. Day 2 of 7.**

## What Changes

- **Curated pediatric nutrition corpus** — sourced from WHO Child Growth Standards, AAP
  Pediatric Nutrition Handbook, and national infant dietary guidelines (e.g., CDC/USDA
  dietary guidelines for 0–4 years). Documents carry metadata (source title, date,
  topic, authority level, page/section reference).
- **Document chunking and metadata extraction** — segmentation strategy that preserves
  reference integrity (e.g., chunks carry source + page), semantic segmentation (not
  just sliding windows) for nutrition content.
- **Embedding pipeline** — using LangChain's document loaders and the embeddings
  reachable via OpenRouter (same as the LLM provider, so credentials are already
  managed). Or, if OpenRouter embeddings are unavailable, a fallback to a standard
  open model (e.g., `all-MiniLM-L6-v2`).
- **Milvus Lite collection** — schema capturing document content, embeddings, metadata,
  and source provenance. Initial ingestion creates or upserts into a stable collection
  name.
- **Re-runnable ingestion pipeline** — a Python script/entrypoint that loads documents,
  embeds them, and upserts into Milvus without a full rebuild. Idempotent: running it
  twice with the same source data leaves the collection unchanged. Detects new or
  changed documents and re-embeds only those.
- **Ingestion configuration** — environment-driven settings for Milvus connection
  (Milvus Lite runs as a Python library in-process on Day 2; becomes a service later)
  and embedding model choice.
- **Test/validation baseline** — a small curated set of queries and expected retrieval
  outcomes, so Day 3's RAG evaluation starts with a known baseline.

## Capabilities

### New Capabilities

- `nutrition-knowledge-base`: A curated corpus of pediatric nutrition guidance from
  recognized sources (WHO, AAP, national guidelines), indexed in Milvus Lite and
  retrievable by semantic similarity. Carries full source provenance so citations can be
  generated later.
- `knowledge-ingestion-pipeline`: An idempotent, re-runnable job that loads documents,
  embeds them, and upserts into Milvus. Detects new or changed documents and re-embeds
  only those, supporting real-time knowledge updates.

### Modified Capabilities

None — Day 1's user and child-profile tables are untouched.

## Impact

- **New code**: `backend/knowledge/` (loaders, chunking, embeddings, Milvus clients),
  `scripts/ingest.py` (the re-runnable entrypoint), test fixtures for embedding.
- **New dependencies**: LangChain document loaders, `pymilvus` 3.x, `langchain-community`,
  optionally `sentence-transformers` if OpenRouter embeddings are unavailable.
- **New data**: the curated corpus lives as Markdown or PDF files in `knowledge-base/`,
  with source metadata in a manifest (YAML or JSON).
- **Milvus Lite**: runs in-process on Day 2 (no Docker, no server). Upserts to a
  persistent `milvus.db` file in the working directory.
- **No breaking changes** — the API and models from Day 1 are untouched.

## Non-goals

Deliberately deferred, protecting Day 2 from scope creep:

- **Full-text search or hybrid retrieval** — semantic-only on Day 2. Hybrid adds a
  second retrieval path Day 3 will scope and implement.
- **Advanced chunking strategies** — semantic overlap, hierarchical chunking, entity
  extraction — defer to Day 3 as the advanced RAG layer.
- **Multi-language support** — assume English documents only.
- **Live ingestion triggers or webhooks** — the script is manual for now; Day 7 may add
  scheduling.
- **Milvus cluster or high-availability setup** — Lite's single-process model is
  sufficient for MVP.
- **LangSmith tracing or observability on the ingestion pipeline** — Day 6.
