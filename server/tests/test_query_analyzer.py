from app.modules.knowledge.query import analyze_query


def test_query_analyzer_extracts_scope_without_model_call() -> None:
    plan = analyze_query("请比较第 3 章第 42 页的两种设计")

    assert plan.question_type == "comparison"
    assert plan.target_chapters == ("3",)
    assert plan.target_pages == (42,)
    assert plan.channel_priors == {"dense": 0.5, "sparse": 0.5, "visual": 0.0}


def test_query_analyzer_routes_figure_table_and_formula_questions() -> None:
    assert analyze_query("图 4-3 表示什么？").question_type == "visual"
    assert analyze_query("表 2 的均值是多少？").question_type == "table"
    assert analyze_query("这个公式的含义是什么？").question_type == "formula"
