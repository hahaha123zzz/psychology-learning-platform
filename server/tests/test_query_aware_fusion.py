from app.modules.knowledge.fusion import text_channel_weights, unavailable_modalities
from app.modules.knowledge.service import _rrf_fuse


def test_query_aware_fusion_changes_text_channel_priority() -> None:
    fused = _rrf_fuse(
        [("sparse-first", 1.0)],
        [("dense-first", 1.0)],
        channel_priors={"sparse": 0.8, "dense": 0.2},
    )

    assert fused[0][0] == "sparse-first"
    assert text_channel_weights({"sparse": 0.8, "dense": 0.2}) == {
        "sparse": 0.8,
        "dense": 0.2,
    }


def test_query_aware_fusion_excludes_unimplemented_visual_channel() -> None:
    priors = {"visual": 0.7, "dense": 0.2, "sparse": 0.1}

    assert text_channel_weights(priors) == {
        "sparse": 1 / 3,
        "dense": 2 / 3,
    }
    assert unavailable_modalities(priors) == ("visual",)
