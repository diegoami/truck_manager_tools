# truck-manager-tools

Modular Python CLI tools that support playing the game Truck Manager. Each
tool has its own top-level command; see `docs/specs/*.md` for the design
doc behind each one.

## trucklist

Parses batches of Truck Manager screenshots (the Unterwegs/Ausstehend/Im
Leerlauf list panels) into structured JSON, merges them into one combined
truck list, and generates reports.

### Prerequisites

- [`uv`](https://docs.astral.sh/uv/) — Python package/tool manager.
- The `claude` CLI, installed and logged in (`claude login`). Extraction
  reads each screenshot via a headless Claude vision call, billed against
  your Claude Pro/Max subscription — **do not** set `ANTHROPIC_API_KEY` in
  the environment you run `trucklist` from, or extraction switches to the
  separate pay-per-token API instead.
- A sibling checkout of `truck_manager_data` (holds the input screenshots
  and all generated output — see that repo's own docs for the batch folder
  convention).

### Install

```
uv tool install --editable .
```

Puts `trucklist` on `PATH`, editable (changes to this repo take effect
immediately, no reinstall). From a checkout without installing, prefix
every command with `uv run` instead (`uv run trucklist ...`).

### Usage

Capture a batch of screenshots into
`truck_manager_data/images/trucklists/<batch>/`, then:

```
trucklist run truck_manager_data/images/trucklists/<batch>
```

This chains three steps — extract each screenshot (Claude vision) → merge
into `trucks.json` → generate reports — writing everything to
`truck_manager_data/data/trucklists/<batch>/`.

Extraction takes roughly 35-40 seconds *per screenshot* (each is a fresh
headless `claude` call), so a typical batch (5-10 images) takes a few
minutes end to end.

Each step is also its own command, if you want to re-run just one (e.g.
`report`, after tweaking a report function, without re-extracting):

```
trucklist parse <batch_dir>       # screenshots -> travelling.json / waiting.json / processing.json
trucklist merge <batch_name>      # combine into trucks.json
trucklist report <batch_name>     # generate reports/*.{json,md}
```

`parse`/`run` take a *path* to the screenshot folder; `merge`/`report` take
just the *batch name* (they read already-extracted JSON, not screenshots).
All four accept `--data-root` to point at a `truck_manager_data/data`
directory other than the default sibling checkout (or set `TMT_DATA_ROOT`).

#### Faster: the `/trucklist-extract` skill

If you're already in an interactive Claude Code session in this repo,
`/trucklist-extract` does the same extraction *inline* in that session
instead of shelling out per screenshot — each subprocess `claude -p` call
pays a ~35-40s "boot a fresh agent" cost that a continuous session doesn't,
so this is noticeably faster for multi-image batches. It scans
`truck_manager_data` for batches that don't have report output yet and
processes those automatically; pass a batch name as an argument to force
reprocessing one that's already done. See
[`.claude/skills/trucklist-extract/SKILL.md`](.claude/skills/trucklist-extract/SKILL.md).

### Output shape

```
truck_manager_data/data/trucklists/<batch>/
  travelling.json     # Unterwegs rows
  waiting.json        # Im Leerlauf rows
  processing.json      # Ausstehend rows
  trucks.json          # all three merged, one row per truck, status field added
  reports/
    by_cargo.json
    by_cargo.md
```

Every field is a raw string as displayed in-game (no unit parsing) — see
the spec for the exact field list per panel type.

### Design docs

[`docs/specs/trucklist-parser.md`](docs/specs/trucklist-parser.md) has the
full design — including the history of *why* extraction works this way.
Worth reading before changing the extraction pipeline: it documents a full
attempt at classical OCR (tesseract) that was abandoned for accuracy
reasons, and a direct-API vision approach that was abandoned for cost
reasons, before landing on the current headless-CLI approach.
