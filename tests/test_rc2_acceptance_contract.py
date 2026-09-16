from pathlib import Path

from scripts.rc2_acceptance import THRESHOLDS, answer_quality, load_cases


def test_rc2_dataset_has_release_candidate_coverage() -> None:
    cases = load_cases(Path("eval/rc2_scenarios.jsonl"))
    assert len(cases) == 30
    assert len({case["conversation"] for case in cases}) >= 20
    assert {case["category"] for case in cases} == {
        "knowledge",
        "weather",
        "multiturn",
        "long_conversation",
        "prompt_injection",
        "out_of_scope",
        "provider_failure",
        "itinerary",
    }
    assert sum(case["category"] == "prompt_injection" for case in cases) >= 3
    assert sum(case["category"] in {"multiturn", "long_conversation"} for case in cases) >= 8
    assert sum(bool(case.get("expected_tool")) for case in cases) >= 8


def test_every_rc2_case_declares_expected_runtime_contract() -> None:
    cases = load_cases(Path("eval/rc2_scenarios.jsonl"))
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        assert case["expected_intent"]
        assert isinstance(case["expected_grounded"], bool)
        assert isinstance(case["expected_fallback"], bool)
        assert isinstance(case["min_citations"], int)
        assert isinstance(case["require_citation_marker"], bool)
        assert case.get("answer_all_terms") or case.get("answer_any_terms") or case.get("forbidden_answer_terms")
        if case.get("expected_tool"):
            assert case.get("expected_tool_status") in {"success", "error"}


def test_answer_quality_requires_expected_facts_and_blocks_leaks() -> None:
    case = {
        "answer_all_terms": ["独秀峰", "靖江王府"],
        "forbidden_answer_terms": ["LLM_API_KEY="],
    }
    passed, failures = answer_quality(case, "景区以独秀峰和靖江王府为核心。[C1]")
    assert passed is True
    assert failures == []

    passed, failures = answer_quality(case, "独秀峰，LLM_API_KEY=secret")
    assert passed is False
    assert "missing:靖江王府" in failures
    assert "forbidden:LLM_API_KEY=" in failures


def test_rc2_thresholds_are_feature_freeze_quality_gates() -> None:
    assert THRESHOLDS["min_scenarios"] >= 30
    assert THRESHOLDS["min_conversations"] >= 20
    assert THRESHOLDS["answer_correctness"] >= 0.90
    assert THRESHOLDS["citation_compliance"] >= 0.85
    assert THRESHOLDS["intent_accuracy"] == 1.0
    assert THRESHOLDS["tool_selection_accuracy"] == 1.0
    assert THRESHOLDS["security_pass_rate"] == 1.0
