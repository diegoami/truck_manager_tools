"""trucklist: parse Truck Manager screenshot batches into structured JSON.

See docs/specs/trucklist-parser.md for the full pipeline design.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import typer

from .dedupe import dedupe_rows, merge_lists
from .reports.registry import REPORTS
from .schema import project_row
from .vision_extract import extract_rows

# Importing this module registers the "by_cargo" report.
from .reports import by_cargo  # noqa: F401

app = typer.Typer(help="Parse Truck Manager screenshot batches into structured JSON.")

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[4] / "truck_manager_data" / "data"
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def _data_root(data_root: Path | None) -> Path:
    if data_root is not None:
        return data_root
    env = os.environ.get("TMT_DATA_ROOT")
    return Path(env) if env else DEFAULT_DATA_ROOT


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _to_markdown_table(rows: list[dict]) -> str:
    if not rows:
        return "(no data)\n"
    columns = list(rows[0].keys())
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(c, "")) for c in columns) + " |")
    return "\n".join(lines) + "\n"


def _do_parse(batch_dir: Path, data_root: Path | None) -> None:
    out_root = _data_root(data_root) / batch_dir.name

    rows_by_type: dict[str, list[dict]] = {}
    images_by_type: dict[str, list[str]] = {}
    for image_path in sorted(batch_dir.iterdir()):
        if image_path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        result = extract_rows(image_path)
        list_type = result["list_type"]
        rows_by_type.setdefault(list_type, []).extend(
            project_row(truck, list_type) for truck in result["trucks"]
        )
        images_by_type.setdefault(list_type, []).append(image_path.name)

    extracted_at = datetime.now().isoformat(timespec="seconds")
    for list_type, rows in rows_by_type.items():
        deduped = dedupe_rows(rows)
        out_path = out_root / f"{list_type}.json"
        _write_json(
            out_path,
            {
                "list_type": list_type,
                "batch": batch_dir.name,
                "source_images": images_by_type[list_type],
                "extracted_at": extracted_at,
                "trucks": deduped,
            },
        )
        typer.echo(f"wrote {out_path} ({len(deduped)} trucks)")


def _read_trucks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())["trucks"]


def _do_merge(batch: str, data_root: Path | None) -> None:
    root = _data_root(data_root) / batch
    travelling = _read_trucks(root / "travelling.json")
    waiting = _read_trucks(root / "waiting.json")
    processing = _read_trucks(root / "processing.json")
    merged = merge_lists(travelling, waiting, processing)

    out_path = root / "trucks.json"
    _write_json(out_path, {"batch": batch, "trucks": merged})
    typer.echo(f"wrote {out_path} ({len(merged)} trucks)")


def _do_report(batch: str, report_name: str | None, data_root: Path | None) -> None:
    root = _data_root(data_root) / batch
    trucks = _read_trucks(root / "trucks.json")

    names = [report_name] if report_name else list(REPORTS)
    for name in names:
        if name not in REPORTS:
            raise typer.BadParameter(f"unknown report {name!r}; available: {list(REPORTS)}")
        rows = REPORTS[name](trucks)
        _write_json(root / "reports" / f"{name}.json", {"report": name, "batch": batch, "rows": rows})
        (root / "reports" / f"{name}.md").write_text(_to_markdown_table(rows))
        typer.echo(f"wrote {root / 'reports' / name}.{{json,md}} ({len(rows)} rows)")


@app.command()
def parse(
    batch_dir: Path = typer.Argument(..., help="Folder of screenshots for one capture session."),
    data_root: Path = typer.Option(None, "--data-root", help="Path to the data repo's data/ dir."),
) -> None:
    """Extract travelling.json / waiting.json / processing.json from a screenshot batch."""
    _do_parse(batch_dir, data_root)


@app.command()
def merge(
    batch: str = typer.Argument(..., help="Batch name, resolved under --data-root."),
    data_root: Path = typer.Option(None, "--data-root", help="Path to the data repo's data/ dir."),
) -> None:
    """Merge a batch's per-type lists into trucks.json."""
    _do_merge(batch, data_root)


@app.command()
def report(
    batch: str = typer.Argument(..., help="Batch name, resolved under --data-root."),
    report_name: str = typer.Option(None, "--report", help="Report to run (default: all registered)."),
    data_root: Path = typer.Option(None, "--data-root", help="Path to the data repo's data/ dir."),
) -> None:
    """Run reports over a batch's trucks.json, writing reports/*.{json,md}."""
    _do_report(batch, report_name, data_root)


@app.command()
def run(
    batch_dir: Path = typer.Argument(..., help="Folder of screenshots for one capture session."),
    data_root: Path = typer.Option(None, "--data-root", help="Path to the data repo's data/ dir."),
) -> None:
    """Chain parse + merge + report for a screenshot batch."""
    _do_parse(batch_dir, data_root)
    _do_merge(batch_dir.name, data_root)
    _do_report(batch_dir.name, None, data_root)


if __name__ == "__main__":
    app()
