"""Within-batch `reg` dedup (latest source_image wins) and cross-list merge."""

import re

_TIMESTAMP_RE = re.compile(r"Screenshot_(\d{8})_(\d{6})")


def _source_image_key(source_image: str) -> str:
    """Sortable key from a `Screenshot_YYYYMMDD_HHMMSS.jpg` filename."""
    match = _TIMESTAMP_RE.search(source_image)
    if not match:
        raise ValueError(f"unrecognized screenshot filename: {source_image!r}")
    return match.group(1) + match.group(2)


def dedupe_rows(rows: list[dict]) -> list[dict]:
    """Group by `reg`, keep the row with the latest `source_image` timestamp."""
    latest: dict[str, dict] = {}
    for row in rows:
        reg = row["reg"]
        if reg not in latest or _source_image_key(row["source_image"]) > _source_image_key(
            latest[reg]["source_image"]
        ):
            latest[reg] = row
    return list(latest.values())


def merge_lists(travelling: list[dict], waiting: list[dict], processing: list[dict]) -> list[dict]:
    """Union the three per-type lists into one row-per-truck list, tagging `status`
    and resolving cross-list `reg` conflicts (latest source_image wins, whole row)."""
    tagged = (
        [{**row, "status": "travelling"} for row in travelling]
        + [{**row, "status": "waiting"} for row in waiting]
        + [{**row, "status": "processing"} for row in processing]
    )
    return dedupe_rows(tagged)
