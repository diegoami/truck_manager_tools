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
# treated as the boundary between two columns' headers. Calibrated against
# the sample batch: intra-label word gaps observed up to 12px, the tightest
# real inter-column gap observed (waiting panel, "Last" -> "Die") is 29px.
LABEL_WORD_GAP = 20

# Column headers with no text data to extract (icons only, or — for "Zeit"
# on the waiting panel — always empty in samples so far) — dropped after
# clustering, before the remaining headers are matched positionally to a
# list type's field names. "Fortschritt" (travelling) renders a vehicle
# icon with no percentage text in any sample row.
ICON_COLUMN_LABELS = {"Typ", "Status", "Zeit", "Fortschritt"}

# How far past its header's right edge the rightmost column may extend.
# Calibrated: real values in the sample sit within ~1px of their header's
# right edge, while background map labels bleeding through the panel's
# transparency start appearing ~55px past it.
LAST_COLUMN_PADDING = 40

# Calibrated absolute right edge of the Typ column's truck-icon graphic —
# see the comment at its use site.
TYP_ICON_RIGHT_EDGE = 195

# Upscaling + hard binarization measurably improves OCR accuracy and
# reliability on this game's UI font (light text on a dark, semi-transparent
# panel) — without it, header words occasionally drop below the confidence
# threshold entirely (e.g. "Reg" on one sample screenshot), and cell text
# misreads more (e.g. a "3" digit reading as "5"). Shared by header/row
# detection here and by per-cell OCR in extract.py.
UPSCALE = 3
# Header words are used only for position, not exact text, and the header
# band is mostly background (a handful of short words scattered across the
# full image width), so a per-crop adaptive threshold has little text to
# calibrate against. A low fixed threshold is robust enough here: it already
# clears the dimmest text color observed (the sorted-column highlight,
# green, max ~153 gray).
HEADER_BINARIZE_THRESHOLD = 120
# Cell text brightness varies a little between screenshots (observed
# max-white as low as ~209 gray and as high as ~248 elsewhere), and cells
# with a colored badge background (e.g. cargo's pill) have a different
# brightness profile again. A per-crop adaptive threshold (relative to each
# crop's own brightness) was tried to handle both, but it overcorrected:
# badge-background cells lost their text entirely instead of misreading it.
# A single fixed threshold, tuned against plain-background cells (the
# majority), reads those reliably and degrades to partial/misread text
# rather than blank on the rest — the better failure mode for v1's raw
# strings. Known gap: an occasional screenshot's text renders dim enough
# (~209) that this still misreads it (see spec's open questions).
CELL_BINARIZE_THRESHOLD = 190

# Low: header/row-anchor words are used only for position, not their exact
# text, and the German language pack sometimes merges two header words into
# one low-confidence blob (e.g. "Bereit in" -> "Bereitin!" at conf 33) —
# still positionally correct, so worth keeping rather than filtering out.
_MIN_CONF = 10
_ROW_TEXT_HEIGHT = (12, 28)  # filters out icon-glyph OCR noise (much taller boxes, conf 0)


def preprocess_for_header_ocr(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    scaled = gray.resize((gray.width * UPSCALE, gray.height * UPSCALE), Image.LANCZOS)
    return scaled.point(lambda p: 255 if p > HEADER_BINARIZE_THRESHOLD else 0)


def preprocess_for_cell_ocr(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    scaled = gray.resize((gray.width * UPSCALE, gray.height * UPSCALE), Image.LANCZOS)
    return scaled.point(lambda p: 255 if p > CELL_BINARIZE_THRESHOLD else 0)


def _ocr_words(image: Image.Image, y_top: int, y_bottom: int) -> list[dict]:
    band = image.crop((0, y_top, image.width, y_bottom))
    pre = preprocess_for_header_ocr(band)
    data = pytesseract.image_to_data(pre, lang="deu", output_type=pytesseract.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text or int(data["conf"][i]) < _MIN_CONF:
            continue
        words.append(
            {
                "text": text,
                "left": data["left"][i] // UPSCALE,
                "top": data["top"][i] // UPSCALE + y_top,
                "width": data["width"][i] // UPSCALE,
                "height": data["height"][i] // UPSCALE,
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
        if i == 0:
            left = 0
        else:
            left = (labels[i - 1]["right"] + label["left"]) // 2
            if labels[i - 1]["text"] == "Typ":
                # Typ renders a truck-icon graphic much wider than its header
                # text, so the header-text midpoint underestimates its true
                # right edge and bleeds icon pixels into this column's crop.
                # Unlike a text column's width, the icon's width doesn't vary
                # by list type (same graphic), so anchor on its calibrated
                # absolute right edge instead of anything header-relative —
                # a header-relative fix (e.g. "next header's left minus a
                # pad") broke `route`, whose "Langstrecke" data starts well
                # left of the "Route" header it sits under.
                left = max(left, TYP_ICON_RIGHT_EDGE)
        if i == len(labels) - 1:
            # The panel is semi-transparent, so extending the last column all
            # the way to the image edge picks up faint map labels bleeding
            # through the background beyond the real data — cap it close to
            # the header instead.
            right = min(image.width, label["right"] + LAST_COLUMN_PADDING)
        else:
            right = (label["right"] + labels[i + 1]["left"]) // 2
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
