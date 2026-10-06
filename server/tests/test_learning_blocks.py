import asyncio
from types import SimpleNamespace

import pytest

from app.core.errors import ApiError
from app.modules.tutor import service as tutor_service
from app.modules.tutor.planner import decide_progress
from app.modules.tutor.service import (
    EvidencePackage,
    apply_presentation_preferences,
    build_learning_blocks,
    example_message,
    generate_grounded_answer,
    hint_message,
    misconception_repair_message,
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

    assert [block["type"] for block in blocks] == ["Question", "Transition"]
    assert all(block["schema_version"] == "learning-block.v1" for block in blocks)
    assert blocks[0]["prompt"] == "请解释自变量和因变量的区别。"
    assert blocks[0]["evidence_refs"] == []
    assert blocks[0]["allowed_actions"] == []
    assert blocks[1]["next_action"] == "wait_for_student"


def test_learning_blocks_mark_only_standalone_practice_question_as_question() -> None:
    standalone = build_learning_blocks(
        session_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        state="practice",
        state_version=4,
        message="迁移练习：请举一个体现“内部效度”的新例子，并说明理由。",
        action="wait_for_student",
        hint_level=1,
    )
    terminal_example = build_learning_blocks(
        session_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        state="practice",
        state_version=5,
        message=(
            "教材中的例子：……\n完整讲解：……\n"
            "迁移练习：请举一个体现“内部效度”的新例子，并说明理由。"
        ),
        action="show_example",
        hint_level=3,
    )
    mixed_without_action_marker = build_learning_blocks(
        session_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        state="practice",
        state_version=6,
        message=(
            "请先看下面的解释。\n"
            "迁移练习：请举一个体现“内部效度”的新例子，并说明理由。"
        ),
        action="wait_for_student",
        hint_level=1,
    )

    assert standalone[0]["type"] == "Question"
    assert standalone[0]["id"].endswith(":4:question")
    assert standalone[0]["prompt"] == "迁移练习：请举一个体现“内部效度”的新例子，并说明理由。"
    assert terminal_example[0]["type"] == "TutorExplanation"
    assert mixed_without_action_marker[0]["type"] == "TutorExplanation"


@pytest.mark.parametrize("state", ["teach", "hint"])
def test_canonical_hint_repair_emits_ordered_inert_blocks(state: str) -> None:
    session_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    focus = ["内部效度", "实验控制"]
    message = (
        hint_message(2, focus)
        + "\n"
        + misconception_repair_message(["合成教材段落"], focus)
    )

    blocks = build_learning_blocks(
        session_id=session_id,
        state=state,
        state_version=9,
        message=message,
        action="wait_for_student",
        hint_level=2,
    )

    assert [block["type"] for block in blocks] == [
        "Hint",
        "Correction",
        "Transition",
    ]
    assert [block["id"] for block in blocks[:2]] == [
        f"{session_id}:9:hint",
        f"{session_id}:9:correction",
    ]
    assert "\n".join(block["text"] for block in blocks[:2]) == message
    assert all(block["evidence_refs"] == [] for block in blocks[:2])
    assert all(block["allowed_actions"] == [] for block in blocks[:2])
    assert all(block["schema_version"] == "learning-block.v1" for block in blocks[:2])


@pytest.mark.parametrize(
    ("state", "action", "hint_level", "message_transform", "expected_type"),
    [
        (
            "teach",
            "wait_for_student",
            2,
            lambda message: "偏好改写：" + message,
            "TutorExplanation",
        ),
        ("hint", "wait_for_student", 2, lambda message: message[:-1], "TutorExplanation"),
        ("hint", "wait_for_student", 1, lambda message: message, "TutorExplanation"),
        (
            "hint",
            "wait_for_student",
            2,
            lambda message: message.replace("\n", " "),
            "TutorExplanation",
        ),
        (
            "hint",
            "wait_for_student",
            2,
            lambda message: message + "\n额外文字",
            "TutorExplanation",
        ),
        ("check", "wait_for_student", 2, lambda message: message, "Question"),
        ("teach", "show_example", 2, lambda message: message, "TutorExplanation"),
    ],
)
def test_noncanonical_hint_repair_fails_closed_to_existing_block_mapping(
    state: str, action: str, hint_level: int, message_transform, expected_type: str
) -> None:
    original = (
        hint_message(2, ["内部效度", "实验控制"])
        + "\n"
        + misconception_repair_message(["合成教材段落"], ["内部效度", "实验控制"])
    )
    message = message_transform(original)

    blocks = build_learning_blocks(
        session_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        state=state,
        state_version=10,
        message=message,
        action=action,
        hint_level=hint_level,
    )

    assert blocks[0]["type"] == expected_type
    assert blocks[0].get("text", blocks[0].get("prompt")) == message
    if expected_type == "TutorExplanation":
        assert blocks[0]["allowed_actions"] == ["OPEN_EVIDENCE"]


def test_terminal_show_example_keeps_legacy_explanation_block() -> None:
    message = (
        hint_message(3, ["内部效度"])
        + "\n"
        + misconception_repair_message(["合成教材段落"], ["内部效度"])
    )
    blocks = build_learning_blocks(
        session_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        state="practice",
        state_version=11,
        message=message,
        action="show_example",
        hint_level=3,
    )

    assert blocks[0]["type"] == "TutorExplanation"
    assert blocks[0]["text"] == message


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


def test_guided_learning_preferences_format_display_without_claiming_evidence() -> None:
    same_response = (
        "Attention control selects relevant signals. "
        "For example, attention control selects a target voice. "
        "Attention control reduces distraction from irrelevant signals."
    )

    concise_example_first = apply_presentation_preferences(
        same_response,
        response_length="CONCISE",
        example_order="EXAMPLE_FIRST",
        include_evidence_prefix=False,
    )
    detailed_concept_first = apply_presentation_preferences(
        same_response,
        response_length="DETAILED",
        example_order="CONCEPT_FIRST",
        include_evidence_prefix=False,
    )

    assert concise_example_first == (
        "For example, attention control selects a target voice"
    )
    assert detailed_concept_first.startswith(
        "Attention control selects relevant signals"
    )
    assert "For example, attention control" in detailed_concept_first
    assert len(detailed_concept_first) > len(concise_example_first)
    assert "根据教材：" not in concise_example_first
    assert "根据教材：" not in detailed_concept_first


def test_internal_grounded_answer_applies_preferences_before_joining_sentences(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        tutor_service, "get_settings", lambda: SimpleNamespace(llm_provider="internal")
    )
    package = EvidencePackage(
        package_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        course_id="01ARZ3NDEKTSV4RRFFQ69G5FAA",
        query="independent variable manipulated researcher for example",
        retrieval_version="test-v1",
        items=[
            {
                "text": (
                    "An independent variable is manipulated by the researcher. "
                    "For example, the researcher changes study time."
                )
            }
        ],
    )

    concise, provider = asyncio.run(
        generate_grounded_answer(
            None,
            query=package.query,
            package=package,
            user_id="01ARZ3NDEKTSV4RRFFQ69G5FABB",
            purpose="course_qa",
            response_length="CONCISE",
            example_order="EXAMPLE_FIRST",
        )
    )
    detailed, _ = asyncio.run(
        generate_grounded_answer(
            None,
            query=package.query,
            package=package,
            user_id="01ARZ3NDEKTSV4RRFFQ69G5FABB",
            purpose="course_qa",
            response_length="DETAILED",
            example_order="CONCEPT_FIRST",
        )
    )

    assert provider == "internal"
    assert concise.startswith("根据教材：For example,")
    assert "independent variable" not in concise
    assert detailed.startswith("根据教材：An independent variable")
    assert "For example" in detailed
    assert "independent variable" in detailed


def test_tutor_microcycle_uses_chapter_terms_and_does_not_invent_examples() -> None:
    texts = [
        "Classical conditioning pairs stimuli. For example, a bell may be paired with food."
    ]

    assert "Classical conditioning" in hint_message(1, ["Classical conditioning"])
    assert "教材中的例子" in example_message(texts, ["conditioning"])
    assert "For example" in example_message(texts, ["conditioning"])
    assert "不急着判断对错" in misconception_repair_message(texts, ["conditioning"])
    assert "暂不提供例子" in example_message([], [])
    assert "明确标记的例子" in example_message(["Concept definition."], [])


def test_terminal_hint_practice_gate_rejects_before_mutating_session(monkeypatch) -> None:
    session = SimpleNamespace(
        state="hint",
        hint_level=2,
        version=7,
        material_version_id="material-version-id",
        chapter_object_id=None,
        tutor_message="上一次的提示",
    )

    async def load_chapter_texts(
        _db, *, material_version_id: str, chapter_object_id: str | None
    ):
        assert material_version_id == "material-version-id"
        assert chapter_object_id is None
        return ["Internal validity depends on control of experimental conditions."]

    monkeypatch.setattr(tutor_service, "load_chapter_texts", load_chapter_texts)
    policy = {
        "version": "effective-policy.v1",
        "allowed_actions": ["diagnose", "teach", "check", "hint"],
        "max_hints": 3,
        "max_support_gradient": 3,
    }

    with pytest.raises(ApiError) as raised:
        asyncio.run(
            tutor_service.respond_learning_session(
                None,
                session,
                "我不知道",
                effective_policy=policy,
            )
        )

    assert raised.value.status_code == 403
    assert raised.value.code == "TEACHING_ACTION_NOT_ALLOWED"
    assert raised.value.details["action"] == "practice"
    assert (session.state, session.version, session.hint_level, session.tutor_message) == (
        "hint",
        7,
        2,
        "上一次的提示",
    )
