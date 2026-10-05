from app.modules.memory.service import mastery_decision


def test_supported_evidence_alone_never_promotes_mastery() -> None:
    state, reason = mastery_decision(
        evidence_count=5,
        correct_ratio=1.0,
        weight_score=5.0,
        context_count=3,
        independent_evidence_count=0,
        last_correct=True,
    )

    assert state == "learning"
    assert "独立证据" in reason


def test_mastery_requires_independent_evidence_across_contexts() -> None:
    proficient, _ = mastery_decision(
        evidence_count=3,
        correct_ratio=0.8,
        weight_score=1.8,
        context_count=2,
        independent_evidence_count=2,
        last_correct=True,
    )
    missing_context, reason = mastery_decision(
        evidence_count=4,
        correct_ratio=0.9,
        weight_score=3.2,
        context_count=1,
        independent_evidence_count=4,
        last_correct=True,
    )
    mastered, _ = mastery_decision(
        evidence_count=4,
        correct_ratio=0.9,
        weight_score=3.2,
        context_count=2,
        independent_evidence_count=3,
        last_correct=True,
    )

    assert proficient == "proficient"
    assert missing_context == "learning"
    assert "情境" in reason
    assert mastered == "mastered"


def test_latest_incorrect_independent_check_requires_consolidation() -> None:
    state, reason = mastery_decision(
        evidence_count=4,
        correct_ratio=0.9,
        weight_score=3.5,
        context_count=2,
        independent_evidence_count=3,
        last_correct=False,
    )

    assert state == "needs_consolidation"
    assert "最近一次" in reason
