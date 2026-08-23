"""OCR each row/column cell (tesseract via pytesseract), per-column tuned."""

from pathlib import Path


def extract_rows(image_path: Path, list_type: str) -> list[dict]:
    """Return one dict per data row, fields per schema.LIST_TYPES[list_type],
    plus `source_image`."""
    raise NotImplementedError
