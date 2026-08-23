"""trucklist: parse Truck Manager screenshot batches into structured JSON.

See docs/specs/trucklist-parser.md for the full pipeline design.
"""

import os
from pathlib import Path

import typer

app = typer.Typer(help="Parse Truck Manager screenshot batches into structured JSON.")

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[4] / "truck_manager_data" / "data"


def _data_root(data_root: Path | None) -> Path:
    if data_root is not None:
        return data_root
    env = os.environ.get("TMT_DATA_ROOT")
    return Path(env) if env else DEFAULT_DATA_ROOT


@app.command()
def parse(
    batch_dir: Path = typer.Argument(..., help="Folder of screenshots for one capture session."),
    data_root: Path = typer.Option(None, "--data-root", help="Path to the data repo's data/ dir."),
) -> None:
    """Extract travelling.json / waiting.json / processing.json from a screenshot batch."""
    raise NotImplementedError


@app.command()
def merge(
    batch: str = typer.Argument(..., help="Batch name, resolved under --data-root."),
    data_root: Path = typer.Option(None, "--data-root", help="Path to the data repo's data/ dir."),
) -> None:
    """Merge a batch's per-type lists into trucks.json."""
    raise NotImplementedError


@app.command()
def report(
    batch: str = typer.Argument(..., help="Batch name, resolved under --data-root."),
    report_name: str = typer.Option(None, "--report", help="Report to run (default: all registered)."),
    data_root: Path = typer.Option(None, "--data-root", help="Path to the data repo's data/ dir."),
) -> None:
    """Run reports over a batch's trucks.json, writing reports/*.{json,md}."""
    raise NotImplementedError


@app.command()
def run(
    batch_dir: Path = typer.Argument(..., help="Folder of screenshots for one capture session."),
    data_root: Path = typer.Option(None, "--data-root", help="Path to the data repo's data/ dir."),
) -> None:
    """Chain parse + merge + report for a screenshot batch."""
    raise NotImplementedError


if __name__ == "__main__":
    app()
