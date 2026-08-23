---
name: trucklist-extract
description: Find truck_manager_data trucklist batches that haven't been processed yet (no reports/ output), extract each screenshot's rows by reading the images directly with vision, then run the deterministic trucklist CLI to merge and generate reports. Use when the user asks to process new trucklist screenshots, update trucklist data, or run trucklist reports.
---

## Why this skill exists

`trucklist parse` (the CLI command) already does this by shelling out to
`claude -p` once per screenshot — but each subprocess call pays a ~35-40s
"boot a fresh headless agent" cost, so a batch of 5-10 images takes several
minutes. Running the same extraction *yourself*, inline in this session,
skips that repeated boot cost — you're already running, so reading a second
or third image costs almost nothing extra. This skill is that faster path.

Only the extraction step (image → row data) is your job here. Dedup within
a batch, merging the three per-type lists, and reports are all deterministic
Python (`dedupe.py`, `cli.py` merge/report) — call the CLI for those, don't
reimplement them.

## Step 1: Find the data root

Default: `../truck_manager_data` relative to this repo (sibling checkout).
If `TMT_DATA_ROOT` is set in the environment, use that instead. Confirm it
exists before continuing.

## Step 2: Find batches needing processing

List the batch folders under `<data_root>/images/trucklists/` (each
subdirectory is one batch). For each batch, it needs processing if
`<data_root>/data/trucklists/<batch>/reports/by_cargo.json` does **not**
exist yet — that file is the last thing the pipeline writes, so its absence
means the batch was never fully processed.

If the user invoked this skill with an argument (`$ARGUMENTS`), treat that
as a specific batch name and process **only** that batch, even if its
reports already exist (force reprocess — e.g. after adding screenshots to
an existing batch folder, or after an extraction quality fix). If the named
batch folder doesn't exist under `images/trucklists/`, tell the user and
stop.

If no batches need processing, say so and stop — nothing to do.

## Step 3: Read the extraction contract

Before extracting anything, read these two files in this repo so your
extraction matches the CLI's exactly:

- `src/truck_manager_tools/trucklist/vision_extract.py` — its
  `PROMPT_TEMPLATE` constant has the authoritative panel-type identification
  rules and column-to-field mapping (German column names, which columns are
  icon-only and must be skipped, e.g. `Typ`, `Status`, `Fortschritt`,
  trailing `Zeit`).
- `src/truck_manager_tools/trucklist/schema.py` — `TRAVELLING_FIELDS`,
  `WAITING_FIELDS`, `PROCESSING_FIELDS` are the exact field lists (and
  field order doesn't matter, but every field must be present) for each
  per-type output file.

Don't hardcode the mapping from memory — read these two files fresh each
time you run this skill, since they're the single source of truth and may
have changed since this skill was written.

## Step 4: Extract each batch

For each batch to process:

1. List the screenshot files in `<data_root>/images/trucklists/<batch>/`
   (`.jpg`/`.jpeg`/`.png` only — ignore stray files like `placeholder.txt`),
   sorted by filename (sorts by capture timestamp).
2. For each image, read it and: identify which panel it shows (the German
   title top-left, below the HUD bar), then extract every visible truck
   row's fields exactly as displayed — raw text, no unit conversion, no
   rounding. Read `reg` especially carefully; it's the unique key everything
   else dedupes on. Tag each extracted row with `source_image` (the
   filename).
3. Collect all rows across all of this batch's images, grouped by the
   list_type each image turned out to be.

## Step 5: Dedupe within the batch

Within each list_type's collected rows, if the same `reg` appears from more
than one image, keep only the row from the image with the **latest**
timestamp — compare the `Screenshot_YYYYMMDD_HHMMSS.jpg` filenames as
strings; the lexicographically later one wins (a truck's state can change
between overlapping screenshots, so the most recent capture is the source
of truth). This mirrors `dedupe.py`'s `dedupe_rows` — same rule, applied by
hand since you're the one holding the extracted rows.

## Step 6: Write the per-type output files

For each list_type present in this batch, write
`<data_root>/data/trucklists/<batch>/<list_type>.json`:

```json
{
  "list_type": "<travelling|waiting|processing>",
  "batch": "<batch name>",
  "source_images": ["<every image filename that contributed to this list_type, sorted>"],
  "extracted_at": "<current local ISO timestamp, e.g. 2026-08-23T14:30:00>",
  "trucks": [ /* deduped rows from step 5, each with every field from that
                list_type's field list in schema.py, plus source_image */ ]
}
```

## Step 7: Merge and report

Run these from this repo's root (they're pure Python, no LLM call — do not
run `trucklist parse` or `trucklist run`, which would redo the extraction
you just did by hand):

```
uv run trucklist merge <batch>
uv run trucklist report <batch>
```

Run both for every batch you processed in step 4-6.

## Step 8: Summarize

Tell the user which batches were processed, how many trucks ended up in
each per-type file and in the combined `trucks.json`, and show the
`by_cargo` report's counts.
