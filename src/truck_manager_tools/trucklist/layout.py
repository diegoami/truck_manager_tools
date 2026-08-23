"""Row/column calibration: locate table rows and column x-ranges in a panel screenshot."""

from pathlib import Path


def locate_rows(image_path: Path, list_type: str) -> list[tuple[int, int]]:
    """Return (top, bottom) y-pixel bounds for each data row in the table."""
    raise NotImplementedError


def locate_columns(image_path: Path, list_type: str) -> dict[str, tuple[int, int]]:
    """Return {column_name: (left, right)} x-pixel bounds, from the header row."""
    raise NotImplementedError
