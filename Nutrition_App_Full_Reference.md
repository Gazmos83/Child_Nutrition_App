# Child Nutrition AI App — Full Reference (Revised)

This is the detailed reference for a RAG + tool-calling chatbot specialized in **child nutrition (newborns through ~4 years old)**. For day-to-day work, use `CLAUDE.md`. Every section below is tagged **[MVP]** or **[Stretch]**.

**Not a medical device.** Every recommendation must ship with a disclaimer that this is not medical advice and a pediatrician should be consulted.

---

## 1. Objective
Build a production-oriented child nutrition AI assistant over **7 days**, demonstrating LangChain, RAG (basic + advanced), function calling, a vector DB, a Postgres-backed app layer, and a production UI — evaluated, secured, and deployed. **[MVP]**

Users get nutrient-specific meal plan recommendations based on a child's weight, age (in months), gender, allergies, diet preference, and any doctor's note.

Lightweight agentic orchestration only. **[Stretch: full LangGraph]**

---

## 2. Frontend **[MVP]**
Next.js, React, TypeScript, Tailwind, shadcn/ui, TanStack Query. No Streamlit.

UI must show: dashboard, meal logging, AI Coach chat, conversation history, nutrition summaries, RAG citations, tool-activity indicators, responsive layout.

*Use Claude Code to scaffold component structure and API hooks; review generated data-fetching logic before wiring to production endpoints.*

---

## 3. Backend **[MVP]**
Python, FastAPI, Pydantic, SQLAlchemy, Alembic. FastAPI owns REST APIs, auth boundaries, streaming, validation. Keep AI logic separate from HTTP concerns.

**Tooling:** **uv** for Python deps + venv, Python 3.14 pinned, `uv.lock` committed and authoritative; **pnpm** for frontend deps, workspace-ready. Dependencies are always added through the package manager (`uv add` / `uv add --dev`, `pnpm add`), and Python code runs via `uv run` — never `pip install` into `.venv`, never hand-edit a lockfile.

*Use Claude Code for CRUD boilerplate and migration scaffolding (Alembic).*

---

## 4. AI Stack **[MVP]**
LangChain + **OpenRouter** (OpenAI-compatible SDK) as the LLM provider — this satisfies the course requirement directly; do not call the OpenAI API with a native key. Use OpenRouter-served embeddings or an OpenAI-compatible embedding model reachable the same way.

LangChain handles: prompts, chains, document loading, splitting, embeddings, retrievers, tool definitions, structured outputs.

