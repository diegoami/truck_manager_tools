"""Panel-type detection: OCR the panel title and match against schema.PANEL_TITLES."""

from difflib import get_close_matches
from pathlib import Path

import pytesseract
from PIL import Image

from .schema import PANEL_TITLES

# Calibrated against docs/specs sample batch (2026-08-22-1) at 2560x1600: the
# panel title sits just below the game's top HUD bar and to the right of its
# icon, well clear of both the HUD bar above and the column header below.
TITLE_BAND_Y = (90, 145)
TITLE_BAND_X = (0, 500)

_MATCH_CUTOFF = 0.6


def classify_image(image_path: Path) -> str:
    """Return the list type ('travelling' / 'waiting' / 'processing') for a screenshot."""
    image = Image.open(image_path)
    crop = image.crop((TITLE_BAND_X[0], TITLE_BAND_Y[0], TITLE_BAND_X[1], TITLE_BAND_Y[1]))
    text = pytesseract.image_to_string(crop, lang="deu", config="--psm 7").strip()

    matches = get_close_matches(text, PANEL_TITLES.keys(), n=1, cutoff=_MATCH_CUTOFF)
    if not matches:
        raise ValueError(
            f"{image_path}: could not classify panel title (OCR read {text!r}, "
            f"expected one of {list(PANEL_TITLES)!r})"
        )
    return PANEL_TITLES[matches[0]]
