"""查询计划到已实现检索通道的权重映射。"""

from __future__ import annotations

TEXT_CHANNELS = frozenset({"dense", "sparse"})


def text_channel_weights(channel_priors: dict[str, float] | None) -> dict[str, float]:
    """仅返回已有文本通道的非负权重，并归一化为和为一。"""
    if not channel_priors:
        return {"dense": 0.5, "sparse": 0.5}
    weights = {
        channel: max(float(channel_priors.get(channel, 0.0)), 0.0)
        for channel in TEXT_CHANNELS
    }
    total = sum(weights.values())
    if total == 0:
        return {"dense": 0.5, "sparse": 0.5}
    return {channel: value / total for channel, value in weights.items()}


def unavailable_modalities(channel_priors: dict[str, float] | None) -> tuple[str, ...]:
    if not channel_priors:
        return ()
    return tuple(
        sorted(
            channel
            for channel, weight in channel_priors.items()
            if channel not in TEXT_CHANNELS and weight > 0
        )
    )
