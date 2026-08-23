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

## OCR approach

### v1: tesseract (tried, superseded)

The first implementation used classical OCR: `pytesseract` (tesseract-ocr)
against pixel crops of each row/column, with row and column boundaries
computed from calibrated pixel offsets and per-image header-word detection.

This got the pipeline running end-to-end (classify → locate rows/columns →
per-cell OCR → dedupe → merge → report all worked), but accuracy on the most
important field, `cargo`, was unacceptably poor, and getting there took
fixing a long chain of classical-CV failure modes, each narrower than the
last:

- **psm mode**: tesseract's "single line" mode (psm 7) reads these UI cells
  worse than "uniform block" mode (psm 6), despite each cell holding exactly
  one line.
- **Contrast**: light text on this game's dark, semi-transparent panel needed
  grayscale + upscaling + hard binarization to read reliably at all — and the
  right binarization threshold turned out to vary by context (header text in
  the sorted-column highlight color needed a different threshold than
  regular white cell text; a threshold tuned for one broke the other).
- **Icon bleed**: the `Typ` column's truck-icon graphic is visually wider
  than its "Typ" header text, so header-text-based column boundaries bled
  icon pixels into the `reg` column's crop.
- **Background bleed**: the panel's transparency lets faint map labels show
  through; a column boundary that ran to the image edge occasionally picked
  up a stray map label next to the real value.
- **Digit ambiguity**: some digit shapes in this font are genuinely
  confusable — "3" misread as "5", "1" misread as capital "I" — separate
  from any of the above, and not fixable by threshold tuning.
- **Header detection flakiness**: a single header word would occasionally
  drop below tesseract's confidence threshold on one screenshot and not
  another, breaking the column-count validation that the rest of the
  pipeline depended on.
- **The `cargo` breaking issue**: cargo values are short abbreviations
  (`Tro`, `Gra`, `Mas`, `Bau`, `Küh`, `Gef`) rendered on a colored pill
  badge. Even once every crop was pixel-clean, tesseract's German-language
  model (`deu`) would still misread some of these outright — e.g. a
  perfectly legible "Mas" badge consistently read as "NER". Testing showed
  this wasn't dictionary-correction (disabling tesseract's word lists didn't
  change it) — it's that `deu` and `eng` are separately-trained character
  recognition models, and `eng` simply generalizes better to this font,
  independent of the text being German words. Switching the OCR language
  fixed this one case, but by that point the pattern was clear: every fix
  uncovered a new, narrower failure mode, because pixel-threshold heuristics
  are fundamentally brittle against a UI with icons, colored badges, and
  uneven contrast.

Manually reading a full screenshot by eye (as a stand-in for what a vision
model call would produce) found every field trivially legible with zero
ambiguity — confirming the ceiling here isn't image quality, it's the
approach. Decision: replace classical OCR with a vision-capable LLM call.

### v2: Claude vision (current)

One Claude API call per screenshot: send the image plus a description of the
three panel types and their column layouts, constrain the response with
`output_config: {format: {type: "json_schema", ...}}` (Claude Messages API
"structured outputs"), and get back `{list_type, trucks: [...]}` directly —
classification and every field's extraction happen in that one call. This
removes row/column pixel calibration, per-field OCR tuning, and
language/threshold selection entirely; the model reads the panel the way a
person would.

- **Model**: `claude-opus-5`, called via the `anthropic` Python SDK (not the
  `claude` CLI — that's an interactive coding agent, not suited to scripted
  structured-extraction calls; the API's native image content blocks and
  `output_config` json_schema are purpose-built for this).
- **Auth**: needs an `ANTHROPIC_API_KEY` (separate from any Claude Code
  auth) set in the environment running `trucklist parse`/`run`.
- **Cost/latency**: one call per screenshot, so a handful of calls per batch
  — negligible either way for this project's volume.
- **Schema**: the JSON schema requested from the model is the same
  kitchen-sink shape as `trucks.json` (see Combined list, below) — every
  field from every list type, nullable, plus `list_type`. A given screenshot
  only ever shows one panel type, so only that type's fields come back
  populated; this sidesteps needing three separate request schemas.
- **Icon-only columns** (see below) are simply omitted from the schema/
  prompt — nothing to ask the model to read.

## Pipeline

1. **Extract**: for each image in the batch, one Claude vision call returns
   `{list_type, trucks: [...]}` — every row's fields as raw strings (no
   numeric/unit parsing in v1, see Open Questions), each tagged with
   `source_image`.
