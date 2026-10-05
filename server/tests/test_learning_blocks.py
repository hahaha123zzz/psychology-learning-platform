from app.modules.tutor.planner import decide_progress
from app.modules.tutor.service import (
    apply_presentation_preferences,
    build_learning_blocks,
)


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


def test_tutor_presentation_preferences_change_order_and_length_without_new_claims() -> None:
    answer = "根据教材：概念定义。 例如，教材中的例子。 进一步解释。"

    concise = apply_presentation_preferences(
        answer, response_length="CONCISE", example_order="EXAMPLE_FIRST"
    )
    detailed = apply_presentation_preferences(
        answer, response_length="DETAILED", example_order="EXAMPLE_FIRST"
    )

    assert concise == "根据教材：例如，教材中的例子。"
    assert detailed == "根据教材：例如，教材中的例子。 概念定义。 进一步解释。"


def test_adaptive_example_order_responds_to_example_question() -> None:
    answer = "根据教材：概念定义。 例如，教材中的例子。"

    example_question = apply_presentation_preferences(
        answer,
        response_length="BALANCED",
        example_order="ADAPTIVE",
        query="能举个例子吗？",
    )
    concept_question = apply_presentation_preferences(
        answer,
        response_length="BALANCED",
        example_order="ADAPTIVE",
        query="这个概念是什么？",
    )

    assert example_question.startswith("根据教材：例如，教材中的例子。")
    assert concept_question.startswith("根据教材：概念定义。")
