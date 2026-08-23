"""Panel-type detection: OCR the panel title and match against schema.PANEL_TITLES."""

from pathlib import Path


def classify_image(image_path: Path) -> str:
    """Return the list type ('travelling' / 'waiting' / 'processing') for a screenshot."""
    raise NotImplementedError
