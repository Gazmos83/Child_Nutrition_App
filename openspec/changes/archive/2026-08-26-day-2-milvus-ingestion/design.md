## Context

Day 1 landed the app infrastructure and PostgreSQL schema. The user/child-profile model
is ready. Days 3 and 4 will build RAG (basic, then advanced) and deterministic tools on
top of a knowledge base -- a curated corpus of pediatric nutrition guidance that is
indexed, embedable, and retrievable by semantic similarity.

Day 2's job is to acquire that corpus and build the ingestion/embedding pipeline that
populates it into Milvus Lite. This is not a search problem yet (that's Day 3); it's a
data foundation problem.

Constraints that shape the approach:

- **No LLM is called by the ingestion pipeline** -- the LLM pipeline lives on Days 3/4.
  This job is purely load → chunk → embed → store.
- **Idempotency is load-bearing** -- re-running the pipeline with the same input corpus
  must be safe and fast, not a full rebuild every time. Real-time updates (new source
  drops) need to be incorporated without re-embedding the whole corpus.
- **One week, start to finish** -- there is no time for a custom document loader or
  embedding infrastructure. Reuse: LangChain loaders (load once, reuse on Day 3),
  OpenRouter embeddings (same credentials as the LLM, one account to manage).
- **Milvus Lite runs in-process** (not a service) on Day 2 for simplicity. It's behind
  an abstraction anyway, so moving to a service later doesn't touch the corpus loading
  logic.

## Goals / Non-Goals

**Goals:**

- Ingest a curated corpus of ~50–100 documents (WHO, AAP, national guidelines) covering
  0–60 months pediatric nutrition.
- Every document is chunked, embedded, and indexed into Milvus Lite with full source
  provenance (title, date, section, authority).
- A re-runnable ingestion script detects new/changed documents and re-embeds only those,
  supporting incremental updates without full rebuilds.
- A small test/validation set (10–20 queries + expected results) establishes a baseline
  for Day 3's RAG evaluation.

**Non-Goals (design-level, beyond the proposal's scope):**

- Advanced chunking strategies (semantic overlap, hierarchical chunking, entity
  extraction) -- Day 3's advanced RAG layer owns those.
- Hybrid retrieval (semantic + full-text) -- semantic only on Day 2.
- Multi-lingual support -- English documents only.
- Live webhooks or scheduled triggers -- manual script for now; Day 7 adds scheduling.
- Observability/LangSmith tracing on the ingestion pipeline -- Day 6.

## Decisions

### 1. LangChain document loaders for corpus loading

**Decision:** Use LangChain's `DirectoryLoader`, `TextLoader`, and `PDFPlumberLoader` to
read documents. Define a simple custom loader if a source type isn't covered (e.g.,
Google Sheets for WHO data).

**Why:** LangChain loaders are battle-tested, composable, and will be reused on Day 3
when the RAG retriever is built. Writing a custom loader just for Day 2 is wasted work.

**Alternative considered:** Custom Python loader (os.walk + open). Simple, but doesn't
reuse on Day 3, and is vulnerable to edge cases (encoding, PDF extraction) that LangChain
handles.

**Cost accepted:** a LangChain dependency footprint in ingestion (but it's already on the
backend via FastAPI); minor abstraction complexity (loader needs to report loaded docs
for deduplication).

### 2. Semantic chunking with overlap, targeting 512 token chunks

**Decision:** Use LangChain's `RecursiveCharacterTextSplitter` with `chunk_size=512`,
`chunk_overlap=50`, splitting on newlines/spaces. For PDFs and complex layouts, include
section headers in chunks to preserve context.

**Why:** 512 tokens is a sweet spot for pediatric nutrition docs: short enough to fit in
a context window alongside a query, long enough to contain a complete thought (a guideline
rule or recommendation). Overlap preserves continuity when a semantic boundary falls
mid-sentence. Section headers act as breadcrumb context without ballooning chunk size.

**Alternative considered:** Fixed sliding window (simpler, but loses semantic boundaries
and creates artificial splits mid-sentence); hierarchical chunking (better, but too complex
for Day 2 -- Day 3 can upgrade).

**Cost accepted:** chunk boundaries are heuristic-driven, not perfect. A chunk might
contain partial lists or incomplete thoughts. Day 3's advanced RAG can iterate here.

### 3. Embeddings via OpenRouter (same as the LLM provider)

**Decision:** Use OpenRouter-served embeddings (e.g., OpenAI's text-embedding-3-small or
equivalent). Fallback: if OpenRouter has no embedding endpoint, use `sentence-transformers`
locally (all-MiniLM-L6-v2 or similar).

**Why:** OpenRouter is already the LLM provider (Day 3/4) and handles auth. One account,
one billing, one credential to manage. The embeddings and LLM are likely from the same
vendor, reducing the risk of semantic mismatch between query embeddings and retrieval.

**Alternative considered:** Local `sentence-transformers` only (simplest, no API call).
Rejected because the embedding quality matters for a health domain; OpenRouter's models
are stronger. Hybrid fallback (try OpenRouter, fall back to local) accepted to handle
outages.

**Cost accepted:** API latency on initial ingestion (~1 min for 50 docs at ~2 embeds/sec).
Subsequent runs re-embed only changed docs, so the cost is amortized.

### 4. Milvus Lite, in-process, with persistent file storage

**Decision:** `pymilvus.MilvusClient` connecting to an in-process Milvus Lite instance,
persisting to `milvus.db` in the working directory.

**Why:** Zero infrastructure on Day 2. No Docker, no separate service, no network calls
for storage (only for embedding). The collection is backed by a file, so it survives
process restart. Migration to Milvus Standalone/Zilliz is behind the abstraction (`backend/db/milvus_client.py`), so implementation stays the same on Day 3.

**Alternative considered:** Start a Docker Milvus service (more realistic, but adds a
dependency outside the scope of this one-week sprint). Postgres as a document store (has
pgvector, but we're already storing app data in Postgres; keeping them separate leaves
each system's role clear).

**Cost accepted:** Milvus Lite runs in-process, so if ingestion crashes, the process
dies (and the next run recovers). In production, a service with separate lifetime is safer.

### 5. Change detection via file modification time and document hash

**Decision:** Before embedding, compute a hash (MD5 or SHA256) of each document's
content. Compare against hashes stored in the Milvus collection's metadata. Re-embed
only if the hash differs.

**Why:** File modification time is unreliable (can be changed by copying, git checkout,
etc.); content hash is the source of truth.

**Alternative considered:** Semantic fingerprinting (embedded chunks themselves as a
fingerprint). More sophisticated, but if the corpus is stable (WHO doesn't rewrite
frequently), hashing is overkill. Day 3 can add fingerprinting if needed.

**Cost accepted:** Computing all hashes adds ~1–2 sec to ingestion. Acceptable.

### 6. Corpus format: Markdown files + YAML manifest

**Decision:** Documents live as Markdown files in `knowledge-base/` with a `manifest.yaml`
listing each file's source, publication date, topic, and authority.

```yaml
documents:
  - file: who-growth-standards-2006.md
    source: "WHO Child Growth Standards 2006"
    date: 2006
    topic: growth, standards
    authority: "WHO official"
  - file: aap-infant-nutrition.md
    source: "AAP Pediatric Nutrition Handbook"
    date: 2021
    topic: infant, complementary feeding
    authority: "American Academy of Pediatrics"
```

**Why:** Markdown is readable and git-friendly. A manifest keeps metadata separate from
content, making it easy to update without re-chunking. YAML is simple enough for a
human to edit.

**Alternative considered:** Frontmatter in each Markdown file (avoids a separate manifest,
but makes bulk metadata updates harder). Structured data in a database (premature; a
manifest suffices for now).

**Cost accepted:** manual curation of the manifest; any new source requires a manifest
entry. Day 2 will have a small initial corpus (~20–30 docs), so this is manageable.

### 7. Upsert strategy: replace chunks by document ID

**Decision:** When a document is re-ingested, delete all chunks from that document
(identified by `document_id` in metadata) and insert the new chunks. Use Milvus
transactions or immediate upsert to ensure atomicity.

**Why:** Guarantees consistency: queries never see a mix of old and new chunks from the
same document.

**Alternative considered:** Upsert each chunk independently (simpler, but risks an
inconsistent snapshot if a crash happens mid-update). Soft-delete and lazy cleanup
(complex bookkeeping).

**Cost accepted:** deleting old chunks for a changed document means the query latency
can spike during ingestion (if deletes are not indexed efficiently). Acceptable for Day 2's
manual, off-peak ingestion.

### 8. Retrieval abstraction: a `KnowledgeStore` interface

**Decision:** Create a `backend/db/knowledge_store.py` with an abstract `KnowledgeStore`
interface. Implement it with `MilvusKnowledgeStore` on Day 2; Day 3's retriever calls
through this interface.

```python
class KnowledgeStore(ABC):
    async def search(self, query: str, top_k: int) -> list[Document]:
        ...
```

**Why:** The retriever (Day 3) doesn't know or care whether the backing store is Milvus
Lite, Milvus Standalone, or Zilliz. If we switch implementations, the RAG code is
untouched. This mirrors the pattern from Day 1's session/engine abstraction.

**Cost accepted:** one more abstraction layer, but it pays for itself the moment Day 3 is
written (no changes needed if the vector DB swaps).

## Risks / Trade-offs

- **Manual corpus curation is non-scalable** → Accept for MVP. If the corpus needs to grow
  past 100 docs, Day 7 can add tooling (parsing WHO PDFs directly, scraping guidelines
  from APIs).
- **Embedding costs from OpenRouter** → Roughly $0.02 per 1M tokens; 50 docs at ~5k tokens
  each is ~250k tokens, so ~$0.005 per full rebuild. Acceptable. Local fallback (`sentence-transformers`)
  costs CPU instead.
- **Milvus Lite doesn't scale past ~1M vectors** → Sufficient for this corpus (50 docs × ~50
  chunks each ≈ 2,500 vectors). Day 7 migrates to Standalone if needed.
- **Change detection by hash means content-only; metadata changes are ignored** → Docs
  that change only in the manifest are not re-embedded. Edge case: if a source date changes,
  the hash is unchanged, so the embedding is not refreshed. Accepted; manifest is author
  metadata, not content.

## Migration Plan

1. Acquire and stage the corpus: download WHO Growth Standards, AAP Pediatric Nutrition
   Handbook, national dietary guidelines PDFs. Convert to Markdown (or keep as PDFs and
   use PDFPlumberLoader). Write `knowledge-base/manifest.yaml`.
2. `uv add pymilvus langchain langchain-community sentence-transformers` (the fallback).
3. Implement `backend/db/knowledge_store.py` (interface) and
   `backend/db/milvus_knowledge_store.py` (implementation).
4. Implement `backend/knowledge/loaders.py` (corpus loading, chunking, hashing).
5. Implement `scripts/ingest.py` (the orchestrator: load docs, embed, upsert).
6. Populate `knowledge-base/` with the curated corpus.
7. Run `uv run scripts/ingest.py` and verify Milvus contains the documents.
8. Write a small test/validation set of 10–20 queries and expected results.

**Rollback:** Delete `milvus.db` and re-run `ingest.py` with the original corpus.

## Open Questions

None that block implementation. The corpus sources (WHO, AAP, national guidelines) are
public and well-known; acquiring them is straightforward. The ingestion logic is standard
(load → chunk → embed → upsert); no architectural unknowns remain.

One judgment call: whether to hand-curate chunks in Markdown (cleaner, one-time work) or
parse PDFs dynamically (more flexible, but fragile). Hand-curation is chosen for Day 2's
seven-day sprint; Day 3 can add dynamic parsing if the corpus needs to grow rapidly.
