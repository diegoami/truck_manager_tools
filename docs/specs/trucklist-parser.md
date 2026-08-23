# trucklist-parser

Parses batches of Truck Manager screenshots (the in-game truck list panels) into
structured, deduplicated JSON.

## Problem

Each capture session, the user scrolls through and screenshots the game's truck
list panels. A panel is often taller than one screen, so consecutive screenshots
overlap — the same truck row can appear in two images. There are three distinct
panels (German UI), each with its own column layout:

| Our name     | In-game panel | Meaning                                              |
|--------------|---------------|-------------------------------------------------------|
| `travelling` | Unterwegs     | Trucks currently en route                             |
| `waiting`    | Im Leerlauf   | Idle trucks, no route assigned                        |
| `processing` | Ausstehend    | Trucks with something happening (repair/charging/pending cargo) |

## Input

A **batch** = one folder of screenshots from one capture session, e.g.:

```
truck_manager_data/images/trucklists/2026-08-22-1/
  Screenshot_20260822_220941.jpg
  Screenshot_20260822_220958.jpg
  ...
```

Folder naming is not enforced by the tool — the user creates it. Recommended
convention: `YYYY-MM-DD-N` (N increments per session on days with more than
one capture), since dedup is scoped to a single batch (see below) and two
sessions must not land in the same folder.

A batch may contain screenshots of all three panel types mixed together, in
any order, any quantity.

## Output

One JSON file per list type that appeared in the batch, written to a mirrored
path under the data repo:

```
truck_manager_data/data/trucklists/2026-08-22-1/
  travelling.json
  waiting.json
  processing.json
```

Each file is a JSON array of row objects (schemas below) plus a top-level
metadata object:

```json
{
  "list_type": "travelling",
  "batch": "2026-08-22-1",
  "source_images": ["Screenshot_20260822_220941.jpg", "..."],
  "extracted_at": "2026-08-22T22:30:00",
  "trucks": [ { "reg": "B3T6067", "...": "..." }, ... ]
}
```

## Pipeline

1. **Classify** each image by list type: OCR the panel title text (top-left,
   below the HUD bar) and match against `{Unterwegs, Ausstehend, Im Leerlauf}`.
2. **Locate table rows**: find the header row, then step down in row-height
   increments (calibrated against known sample screenshots) until the bottom
   of the panel/table area. This is the trickiest part to get robust — see
   Open Questions.
3. **Slice columns**: OCR the header row to get each column label's x-range,
   use those (with padding) to crop each data row into per-column cells.
4. **OCR each cell** (tesseract via pytesseract), per-column tuned (e.g.
   numeric whitelist for weight/percentage columns, single-line PSM).
5. **Store raw text per field** — no numeric/unit parsing in v1 (see Open
   Questions). Just cleaned-up strings (trimmed whitespace).
6. **Dedupe within the batch**: group all extracted rows by list type across
   every image in the folder, drop duplicate `reg` values — **latest image
   wins** (compare by the timestamp embedded in the screenshot filename,
   `Screenshot_YYYYMMDD_HHMMSS.jpg`; a truck's state can change between
   overlapping screenshots, so the most recent capture is the source of
   truth).
7. **Write** one JSON file per list type present in the batch.

Every extracted row carries a `source_image` field (the filename it came
from) alongside its data columns — needed both for the dedup rule above and
for the cross-list merge in the next step.

Icon-only columns (`Typ` route-type bar, `Status` wrench/lightning/clock on
the processing list) are **skipped in v1** — not extracted at all. The
waiting list also has a trailing `Zeit` header column, observed always empty
(`-`) in sample data with no clear meaning yet; treated the same as an
icon-only column and skipped.

## Field schemas (v1 — raw strings, `reg` is the dedup key)

Every row also carries `source_image` (see dedup rule above).

**travelling** (Unterwegs)
`reg, route, origin, destination, cargo, cargo_onboard, progress_pct, completed_pct, eta, source_image`

**waiting** (Im Leerlauf)
`reg, tuv, wear_pct, route, origin, destination, cargo, max_load, demand_today, source_image`

**processing** (Ausstehend)
`reg, route, location, destination, cargo, max_load, demand_today, ready_in, source_image`

## Combined list (all trucks)

A second processing step merges the three per-type lists into one
`trucks.json` — one row per truck, covering the whole fleet regardless of
current state.

- **Schema** = union of all fields from the three per-type schemas, plus a
  `status` field (`travelling` / `waiting` / `processing`). Fields that don't
  apply to a given truck's status are `null`:

  `reg, status, route, origin, destination, location, cargo, cargo_onboard, max_load, demand_today, progress_pct, completed_pct, eta, tuv, wear_pct, ready_in, source_image`

- **Cross-list conflict resolution**: the same `reg` can legitimately appear
  in two different type-lists within one batch (a truck finishes travelling
  and becomes idle partway through a capture session). Same rule as within-
  list dedup: **latest `source_image` wins**, whole row — don't merge fields
  from both entries, just take the more recent screenshot's row (and its
  `status`) wholesale.

Output: `truck_manager_data/data/trucklists/<batch>/trucks.json`.

## Reports

A pluggable reporting step runs over `trucks.json` (or a specific per-type
list) and produces named reports. Each report is a small function that takes
the truck list and returns aggregate rows — e.g. count-by-cargo groups by the
`cargo` field and counts trucks per value.

- **Output**: both JSON (source of truth) and Markdown (rendered from the
  JSON) per report, e.g.:
  ```
  data/trucklists/<batch>/reports/by_cargo.json
  data/trucklists/<batch>/reports/by_cargo.md
  ```
