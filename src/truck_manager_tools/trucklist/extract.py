"""OCR each row/column cell (tesseract via pytesseract), per-column tuned."""

import re
from pathlib import Path

import pytesseract
from PIL import Image

from . import layout
from .schema import LIST_TYPES

# Per-field tesseract config. psm 6 (uniform block of text) reads these
# cropped UI cells far more reliably than psm 7 (single line) despite each
# cell holding one line — psm 7 was tested and consistently misreads even
# clean, unambiguous crops here. A character whitelist sharply cuts misreads
# on fields with a known alphabet (dashes included — several fields render
# "-" as a not-applicable placeholder, e.g. demand_today with nothing on
# order).
_DEFAULT_CONFIG = "--psm 6"
_PERCENT_CONFIG = '--psm 6 -c tessedit_char_whitelist="0123456789.,%-"'
_TIME_CONFIG = '--psm 6 -c tessedit_char_whitelist="0123456789:-"'
_WEIGHT_CONFIG = '--psm 6 -c tessedit_char_whitelist="0123456789.,/ mkg3-"'
_TUV_CONFIG = '--psm 6 -c tessedit_char_whitelist="0123456789T -"'

_FIELD_CONFIG = {
    "completed_pct": _PERCENT_CONFIG,
    "wear_pct": _PERCENT_CONFIG,
    "eta": _TIME_CONFIG,
    "ready_in": _TIME_CONFIG,
    "cargo_onboard": _WEIGHT_CONFIG,
    "max_load": _WEIGHT_CONFIG,
    "demand_today": _WEIGHT_CONFIG,
    "tuv": _TUV_CONFIG,
}

_WHITESPACE_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _ocr_cell(image: Image.Image, bounds: tuple[int, int, int, int], config: str) -> str:
    cell = layout.preprocess_for_cell_ocr(image.crop(bounds))
    text = pytesseract.image_to_string(cell, lang="deu", config=config)
    return _clean(text)


def extract_rows(image_path: Path, list_type: str) -> list[dict]:
    """Return one dict per data row, fields per schema.LIST_TYPES[list_type],
    plus `source_image`."""
    image = Image.open(image_path)
    columns = layout.locate_columns(image_path, list_type)
    rows = layout.locate_rows(image_path, list_type)
    fields = [f for f in LIST_TYPES[list_type] if f != "source_image"]
    source_image = Path(image_path).name

    results = []
    for top, bottom in rows:
        reg_left, reg_right = columns["reg"]
        reg = _ocr_cell(image, (reg_left, top, reg_right, bottom), _DEFAULT_CONFIG)
        if not reg:
            continue  # past the last real row in this screenshot

        row = {"reg": reg, "source_image": source_image}
        for field in fields:
            if field == "reg":
                continue
            left, right = columns[field]
            config = _FIELD_CONFIG.get(field, _DEFAULT_CONFIG)
            row[field] = _ocr_cell(image, (left, top, right, bottom), config)
        results.append(row)
    return results
