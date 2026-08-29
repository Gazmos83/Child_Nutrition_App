"""Run the A/B evaluation against a running service.

uv run --project evals python -m harness.run --label baseline
uv run --project evals python -m harness.run --skip-judge --categories rag_basic --limit 5
"""

import argparse
import asyncio
import datetime as dt
import os
import shutil
import sys
from pathlib import Path

from harness.cases import Case, load_cases
from harness.client import ServiceClient, ServiceUnavailable
from harness.judge import Judge, build_sample
from harness.report import Header, RunResult, render, sha256_of, write_results
from harness.scoring import score

EVALS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EVALS_DIR.parent
CASES_PATH = EVALS_DIR / "cases.yaml"
MANIFEST_PATH = REPO_ROOT / "knowledge-base" / "manifest.yaml"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def load_env(path: Path) -> None:
    """Read KEY=VALUE lines from the repo's .env without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG A/B evaluation (reference §12)")
    parser.add_argument("--strategies", default="basic,advanced")
    parser.add_argument("--categories", default="", help="comma-separated; default all")
    parser.add_argument("--limit", type=int, default=None, help="first N cases after filtering")
    parser.add_argument("--repeat", type=int, default=1, help="judge passes per sample (mean)")
    parser.add_argument("--skip-judge", action="store_true", help="deterministic layers only")
    parser.add_argument("--base-url", default=None, help="default EVAL_BASE_URL or localhost:8000")
    parser.add_argument("--label", default="run")
    parser.add_argument("--results-dir", default=str(EVALS_DIR / "results"))
    return parser.parse_args(argv)


def run_case(client: ServiceClient, case: Case, strategy: str, now: dt.datetime) -> RunResult:
    child_id = None
    try:
        if case.endpoint == "ask":
            response, latency = client.ask(case.question, strategy)
        else:
            child = client.save_child(case.child or {})
            child_id = child["id"]
            client.log_feeds(child_id, [f.resolve(now) for f in case.feeding_log])
            response, latency = client.chat(case.question, child_id, strategy)
        deterministic = score(case, response)
        return RunResult(
            case_id=case.id,
            category=case.category,
            strategy=strategy,
            endpoint=case.endpoint,
            question=case.question,
            answer=response.get("answer", ""),
            intent=response.get("intent"),
            tools=[{"name": t["name"], "status": t["status"]} for t in response.get("tools", [])],
            citations=response.get("citations", []),
            retrieval=response.get("retrieval"),
            latency_ms=latency,
            deterministic=deterministic.to_dict(),
        )
    except Exception as exc:
        return RunResult(
            case_id=case.id,
            category=case.category,
            strategy=strategy,
            endpoint=case.endpoint,
            question=case.question,
            answer="",
            intent=None,
            tools=[],
            citations=[],
            retrieval=None,
            latency_ms=0,
            deterministic={"failures": [f"request failed: {exc}"]},
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        if child_id is not None:
            # One child per case keeps feeding logs from bleeding between cases.
            client.delete_child(child_id)


def _sample_for(cases: list[Case], result: RunResult):
    if result.error:
        return None
    case = next(c for c in cases if c.id == result.case_id)
    return build_sample(
        case, result.strategy, {"answer": result.answer, "citations": result.citations}
    )


def _mean_or_none(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    load_env(REPO_ROOT / ".env")
    base_url = args.base_url or os.environ.get("EVAL_BASE_URL", "http://localhost:8000")
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    case_set = load_cases(CASES_PATH)
    cases = [c for c in case_set.cases if not categories or c.category in categories]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("no cases selected")
        return 2

    client = ServiceClient(base_url)
    # Every case runs under a session: /api/ask has required one since Day 7, and chat
    # cases additionally save a child and its feeds to the account.
    try:
        client.require_database()
    except ServiceUnavailable as exc:
        print(f"cannot run: {exc}")
        return 2
    client.register()
    print(f"registered throwaway account {client.account['email']} for every case")

    started = dt.datetime.now(dt.UTC)
    stamp = started.strftime("%Y-%m-%d-%H%M%S")
    out_dir = Path(args.results_dir) / f"{stamp}-{args.label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"

    results: list[RunResult] = []
    total = len(cases) * len(strategies)
    for strategy in strategies:
        for case in cases:
            result = run_case(client, case, strategy, started)
            results.append(result)
            status = "ok" if not result.deterministic.get("failures") else "FAIL"
            print(
                f"[{len(results)}/{total}] {strategy:8} {case.id:32} "
                f"{result.latency_ms:6}ms {status}"
            )
            with results_path.open("a", encoding="utf-8") as handle:
                handle.write(result.to_json() + "\n")

    judge_model = None
    excluded = {s: 0 for s in strategies}
    if not args.skip_judge:
        judge_model = os.environ.get("EVAL_JUDGE_MODEL") or os.environ.get(
            "OPENROUTER_MODEL", "openai/gpt-4o-mini"
        )
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            print("OPENROUTER_API_KEY is not set; cannot judge")
            return 2
        judge = Judge(
            model=judge_model,
            embedding_model=os.environ.get("EMBEDDING_MODEL", "openai/text-embedding-3-small"),
            api_key=api_key,
            base_url=os.environ.get("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
        )
        samples = []
        for r in results:
            sample = _sample_for(cases, r)
            if sample is None:
                excluded[r.strategy] += 1
            else:
                samples.append(sample)
        print(f"judging {len(samples)} samples with {judge_model} (repeat={args.repeat})")
        scores: dict[tuple[str, str], list[dict]] = {}
        for _ in range(max(1, args.repeat)):
            for key, value in asyncio.run(judge.score_all(samples)).items():
                scores.setdefault(key, []).append(value)
        for r in results:
            passes = scores.get((r.case_id, r.strategy))
            if passes:
                r.judged = {m: _mean_or_none([p.get(m) for p in passes]) for m in passes[0]}
    else:
        for r in results:
            if _sample_for(cases, r) is None:
                excluded[r.strategy] += 1

    header = Header(
        timestamp=started.isoformat(timespec="seconds"),
        label=args.label,
        base_url=base_url,
        case_set_sha256=sha256_of(CASES_PATH),
        manifest_sha256=sha256_of(MANIFEST_PATH),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "openai/text-embedding-3-small"),
        chat_model=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        relevance_floor=os.environ.get("RAG_MIN_SIMILARITY", "0.45"),
        judge_model=judge_model,
        strategies=strategies,
        categories=categories,
        limit=args.limit,
        repeat=args.repeat,
        counts={s: sum(1 for r in results if r.strategy == s) for s in strategies},
        excluded_from_judging=excluded,
    )
    write_results(results, results_path)
    report = render(header, results)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    reports_dir = EVALS_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    published = reports_dir / f"{started.strftime('%Y-%m-%d')}-{args.label}.md"
    shutil.copyfile(out_dir / "report.md", published)
    print(f"\nreport: {published}\nraw:    {results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
