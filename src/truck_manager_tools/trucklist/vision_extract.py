"""Claude vision call: classify a screenshot's panel type and extract every
visible row's fields in one call. See docs/specs/trucklist-parser.md,
"OCR approach" / "v3: Claude Code CLI (headless)".

Shells out to the `claude` CLI in headless mode (`-p`), rather than calling
the Anthropic API directly, so extraction draws on the user's Claude Pro/Max
subscription quota instead of separate pay-per-token API billing. Requires
`claude` on PATH and already logged in (`claude login`) — no
`ANTHROPIC_API_KEY` should be set, since that switches auth to the (billed)
API instead of the subscription session.
"""

import json
import subprocess
from pathlib import Path

from .schema import vision_response_schema

PROMPT_TEMPLATE = """\
Read the image at {image_path} (use your Read tool).

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
    """Classify and extract every row from one screenshot via a headless
    `claude -p` call.

    Returns {"list_type": str, "trucks": [row dicts]}, each row tagged with
    `source_image` (not `status` — that's added later, during merge).
    """
    image_path = Path(image_path).resolve()
    prompt = PROMPT_TEMPLATE.format(image_path=image_path)

    result = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(vision_response_schema()),
            "--allowedTools",
            "Read",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed for {image_path} (exit {result.returncode}): {result.stderr}")

    response = json.loads(result.stdout)
    if response.get("is_error"):
        raise RuntimeError(f"claude -p reported an error for {image_path}: {response}")

    data = response["structured_output"]
    for truck in data["trucks"]:
        truck["source_image"] = image_path.name
    return data