2. **Dedupe within the batch**: group all extracted rows by list type across
   every image in the folder, drop duplicate `reg` values — **latest image
   wins** (compare by the timestamp embedded in the screenshot filename,
   `Screenshot_YYYYMMDD_HHMMSS.jpg`; a truck's state can change between
   overlapping screenshots, so the most recent capture is the source of
   truth).
3. **Write** one JSON file per list type present in the batch.

Every extracted row carries a `source_image` field (the filename it came
from) alongside its data columns — needed both for the dedup rule above and
for the cross-list merge in the next step.

Icon-only columns (`Typ` route-type bar, `Status` wrench/lightning/clock on
the processing list) are **skipped** — not extracted at all. The waiting
list also has a trailing `Zeit` header column, observed always empty (`-`)
in sample data with no clear meaning yet; treated the same as an icon-only
column and skipped. The travelling list's `Fortschritt` column is icon-only
too (a vehicle icon, no percentage text) in all sample data — also skipped;
`completed_pct` (`Abgeschlossen`) is the real progress percentage for that
list.

## Field schemas (v1 — raw strings, `reg` is the dedup key)

Every row also carries `source_image` (see dedup rule above).

**travelling** (Unterwegs)
`reg, route, origin, destination, cargo, cargo_onboard, completed_pct, eta, source_image`

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

  `reg, status, route, origin, destination, location, cargo, cargo_onboard, max_load, demand_today, completed_pct, eta, tuv, wear_pct, ready_in, source_image`

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
    vision_extract.py       # Claude vision call: classify + extract per image
    dedupe.py                # within-batch reg dedup, latest-wins merge
    schema.py                 # field lists per list type, JSON schema for the API call
    reports/
      registry.py              # {name: report_fn} map
      by_cargo.py                # v1 report
docs/specs/
  trucklist-parser.md         # this file
```

System dependency: none (no tesseract-ocr). Needs an `ANTHROPIC_API_KEY`
environment variable at runtime.
Python deps: `typer`, `anthropic`.

## CI / automation

Same two-repo shape as before, but simpler — no OS-level dependency (no
`tesseract-ocr`), so `truck_manager_tools` no longer needs its own Docker
image; the data repo's workflow can just check out `truck_manager_tools` and
`uv sync` + run directly on the runner.

1. **`truck_manager_data`** has a `workflow_dispatch` workflow (manual
   trigger) that takes the batch folder name as input, checks out
   `truck_manager_tools` as a second repo (`actions/checkout`), `uv sync`s
   it, runs `trucklist run <batch_dir>` with `ANTHROPIC_API_KEY` from a
   repository secret, then commits the resulting `*.json`/`reports/*` files
   back to `main` (`git commit` + `git push`, using `GITHUB_TOKEN`).
2. No image to build or publish, so no workflow needed in
   `truck_manager_tools` itself for this — a plain checkout of its `main`
   branch each run is enough, at the cost of not having a pinned/versioned
   release of the tool (acceptable for now; revisit if that becomes a
   problem).

## Open questions / v1 limitations (deliberately deferred)

- **No numeric/unit parsing** — e.g. `"26,265 kg"`, `"87.7 m3"`, `"61:00:18"`
  elapsed time, `"204,873 /257,403 kg"` demand fractions are stored as raw
  strings, not split into typed value+unit fields. Fast-follow once the raw
  extraction is proven reliable.
- **Icon columns skipped** — `route_type` (Linie/Langstrecke bar color) and
  `status` (repair/charging/pending-cargo icon) are not captured in v1.
- **Cross-batch dedup** is out of scope — re-running on overlapping sessions
  captured in different folders will produce separate, potentially
  overlapping truck entries. Revisit if the user wants an accumulating master
  truck history later.
- **No automated test suite yet** — validated so far by running against real
  sample batches and checking output by hand, not by a pytest suite.
- **Vision extraction accuracy not yet validated at scale** — the tesseract
  approach was disproven on real samples (see above); the vision approach's
  own accuracy still needs the same kind of validation once implemented,
  across more batches and both edge cases (partial rows, unusual cargo
  types, screenshots at a different resolution than the fixed 2560x1600
  samples seen so far — vision extraction doesn't need pixel calibration,
  so should be far more resolution-tolerant than v1, but that's an
  expectation to confirm, not a guarantee).
- **Response reliability**: `output_config` json_schema constrains the
  *shape* of the response, not its accuracy — still need to decide how to
  handle a call that errors, times out, or (rare but possible) returns a
  row count that doesn't match what's visible, e.g. a retry policy.
