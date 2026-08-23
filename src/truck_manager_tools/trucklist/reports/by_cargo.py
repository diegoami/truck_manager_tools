"""v1 report: truck count grouped by `cargo`."""

from collections import Counter

from .registry import register


def by_cargo_report(trucks: list[dict]) -> list[dict]:
    counts = Counter(truck.get("cargo") for truck in trucks)
    return [{"cargo": cargo, "count": count} for cargo, count in counts.most_common()]


register("by_cargo", by_cargo_report)
