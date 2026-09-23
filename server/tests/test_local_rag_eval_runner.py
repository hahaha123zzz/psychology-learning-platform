import runpy
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "run_local_rag_eval.py"
_canonical_object_id = runpy.run_path(str(RUNNER))["_canonical_object_id"]


def test_eval_runner_does_not_map_paragraph_caption_to_image_object() -> None:
    item = {
        "physical_page": 12,
        "object_type": "paragraph",
        "text": "FIGURE 1.2 A caption beside the image.",
        "source_object_id": "real-paragraph-id",
    }
    objects = [
        {
            "id": "annotated-image-id",
            "page": 12,
            "object_type": "image",
            "text_anchor": "FIGURE 1.2",
        }
    ]

    assert _canonical_object_id(item, objects) == "real-paragraph-id"


def test_eval_runner_maps_same_type_same_page_anchor() -> None:
    item = {
        "physical_page": 12,
        "object_type": "paragraph",
        "text": "An independent variable is manipulated by the experimenter.",
        "source_object_id": "real-paragraph-id",
    }
    objects = [
        {
            "id": "annotated-paragraph-id",
            "page": 12,
            "object_type": "paragraph",
            "text_anchor": "An independent variable is manipulated",
        }
    ]

    assert _canonical_object_id(item, objects) == "annotated-paragraph-id"
