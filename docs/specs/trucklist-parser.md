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

### v2: Claude vision via the Anthropic API (tried, superseded by cost)

One Claude API call per screenshot: send the image plus a description of the
three panel types and their column layouts, constrain the response with
`output_config: {format: {type: "json_schema", ...}}` (Claude Messages API
"structured outputs"), and get back `{list_type, trucks: [...]}` directly —
classification and every field's extraction happen in that one call. This
removes row/column pixel calibration, per-field OCR tuning, and
language/threshold selection entirely; the model reads the panel the way a
person would, and accuracy was verified 28/28 correct against a manual
transcription of a full screenshot, including every case that broke
tesseract (cargo values, umlauts).

The catch: this uses `claude-opus-5` via the `anthropic` Python SDK, billed
against the Anthropic Console's separate pay-per-token API credits — not
covered by a Claude Pro/Max subscription. Running it against both sample
batches (~12 screenshots) cost about €1.60. Fine for a one-off test, not
something to run "all the time" for a hobby tool with a subscription
already paid for. Superseded by v3.

### v3: Claude Code CLI, headless (current)

Same call shape (image in, `{list_type, trucks: [...]}` out, one call per
screenshot) but via the `claude` CLI's headless mode instead of the API
directly:

```
claude -p "<prompt>" --output-format json --json-schema '<schema>' --allowedTools Read
```

The prompt tells Claude to read the image at a given absolute path with its
Read tool (there's no dedicated CLI flag for attaching an image, unlike the
API); `--json-schema` gets the same structured-output guarantee as
`output_config` on the API, surfaced as the response's `structured_output`
field; `--allowedTools Read` restricts the session to read-only.

- **Auth / cost**: as long as `ANTHROPIC_API_KEY` is **not** set, `claude
  -p` authenticates via the logged-in session (`claude login`) and draws on
  Claude Pro/Max subscription quota — not the pay-per-token API. The
  response reports a `total_cost_usd` figure, but that's an informational
  equivalent-API-cost estimate, not an actual charge, under subscription
  auth. Verified: re-ran the same extraction that cost €1.60 via the API,
  with identical 28/28 accuracy, no separate billing.
- **Latency**: noticeably slower than the direct API — around 35-40s per
  screenshot, versus a few seconds for the API call. Headless mode loads
  Claude Code's full agent context (system prompt, tool definitions, etc.)
  on every invocation; there's no lean "just answer this one thing" mode
  available while still authenticating via the subscription (`--bare` mode
  strips that overhead but forces `ANTHROPIC_API_KEY` auth, defeating the
  purpose). Acceptable for this tool's occasional-batch use case (a few
  minutes per batch), revisit if that changes.
- **System dependency**: the `claude` CLI installed and logged in
  (`claude login`) on whatever machine runs `trucklist parse`/`run` —
  replaces the `anthropic` Python package and `ANTHROPIC_API_KEY`
  entirely (no Python SDK dependency for this at all now).
- **Schema**: same kitchen-sink shape as v2 — see Combined list, below.
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
    vision_extract.py       # classify + extract per image, via `claude -p` headless
    dedupe.py                # within-batch reg dedup, latest-wins merge
    schema.py                 # field lists per list type, JSON schema for the vision call
    reports/
      registry.py              # {name: report_fn} map
      by_cargo.py                # v1 report
docs/specs/
  trucklist-parser.md         # this file
```

System dependency: the `claude` CLI, installed and logged in (`claude
login`) — no OS packages (no tesseract-ocr), no Python SDK (no `anthropic`
package), no API key. `ANTHROPIC_API_KEY` must specifically **not** be set,
or extraction bills the pay-per-token API instead of using the subscription.
Python deps: `typer` only.

## CI / automation

Unattended CI (the `workflow_dispatch` shape sketched in earlier drafts of
this spec) doesn't fit v3 as cleanly as it fit the API-based v2: a GitHub
Actions runner isn't logged into the user's Claude Code session, so
`trucklist run` there would need either `ANTHROPIC_API_KEY` (a repository
secret, back to pay-per-token billing — defeats the reason for choosing v3)
or a `CLAUDE_CODE_OAUTH_TOKEN` (a long-lived token generated via `claude
setup-token` that still draws on subscription quota, but is a credential to
generate, store as a secret, and rotate before it expires).

Given the tool is used occasionally and by hand today, this is left as a
deliberately open question rather than designed now — revisit if/when
there's an actual need to run this unattended. Until then, `trucklist run`
is invoked locally, on a machine with an authenticated `claude` session.

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
- **Vision extraction accuracy validated on two batches, not at scale** —
  28/28 rows correct against a manual transcription (both the API and CLI
  variants, identical output), and a clean 6-category `by_cargo` report
  where tesseract produced 26 noisy near-duplicates. Not yet tested across
  more batches, edge cases (partial rows, unusual cargo types), or
  screenshots at a resolution other than the fixed 2560x1600 samples seen so
  far — vision extraction doesn't need pixel calibration, so should be far
  more resolution-tolerant than v1, but that's an expectation to confirm,
  not a guarantee.
- **Response reliability**: `--json-schema` constrains the response's
  *shape*, not its accuracy — still need to decide how to handle a call
  that errors, times out, or (rare but possible) returns a row count that
  doesn't match what's visible, e.g. a retry policy. `vision_extract.py`
  currently raises on a non-zero exit or an `is_error` response and doesn't
  retry.
- **Headless-mode vision via a file-path prompt is a workaround**, not a
  documented, first-class CLI feature (there's no dedicated "attach an
  image" flag) — it works because Claude's Read tool loads the file when
  told to, but a future CLI version could change how that behaves.
- **Per-call latency** (~35-40s) means a full batch takes several minutes;
  fine for occasional manual runs, would need reworking (parallel calls, or
  back to `--bare` + API billing) if usage grows.
