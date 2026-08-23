"""Claude vision call: classify a screenshot's panel type and extract every
visible row's fields in one call. See docs/specs/trucklist-parser.md,
"OCR approach" / "v2: Claude vision"."""

import base64
import json
from pathlib import Path

import anthropic

from .schema import vision_response_schema

MODEL = "claude-opus-5"

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

PROMPT = """\
This is a screenshot from the game Truck Manager. It shows one of three \
floating list panels, identified by its German title in the top-left, \
below the game's top HUD bar:

- "Unterwegs" -> list_type "travelling": trucks currently en route.
  Columns: Reg, Route, Ursprung (origin), Ziel (destination), Fracht \
(cargo), Fracht an Bord (cargo_onboard), Abgeschlossen (completed_pct), \
Ankunft (eta). Ignore the Typ column (a route-type icon/color bar, no \
text) and the Fortschritt column (a vehicle icon, no text).
- "Im Leerlauf" -> list_type "waiting": idle trucks with no route \
assigned. Columns: Reg, TÜV (tuv), Abnutzung (wear_pct), Route, Ursprung \
(origin), Ziel (destination), Fracht (cargo), Maximale Last (max_load), \
Die Nachfrage von heute (demand_today). Ignore the Typ column and the \
trailing Zeit column (always empty).
- "Ausstehend" -> list_type "processing": trucks with something pending \
(repair/charging/cargo). Columns: Reg, Route, Standort (location), Ziel \
(destination), Fracht (cargo), Maximale Last (max_load), Die Nachfrage \
von heute (demand_today), Bereit in (ready_in). Ignore the Typ column \
and the Status column (a wrench/lightning/clock icon, no text).

Identify which panel this screenshot shows, then extract every visible \
truck row in the table — including partially-cut-off rows at the very \
top or bottom of the panel, if their Reg value is legible. Read each \
field exactly as displayed (raw text, e.g. "26,265 kg" or "87.7 m3" or \
"98.0%" or "00:31:25") — do not convert units, round numbers, or \
reformat. `reg` is a unique identifier per truck; read it especially \
carefully, character by character. Only fill in fields that column list \
above; leave every other field null. If the panel is empty (zero trucks \
visible), return an empty `trucks` array.
"""


def extract_rows(image_path: Path) -> dict:
    """Classify and extract every row from one screenshot via Claude vision.

    Returns {"list_type": str, "trucks": [row dicts]}, each row tagged with
    `source_image` (not `status` — that's added later, during merge).
    """
    image_path = Path(image_path)
    media_type = _MEDIA_TYPES.get(image_path.suffix.lower())
    if media_type is None:
        raise ValueError(f"unsupported image type: {image_path.suffix!r} ({image_path})")

    image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_data},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": vision_response_schema()}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    result = json.loads(text)

    for truck in result["trucks"]:
        truck["source_image"] = image_path.name
    return result