- **v1 report**: `by_cargo` — truck count grouped by `cargo`.
- **Future reports** (not designed yet, architecture just needs to allow
  adding them): grouping/filtering by other fields, and reports derived from
  the `reg` value itself — e.g. inferring country of registration from the
  plate format. This depends on whether the game's `reg` values actually
  encode anything meaningful (the samples seen so far — `B3T6067`,
  `DXDXG7` — don't obviously match a real-world plate scheme); treat as a
  research spike before committing to it as a report.
- **Implementation shape**: a `reports/` module with one function per report
  registered in a small dict/registry (`{"by_cargo": by_cargo_report, ...}`),
  and a CLI command `tmt trucklist report <batch_dir> [--report NAME]`
  (default: run all registered reports) — so adding a report later means
  writing one function, not touching the pipeline.

## CLI

Project uses `uv` + `typer`. Each modular tool in this repo gets its **own**
top-level command (no shared umbrella command) — this one is `trucklist`,
registered as its own console-script entry point. After a one-time
`uv tool install --editable .` (installs from the repo, keeps it live-editable),
`trucklist` is on `PATH` directly — no `uv run` prefix needed. During
development from a repo checkout, `uv run trucklist ...` still works without
installing.

```
trucklist parse <batch_dir> [--data-root <path>]
trucklist merge <batch> [--data-root <path>]
trucklist report <batch> [--report NAME] [--data-root <path>]
trucklist run <batch_dir> [--data-root <path>]   # chains parse+merge+report
```

- `parse`: runs the per-type extraction pipeline, writes
  `travelling.json` / `waiting.json` / `processing.json`.
- `merge`: reads those three files for a batch, writes `trucks.json`.
- `report`: reads `trucks.json`, writes `reports/*.{json,md}`.
- `run`: convenience command chaining all three (this is what the CI workflow
  calls).
- `batch_dir` (parse, run): path to the folder of screenshots (e.g.
  `truck_manager_data/images/trucklists/2026-08-22-1`)
- `batch` (merge/report): batch name, resolved under `--data-root` (they
  operate on already-extracted JSON, not screenshots)
- `--data-root`: path to the data repo's `data/` dir (default: sibling
  `../truck_manager_data/data`, overridable via `TMT_DATA_ROOT` env var)

Output subfolder name = `batch_dir`'s basename.

## Repo layout (truck_manager_tools)

```
pyproject.toml              # [project.scripts] trucklist = "truck_manager_tools.trucklist.cli:app"
src/truck_manager_tools/
  trucklist/
    cli.py                  # typer app: parse/merge/report/run
    classify.py            # panel-type detection
    layout.py               # row/column calibration
    extract.py              # OCR + cell parsing
    dedupe.py                # within-batch reg dedup, latest-wins merge
    schema.py                 # field lists per list type
    reports/
      registry.py              # {name: report_fn} map
      by_cargo.py                # v1 report
docs/specs/
  trucklist-parser.md         # this file
```

System dependency: `tesseract-ocr` (not installed yet — `apt install tesseract-ocr`).
Python deps: `typer`, `pillow`, `pytesseract`.

## CI / automation

Yes — GitHub Actions can run steps directly inside a Docker container on the
standard hosted runners; no separate VM or external Docker host is needed.
`tesseract-ocr` + a Python OCR pipeline is lightweight (seconds per image),
well within free-tier Actions minutes.

The wrinkle is that tools and data live in **two separate repos**. Recommended
shape:

1. **`truck_manager_tools`** has a `Dockerfile` (tesseract + Python deps +
   `trucklist` installed) and a workflow that builds and publishes it to GHCR
   (`ghcr.io/diegoami/truck_manager_tools`) on push to `main` (or on tag, if
   we want versioned releases instead of a rolling `latest`).
2. **`truck_manager_data`** has a `workflow_dispatch` workflow (manual
   trigger, per your answer above) that takes the batch folder name as an
   input, runs `docker run ghcr.io/diegoami/truck_manager_tools ...` with the
   repo checkout mounted as a volume, then commits the resulting
   `*.json`/`reports/*` files back to `main` (`git commit` + `git push` as
   the final step, using `GITHUB_TOKEN`).

This keeps the two repos' responsibilities clean — `truck_manager_tools`
owns and versions the processing logic and its image, `truck_manager_data`
just consumes it — at the cost of one extra publish step when the tool
changes. Alternative (simpler, more coupled): skip the published image and
have the data repo's workflow check out `truck_manager_tools` as a second
repo via `actions/checkout` and `uv sync` + run directly on the runner
(no Docker layer at all). Worth deciding once the CLI itself exists and we
know how heavy the dependencies are — flagging both options here rather than
locking it in now.

## Open questions / v1 limitations (deliberately deferred)

- **Row/column calibration** is resolution-dependent; v1 assumes the fixed
  2560x1600 game resolution seen in the sample batch (`trucklists/1`). If the
  user captures at a different resolution/window size, calibration breaks.
- **No numeric/unit parsing** — e.g. `"26,265 kg"`, `"87.7 m3"`, `"61:00:18"`
  elapsed time, `"204,873 /257,403 kg"` demand fractions are stored as raw
  OCR'd strings, not split into typed value+unit fields. Fast-follow once the
  raw extraction is proven reliable.
- **Icon columns skipped** — `route_type` (Linie/Langstrecke bar color) and
  `status` (repair/charging/pending-cargo icon) are not captured in v1.
- **Cross-batch dedup** is out of scope — re-running on overlapping sessions
  captured in different folders will produce separate, potentially
  overlapping truck entries. Revisit if the user wants an accumulating master
  truck history later.
