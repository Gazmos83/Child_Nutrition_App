# CLAUDE.md

Project context for AI coding assistants (Claude Code and others) working on this repo.

## Project

A RAG + tool-calling chatbot for **Turing College Project 2**, specialized in **child nutrition** (newborns through ~4 years old). Users get nutrient-specific meal plan recommendations based on the child's weight, age, gender, allergies, diet preference, and any doctor's note. Deliverable: a working, deployed MVP in **7 days**.

**Not a medical device.** Every recommendation must ship with a disclaimer that this is not medical advice and a pediatrician should be consulted.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind, shadcn/ui, TanStack Query |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| LLM | LangChain via **OpenRouter** (OpenAI-compatible SDK) — never call OpenAI directly with a raw key |
| Vector DB | Milvus Lite, behind a vector-store abstraction (not tightly coupled) |
| App DB | PostgreSQL — users, meals, conversations, nutrition data. **Never store this in Milvus.** |
| Tooling | **uv** — Python deps + venv, Python 3.14 pinned, `uv.lock` committed and authoritative · **pnpm** — frontend deps, workspace-ready |

Dependencies are always added through the package manager — `uv add` / `uv add --dev`, `pnpm add` — and Python code runs via `uv run`. Never `pip install` into `.venv` and never hand-edit a lockfile; `uv.lock` and `pnpm-lock.yaml` are the source of truth.

## Architecture principle

`Deterministic code → RAG → Tools → lightweight routing`

- No full agentic orchestration (LangGraph) for the MVP — a simple LLM-based intent router (RAG vs. tool vs. hybrid) is sufficient.
- The LLM extracts structured inputs; it never generates nutrient numbers itself. All quantities come from a lookup-table-driven Python function.

## Hard rules

1. **Age is stored and reasoned in months**, not years — nutrient needs shift fast in year one.
2. **Allergies and diet preference are enum/controlled-vocabulary fields**, never free text.
3. **Doctor's recommendation overrides** the general nutrient targets on conflict; flag the conflict in the UI, don't silently blend.
4. Every meal plan passes a **hard-coded infant-safety filter** (e.g., no honey under 12 months, no choking hazards, no unpasteurized products) independent of the RAG/LLM pipeline.
5. Knowledge base is sourced from **recognized pediatric guidelines** (WHO Child Growth Standards, AAP, national infant dietary guidelines) — cite source + publication date on every RAG-backed answer.
6. **No LLM-executed SQL.** All data access goes through validated, auth-scoped application code.
7. All tool/API inputs are validated with **Pydantic** before use.
8. Log every meal-plan recommendation with its full input snapshot (age, weight, allergies, preference, doctor's note, rule/source used) for auditability.
9. **Every user-scoped read and write is bound to the authenticated user's identity** — User A must never reach User B's child profiles, meals, or conversations. Auth/authz ships before deployment, not after it.

## Scope discipline

- Label every proposed feature **[MVP]** or **[Stretch]** — do not silently expand MVP scope.
- MVP: basic + advanced RAG, 3+ deterministic tools (BMI, calorie/protein targets, food lookup, meal nutrition, nutrient-specific meal plan), simple intent router, production UI with citations + tool-activity display, real-time KB re-ingestion, logging/monitoring, RAGAs A/B evaluation.
- Stretch (only if MVP done early): full LangGraph orchestration, LangSmith tracing, multi-model support, token/cost dashboards. **Kubernetes/Celery/distributed infra is out of scope entirely.**

## Detailed reference
`Nutrition_App_Full_Reference.md` in this same folder has the full day-by-day
plan and rationale behind these rules. It is NOT loaded automatically — open
it only when you need more depth than this file provides (e.g. clarifying an
edge case in the 7-day plan, the RAGAs eval design, or the infant-safety
filter rationale).
