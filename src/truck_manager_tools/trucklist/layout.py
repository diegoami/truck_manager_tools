"""Row/column calibration: locate table rows and column x-ranges in a panel screenshot.

Column x-ranges are detected dynamically per image by OCR-ing the header row
(spec step 3). Row height is a constant calibrated against sample
screenshots at the fixed 2560x1600 game resolution (spec step 2); the first
row's y-position and the table's bottom edge are detected per image so the
row count can vary between screenshots (e.g. panel not fully scrolled to
the end, fewer trucks than fit on screen).
"""

from pathlib import Path

import pytesseract
from PIL import Image

from .schema import LIST_TYPES

# Calibrated against docs/specs sample batch (2026-08-22-1) at 2560x1600.
HEADER_SEARCH_BAND = (140, 195)  # y range to search for the column header row (title above, rows below)
FOOTER_CUTOFF_Y = 1546  # y where the game's bottom HUD bar begins
ROW_HEIGHT = 48  # constant row height in the truck list table
MIN_ROW_VISIBLE = ROW_HEIGHT // 2  # a row must have at least this much room before the footer

# Header label clustering: gaps below this (px) are treated as spaces within
# one multi-word label (e.g. "Fracht" + "an" + "Bord"); larger gaps are
# treated as the boundary between two columns' headers.
LABEL_WORD_GAP = 30

# Column headers with no text data to extract (icons only) — dropped after
# clustering, before the remaining headers are matched positionally to a
# list type's field names.
ICON_COLUMN_LABELS = {"Typ", "Status"}

_MIN_CONF = 40
_ROW_TEXT_HEIGHT = (12, 28)  # filters out icon-glyph OCR noise (much taller boxes, conf 0)


def _ocr_words(image: Image.Image, y_top: int, y_bottom: int) -> list[dict]:
    band = image.crop((0, y_top, image.width, y_bottom))
    data = pytesseract.image_to_data(band, lang="deu", output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text or int(data["conf"][i]) < _MIN_CONF:
            continue
        words.append(
            {
                "text": text,
                "left": data["left"][i],
                "top": data["top"][i] + y_top,
                "width": data["width"][i],
                "height": data["height"][i],
            }
        )
    return sorted(words, key=lambda w: w["left"])


def _cluster_labels(words: list[dict]) -> list[dict]:
    """Merge adjacent words into multi-word column labels."""
    if not words:
        return []
    clusters = [[words[0]]]
    for word in words[1:]:
        prev = clusters[-1][-1]
        if word["left"] - (prev["left"] + prev["width"]) <= LABEL_WORD_GAP:
            clusters[-1].append(word)
        else:
            clusters.append([word])
    labels = []
    for cluster in clusters:
        labels.append(
            {
                "text": " ".join(w["text"] for w in cluster),
                "left": min(w["left"] for w in cluster),
                "right": max(w["left"] + w["width"] for w in cluster),
                "top": min(w["top"] for w in cluster),
                "bottom": max(w["top"] + w["height"] for w in cluster),
            }
        )
    return labels


def _header_labels(image: Image.Image) -> list[dict]:
    words = _ocr_words(image, *HEADER_SEARCH_BAND)
    return _cluster_labels(words)


def locate_columns(image_path: Path, list_type: str) -> dict[str, tuple[int, int]]:
    """Return {column_name: (left, right)} x-pixel bounds, from the header row."""
    image = Image.open(image_path)
    labels = _header_labels(image)
    if not labels:
        raise ValueError(f"no header labels detected in {image_path}")

    # Boundary between two columns = midpoint of the gap between their header
    # labels, computed over *all* headers (icon columns included) so the
    # spacing around a dropped icon column still lands on the right column.
    bounds = []
    for i, label in enumerate(labels):
        left = 0 if i == 0 else (labels[i - 1]["right"] + label["left"]) // 2
        right = image.width if i == len(labels) - 1 else (label["right"] + labels[i + 1]["left"]) // 2
        bounds.append((label["text"], left, right))

    fields = [f for f in LIST_TYPES[list_type] if f != "source_image"]
    data_bounds = [(text, left, right) for text, left, right in bounds if text not in ICON_COLUMN_LABELS]
    if len(data_bounds) != len(fields):
        raise ValueError(
            f"{image_path}: detected {len(data_bounds)} data column header(s) "
            f"{[t for t, _, _ in data_bounds]!r} but list type {list_type!r} expects "
            f"{len(fields)} fields {fields!r}"
        )
    return {field: (left, right) for field, (_text, left, right) in zip(fields, data_bounds)}


def locate_rows(image_path: Path, list_type: str) -> list[tuple[int, int]]:
    """Return (top, bottom) y-pixel bounds for each data row in the table."""
    image = Image.open(image_path)
    labels = _header_labels(image)
    header_bottom = max((label["bottom"] for label in labels), default=HEADER_SEARCH_BAND[1])

    words = _ocr_words(image, header_bottom, FOOTER_CUTOFF_Y)
    row_text_words = [w for w in words if _ROW_TEXT_HEIGHT[0] <= w["height"] <= _ROW_TEXT_HEIGHT[1]]
    if not row_text_words:
        return []
    first_row_top = min(w["top"] for w in row_text_words)

    rows = []
    top = first_row_top
    while top + MIN_ROW_VISIBLE <= FOOTER_CUTOFF_Y:
        rows.append((top, top + ROW_HEIGHT))
        top += ROW_HEIGHT
    return rows
