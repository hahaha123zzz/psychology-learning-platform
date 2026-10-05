from app.modules.tutor.planner import decide_progress
from app.modules.tutor.service import build_learning_blocks


def test_learning_blocks_are_whitelisted_and_versioned() -> None:
    blocks = build_learning_blocks(
        session_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        state="check",
        state_version=3,
        message="请解释自变量和因变量的区别。",
        action="wait_for_student",
        hint_level=1,
    )

    assert [block["type"] for block in blocks] == ["TutorExplanation", "Transition"]
    assert all(block["schema_version"] == "learning-block.v1" for block in blocks)
    assert blocks[0]["allowed_actions"] == ["OPEN_EVIDENCE"]
    assert blocks[1]["next_action"] == "wait_for_student"


def test_completed_learning_block_does_not_claim_mastery() -> None:
    blocks = build_learning_blocks(
        session_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        state="completed",
        state_version=7,
        message="本节学习已完成。",
        action="complete",
        hint_level=2,
    )

    assert blocks[-1]["type"] == "TaskCompletion"
    assert blocks[-1]["completion"] == "activity_completed"
    assert "mastery" not in blocks[-1]


def test_progress_planner_has_four_explainable_states_and_safe_fallback() -> None:
    assert decide_progress(
        task_status="completed", task_state="completed", due_review_count=0
    )["decision"] == "complete"
    assert decide_progress(
        task_status="active", task_state="check", due_review_count=1
    )["decision"] == "review"
    assert decide_progress(
        task_status="active", task_state="diagnose", due_review_count=0
    )["decision"] == "remediate"
    result = decide_progress(task_status="active", task_state="check", due_review_count=0)
    assert result["decision"] == "continue"
    assert result["fallback"] == "continue"
