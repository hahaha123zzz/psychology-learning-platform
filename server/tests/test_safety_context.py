"""Tutor 安全判断区分个人风险表达与课程/研究语境。"""

from app.modules.memory.service import is_crisis_content


def test_academic_discussion_of_suicide_is_not_personal_crisis() -> None:
    assert not is_crisis_content("在实验心理学教材中，什么是自杀意念的操作化定义？")
    assert not is_crisis_content("自残和自杀是心理学研究中的测量变量，论文如何区分？")


def test_personal_self_harm_intent_takes_priority() -> None:
    assert is_crisis_content("我最近不想活了。")
    assert is_crisis_content("我有自杀念头，今晚准备结束生命。")
    assert is_crisis_content("我做心理学论文时也在想自杀，担心自己会行动。")


def test_concern_for_another_person_gets_support() -> None:
    assert is_crisis_content("我的朋友说不想活了，我该怎么办？")


def test_generic_keyword_without_personal_or_academic_context_stays_conservative() -> None:
    assert is_crisis_content("suicide")
