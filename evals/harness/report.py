"""Results on disk and the Markdown report (rag-evaluation spec, *The report compares the
strategies and can be reproduced*; design.md Decision 5)."""

import hashlib
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from harness.judge import METRICS

DETERMINISTIC = (
    "retrieval_hit",
    "provenance_ok",
    "intent_ok",
    "tools_ok",
    "no_answer_ok",
    "phrases_ok",
    "plan_items_ok",
)
TIE_MARGIN = 0.05  # judged metrics: |delta| below this counts as a tie


@dataclass
class RunResult:
    """One (case, strategy) outcome — the JSON-lines record."""

    case_id: str
    category: str
    strategy: str
    endpoint: str
    question: str
    answer: str
    intent: str | None
    tools: list[dict]
    citations: list[dict]
    retrieval: dict | None
    latency_ms: int
    deterministic: dict
    judged: dict = field(default_factory=dict)  # metric -> score | None
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, default=str)


@dataclass
class Header:
    timestamp: str
    label: str
    base_url: str
    case_set_sha256: str
    manifest_sha256: str
    embedding_model: str
    chat_model: str
    relevance_floor: str
    judge_model: str | None
    strategies: list[str]
    categories: list[str]
    limit: int | None
    repeat: int
    counts: dict[str, int] = field(default_factory=dict)
    excluded_from_judging: dict[str, int] = field(default_factory=dict)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_results(results: list[RunResult], path: Path) -> None:
    path.write_text("".join(r.to_json() + "\n" for r in results), encoding="utf-8")


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


def _rate(flags: list[bool | None]) -> str:
    known = [f for f in flags if f is not None]
    if not known:
        return "–"
    return f"{sum(known)}/{len(known)} ({100 * sum(known) / len(known):.0f}%)"


def render(header: Header, results: list[RunResult]) -> str:
    strategies = header.strategies
    by_strategy: dict[str, list[RunResult]] = defaultdict(list)
    for r in results:
        by_strategy[r.strategy].append(r)

    lines: list[str] = []
    lines += [
        f"# RAG A/B evaluation — {header.label}",
        "",
        "## Reproducibility",
        "",
        f"- Timestamp: {header.timestamp}",
        f"- Service: `{header.base_url}`",
        f"- Case set sha256: `{header.case_set_sha256}`",
        f"- Knowledge-base manifest sha256: `{header.manifest_sha256}`",
        f"- Embedding model: `{header.embedding_model}` · chat model: `{header.chat_model}` · "
        f"relevance floor: `{header.relevance_floor}`",
        (
            f"- Judge model: `{header.judge_model}`"
            if header.judge_model
            else "- Judge: skipped (`--skip-judge`)"
        ),
        f"- Strategies: {', '.join(strategies)} · categories: "
        f"{', '.join(header.categories) if header.categories else 'all'} · "
        f"limit: {header.limit if header.limit else 'none'} · repeat: {header.repeat}",
        "- Cases run per strategy: "
        + ", ".join(f"{s}={header.counts.get(s, 0)}" for s in strategies),
        "- Excluded from generation metrics (no-answer or not a judged category): "
        + ", ".join(f"{s}={header.excluded_from_judging.get(s, 0)}" for s in strategies),
        "",
        "## Deterministic checks (pass rate over cases that expect the check)",
        "",
        "| Check | " + " | ".join(strategies) + " |",
        "|---|" + "---|" * len(strategies),
    ]
    for check in DETERMINISTIC:
        cells = [_rate([r.deterministic.get(check) for r in by_strategy[s]]) for s in strategies]
        lines.append(f"| {check} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Latency (median ms): "
        + ", ".join(
            f"{s}={int(statistics.median([r.latency_ms for r in by_strategy[s]]))}"
            if by_strategy[s]
            else f"{s}=–"
            for s in strategies
        ),
        "",
        "## Generation metrics (RAGAs; answered rag/hybrid cases only)",
        "",
        "| Metric | " + " | ".join(strategies) + " | n |",
        "|---|" + "---|" * len(strategies) + "---|",
    ]
    for metric in METRICS:
        cells, n = [], 0
        for s in strategies:
            values = [r.judged[metric] for r in by_strategy[s] if r.judged.get(metric) is not None]
            n = max(n, len(values))
            mean = _mean(values)
            cells.append("–" if mean is None else f"{mean:.3f}")
        lines.append(f"| {metric} | " + " | ".join(cells) + f" | {n} |")

    if len(strategies) == 2:
        a, b = strategies
        lines += [
            "",
            f"## Paired comparison ({b} − {a})",
            "",
            "| Metric | mean Δ | wins | ties | losses |",
            "|---|---|---|---|---|",
        ]
        paired_b = {r.case_id: r for r in by_strategy[b]}
        for metric in METRICS:
            deltas = []
            for ra in by_strategy[a]:
                rb = paired_b.get(ra.case_id)
                if rb is None:
                    continue
                va, vb = ra.judged.get(metric), rb.judged.get(metric)
                if va is not None and vb is not None:
                    deltas.append(vb - va)
            wins = sum(d > TIE_MARGIN for d in deltas)
            losses = sum(d < -TIE_MARGIN for d in deltas)
            ties = len(deltas) - wins - losses
            mean = _mean(deltas)
            shown = "–" if mean is None else f"{mean:+.3f}"
            lines.append(f"| {metric} | {shown} | {wins} | {ties} | {losses} |")
        lines += ["", "| Check | " + f"{b} better | same | {a} better |", "|---|---|---|---|"]
        for check in DETERMINISTIC:
            better = same = worse = 0
            for ra in by_strategy[a]:
                rb = paired_b.get(ra.case_id)
                if rb is None:
                    continue
                fa, fb = ra.deterministic.get(check), rb.deterministic.get(check)
                if fa is None or fb is None:
                    continue
                if fb and not fa:
                    better += 1
                elif fa and not fb:
                    worse += 1
                else:
                    same += 1
            lines.append(f"| {check} | {better} | {same} | {worse} |")
        lines.append("")
        lines.append(
            f"Ties within ±{TIE_MARGIN} on a judged metric are noise at this sample size; "
            "no significance is claimed."
        )

    lines += ["", "## By category", ""]
    categories = sorted({r.category for r in results})
    lines.append("| Category | strategy | n | deterministic pass | " + " | ".join(METRICS) + " |")
    lines.append("|---|---|---|---|" + "---|" * len(METRICS))
    for category in categories:
        for s in strategies:
            rows = [r for r in by_strategy[s] if r.category == category]
            if not rows:
                continue
            passed = sum(1 for r in rows if not r.deterministic.get("failures"))
            means = []
            for metric in METRICS:
                m = _mean([r.judged[metric] for r in rows if r.judged.get(metric) is not None])
                means.append("–" if m is None else f"{m:.3f}")
            row = f"| {category} | {s} | {len(rows)} | {passed}/{len(rows)} | "
            lines.append(row + " | ".join(means) + " |")

    lines += ["", "## Failed deterministic checks", ""]
    failures = [
        (r.case_id, r.strategy, f) for r in results for f in r.deterministic.get("failures", [])
    ]
    errors = [(r.case_id, r.strategy, r.error) for r in results if r.error]
    if not failures and not errors:
        lines.append("None.")
    for case_id, strategy, failure in failures:
        lines.append(f"- `{case_id}` [{strategy}]: {failure}")
    for case_id, strategy, error in errors:
        lines.append(f"- `{case_id}` [{strategy}]: request failed — {error}")
    lines.append("")
    return "\n".join(lines)
