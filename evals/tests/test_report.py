from harness.report import Header, RunResult, render


def result(
    case_id, strategy, category="rag_basic", judged=None, failures=(), hit=True
) -> RunResult:
    return RunResult(
        case_id=case_id,
        category=category,
        strategy=strategy,
        endpoint="ask",
        question="q",
        answer="a",
        intent=None,
        tools=[],
        citations=[],
        retrieval=None,
        latency_ms=100,
        deterministic={
            "retrieval_hit": hit,
            "provenance_ok": True,
            "intent_ok": None,
            "tools_ok": None,
            "no_answer_ok": True,
            "phrases_ok": None,
            "failures": list(failures),
        },
        judged=judged or {},
    )


def test_report_has_every_section_and_paired_counts() -> None:
    header = Header(
        timestamp="2026-08-28T12:00:00+00:00",
        label="test",
        base_url="http://x",
        case_set_sha256="c" * 64,
        manifest_sha256="m" * 64,
        embedding_model="e",
        chat_model="m",
        relevance_floor="0.45",
        judge_model="j",
        strategies=["basic", "advanced"],
        categories=[],
        limit=None,
        repeat=1,
        counts={"basic": 2, "advanced": 2},
        excluded_from_judging={"basic": 0, "advanced": 0},
    )
    results = [
        result(
            "a",
            "basic",
            judged={
                "faithfulness": 0.5,
                "answer_relevancy": 0.8,
                "context_precision": 0.5,
                "context_recall": 0.5,
            },
        ),
        result(
            "b",
            "basic",
            judged={
                "faithfulness": 0.9,
                "answer_relevancy": 0.8,
                "context_precision": 0.5,
                "context_recall": 0.5,
            },
            hit=False,
            failures=["none of [x] cited"],
        ),
        result(
            "a",
            "advanced",
            judged={
                "faithfulness": 0.9,
                "answer_relevancy": 0.8,
                "context_precision": 0.5,
                "context_recall": 0.5,
            },
        ),
        result(
            "b",
            "advanced",
            judged={
                "faithfulness": 0.9,
                "answer_relevancy": 0.8,
                "context_precision": 0.5,
                "context_recall": 0.5,
            },
        ),
    ]
    text = render(header, results)
    for section in (
        "## Reproducibility",
        "## Deterministic checks",
        "## Generation metrics",
        "## Paired comparison (advanced − basic)",
        "## By category",
        "## Failed deterministic checks",
    ):
        assert section in text
    assert "`" + "c" * 64 + "`" in text
    assert "Judge model: `j`" in text
    # faithfulness: a improves by 0.4 (win), b unchanged (tie) -> +0.200, 1 win, 1 tie
    assert "| faithfulness | +0.200 | 1 | 1 | 0 |" in text
    assert "| retrieval_hit | 1/2 (50%) | 2/2 (100%) |" in text
    assert "- `b` [basic]: none of [x] cited" in text