The LLM extracts structured inputs (age in months, weight, gender, allergies, diet preference, doctor's note); it never generates nutrient numbers itself — all quantities come from a lookup-table-driven Python function.

LangGraph is **[Stretch]** — see Section 9.

---

## 5. Vector Database — Milvus Lite **[MVP]**
Use for nutrition knowledge, guidelines, recipes, semantic retrieval, metadata filtering. Build behind a vector-store abstraction so migration to Milvus Standalone/Zilliz later doesn't touch business logic.

```
Milvus Lite → Milvus Standalone / Zilliz → Milvus Distributed (future, not now)
```

---

## 6. PostgreSQL **[MVP]**
Authoritative store for users, child profiles (age **stored and reasoned in months**, weight, gender), allergies and diet preference (**enum/controlled-vocabulary fields, never free text**), doctor's notes, meals, meal items, daily nutrition, conversations, messages. Never use Milvus as primary app data storage.

---

## 7. RAG Strategy

### Stage 1 — Basic RAG **[MVP]**
Query → Embedding → Milvus → Top-K → Prompt → LLM → Answer.

### Stage 2 — Advanced RAG **[MVP]**
Query analysis, query translation, multi-query retrieval, metadata filtering, deduplication, context construction. Establish a strong baseline before layering complexity — protect this day from scope creep.

---

## 8. Knowledge Base **[MVP]**
Curated pediatric nutrition corpus sourced from **recognized pediatric guidelines** (WHO Child Growth Standards, AAP, national infant dietary guidelines): dietary guidelines, macro/micronutrients, hydration, meal planning fundamentals for newborns through ~4 years. Each document carries metadata (source, title, topic, date, type, authority). Prioritize authoritative sources. **Cite source + publication date on every RAG-backed answer.**

Ingestion pipeline: Load → Clean → Chunk → Metadata → Embeddings → Milvus Lite, runnable via a single rebuild script.

**Real-time knowledge-base updates — committed to MVP (Medium bonus task):**
Design ingestion as a reproducible, re-runnable job (not one-off) — e.g., a script or scheduled endpoint that re-embeds new/changed documents and upserts into Milvus without a full rebuild. Doesn't need to be a live streaming pipeline; a triggerable, idempotent update job satisfies this.

*Use Claude Code to write and iterate on the ingestion script.*

---

## 9. Function Calling / Tools **[MVP]**
Deterministic Python functions, typed inputs, Pydantic validation, authorization checks, structured results, graceful failure handling. Never let the LLM perform math it can compute deterministically.

Initial tools: `calculate_bmi()`, `calculate_calorie_target()`, `calculate_protein_target()`, `lookup_food()`, `calculate_meal_nutrition()`, `generate_meal_plan()` (nutrient-specific meal plan), `get_daily_nutrition()`, `get_remaining_targets()`. MVP requires 3+ of these as deterministic tools, with `generate_meal_plan()` as the core child-facing one.

Every meal plan passes a **hard-coded infant-safety filter** (e.g., no honey under 12 months, no choking hazards, no unpasteurized products) that runs independently of the RAG/LLM pipeline — the LLM cannot bypass or override it.

**Doctor's note overrides on conflict:** when a doctor's recommendation conflicts with the general nutrient targets, the doctor's note wins; flag the conflict in the UI rather than silently blending the two.

---

## 9a. Routing Strategy (Reduced Priority)

**MVP:** A single lightweight router — one LLM call or classifier that decides RAG vs. tool vs. hybrid vs. user-data lookup, then executes deterministically. No persistent agent state machine required.

```
"What is fiber?"                      → RAG
"What's my child's BMI?"              → Tool
"How much protein does my toddler need?" → Tool + child profile
"What should my 8-month-old eat this week?" → RAG + tools + user data
```

**[Stretch] Full LangGraph Nutrition Agent:** explicit state graph (intent analysis → planning/routing → RAG/Tools/UserData/Hybrid branches → context builder → answer generator → validator), with tool-call limits, retries, and execution-time caps. Only build this if Days 1–7 finish with time to spare — it was originally a Day 6 priority but is now optional upside, not required scope.

*If pursued, use Claude Code to scaffold the graph nodes/edges after you've decided the routing logic by hand.*

---

## 10. Frontend ↔ Backend Communication **[MVP]**
Next.js → REST → FastAPI. Use SSE/streaming for AI responses where practical. Responses should carry streaming text, citations, tool-activity, errors, and history.

Example UX:
```
User: How much protein does my child still need today?
AI: You have approximately 42g remaining today.
Sources: • Nutrition guideline
Tools used: ✓ Daily nutrition ✓ Protein target calculator
```

---

## 11. AI Safety **[MVP]**
This is a child nutrition assistant, not a medical professional. **Every recommendation ships with a disclaimer that this is not medical advice and a pediatrician should be consulted.** Implement clear boundaries and disclaimers for: diagnosis requests, serious symptoms, allergic-reaction/emergency situations, medication interactions, extreme dieting, eating-disorder-related requests, and dangerous nutritional recommendations for infants/toddlers. No unsupported medical claims. When a doctor's note conflicts with the general nutrient targets, defer to the doctor's note and surface the conflict rather than resolving it silently.

---

## 12. Evaluation Strategy

**[MVP] Committed hard bonus task:** A/B testing of different RAG strategies (e.g., basic vs. advanced/query-translated retrieval), evaluated with **RAGAs where practical** (faithfulness, answer relevance, context precision/recall). If RAGAs proves too heavy to integrate in the time available, fall back to a smaller hand-scored rubric across the same test set — but attempt RAGAs first since it's the stated goal.

Build a test set of **40–60 cases** covering: basic RAG, advanced/multi-query RAG, tool questions, RAG+tool combos, user-data questions, out-of-domain, adversarial. Evaluate retrieval (relevance, source quality), routing (correct path chosen), and generation (correctness, groundedness, citation accuracy).

*Use Claude Code to generate test-case scaffolding and the eval-runner script; review the actual test cases and scoring logic yourself.*

---

## 13. Security **[MVP]**
Auth/authz before deployment. Every user-scoped operation must be bound to authenticated identity — User A must never reach User B's data. Validate all API inputs, tool inputs, DB operations, uploaded documents, and LLM-generated tool arguments with **Pydantic** before use. Allergies and diet preference are enum/controlled-vocabulary fields, never free text. Never let the LLM execute arbitrary SQL — all data access goes through validated, auth-scoped application code.

---

## 14. Observability & Logging

**[MVP] Committed medium bonus task:** Application-level logging and monitoring — log queries, routing decisions, tool calls, retrieval results, errors, and latency at minimum. Keep it lightweight (structured logs are enough; a dashboard is not required for MVP).

**Log every meal-plan recommendation** with its full input snapshot (age in months, weight, gender, allergies, diet preference, doctor's note, rule/source used) for auditability.

**[Stretch]** Full LangSmith tracing across the query → router → retrieval → tool → LLM → response pipeline, plus token-usage/cost dashboards.

---

## 15. Infrastructure **[MVP, kept simple]**
Docker, GitHub, GitHub Actions, managed PostgreSQL, Milvus Lite, Vercel (or equivalent) for Next.js, container hosting for FastAPI. No Kubernetes, Celery, or microservices unless a real need appears.

---

## 16. Production Migration Path (Design-only, not built now)
```
Now:    Next.js → FastAPI → LangChain/router → Milvus Lite + PostgreSQL
Future: Next.js → FastAPI → LangGraph/LangChain → Milvus Standalone/Zilliz → PostgreSQL
```
Keep the RAG service decoupled from Milvus's deployment mode so this migration doesn't require a rewrite.

---

## 17. Seven-Day Priority Order (MVP-first)

```
DAY 1  Architecture + project setup + PostgreSQL
       (users, child profiles in months, allergy/diet enums, doctor's note field)
DAY 2  Nutrition data + Milvus ingestion + re-runnable update pipeline [MVP]
       (pediatric guideline corpus: WHO, AAP, national infant dietary guidelines)
DAY 3  Basic + Advanced LangChain RAG (OpenRouter) + query translation
       — protect from feature creep; establish a strong baseline first
DAY 4  Function calling + deterministic tools
       (BMI, calorie/protein targets, food lookup, meal nutrition, meal plan)
       + hard-coded infant-safety filter + doctor's-note override logic
DAY 5  Lightweight intent router + Next.js/React production UI
       (chat, citations, tool-activity display)
       — protect from feature creep; full LangGraph agent only if ahead of schedule
DAY 6  Evaluation (RAGAs A/B testing [MVP]) +
       security + AI safety + logging/monitoring [MVP]        — protect from feature creep
DAY 7  Deployment + UX polish + stretch goals if time allows
```

---

## 18. Core Engineering Principle
**Deterministic code → RAG → Tools → lightweight routing**, not agent-everywhere. Use AI where it adds genuine value; use Claude Code to accelerate implementation of decisions you've already made, not to make architectural decisions for you.

## Definition of Success
By Day 7: a working, deployed child nutrition AI product (newborns through ~4 years) covering LangChain → RAG → Advanced RAG → Function Calling → Lightweight Routing → Full-Stack App → Evaluation (with RAG A/B testing) → Logging/Monitoring → Production Hardening — with full agent orchestration and deeper observability as clearly-labeled stretch upside, not required scope.
