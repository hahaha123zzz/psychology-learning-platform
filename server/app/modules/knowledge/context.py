"""从检索命中组装受预算约束的 GenerationUnit。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationUnit:
    source_object_id: str | None
    evidence_id: str
    material_version_id: str
    objects: tuple[dict, ...]
    text: str


def assemble_generation_units(
    items: list[dict], *, context_budget_chars: int, max_units: int = 3
) -> list[GenerationUnit]:
    """主命中优先，按已确认闭包补充上下文；对象覆盖范围去重。"""
    remaining = context_budget_chars
    covered: set[str] = set()
    units: list[GenerationUnit] = []
    for item in items:
        if len(units) >= max_units or remaining <= 0:
            break
        object_id = item.get("source_object_id")
        if object_id and object_id in covered:
            continue
        objects = [
            {
                "object_id": object_id,
                "object_type": item.get("object_type", "paragraph"),
                "physical_page": item.get("physical_page"),
                "bbox": item.get("bbox"),
                "text": item["text"],
                "role": "primary",
            }
        ]
        if object_id:
            covered.add(object_id)
        text_parts = [item["text"]]
        for neighbor in item.get("closure", []):
            neighbor_id = neighbor.get("object_id")
            neighbor_text = neighbor.get("text", "")
            if not neighbor_text or (neighbor_id and neighbor_id in covered):
                continue
            if len("\n".join(text_parts)) + len(neighbor_text) > remaining:
                continue
            objects.append({**neighbor, "role": "closure"})
            text_parts.append(neighbor_text)
            if neighbor_id:
                covered.add(neighbor_id)
        unit_text = "\n".join(text_parts)
        if len(unit_text) > remaining:
            unit_text = unit_text[:remaining]
            objects[0] = {**objects[0], "text": unit_text}
        if not unit_text:
            continue
        remaining -= len(unit_text)
        units.append(
            GenerationUnit(
                source_object_id=object_id,
                evidence_id=item["evidence_id"],
                material_version_id=item["material_version_id"],
                objects=tuple(objects),
                text=unit_text,
            )
        )
    return units
