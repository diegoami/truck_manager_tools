# Truck Manager Tools

Modular Python CLI tools that support playing the game Truck Manager.

Sibling repo `../truck_manager_data` holds captured game screenshots and all
generated data/reports. This repo holds only tooling code — no game data or
generated output belongs here.

## Working rules

- **Spec first.** Before implementing a new tool or a significant feature,
  write or update a design doc under `docs/specs/*.md` and go through it with
  the user before writing code. Don't jump straight to implementation.
- **Commit and push after each iteration.** Don't stockpile uncommitted work
  across turns — commit (and push) once a step is done, rather than waiting
  for a large batch of changes.

## CLI conventions

- Each modular tool gets its **own** top-level command / console-script entry
  point (e.g. `trucklist`) — not nested under a shared umbrella CLI.
- `uv` + `typer`. `uv tool install --editable .` for local dev puts commands
  on `PATH` directly (no `uv run` prefix needed); `uv run <command> ...` also
  works from a repo checkout without installing.

## Tools

- **`trucklist`** (spec only, not yet implemented) — parses batches of Truck
  Manager screenshots (the Unterwegs/Ausstehend/Im Leerlauf list panels) into
  structured JSON, merges them into one combined truck list, and generates
  reports. Spec: [docs/specs/trucklist-parser.md](docs/specs/trucklist-parser.md).

## Related repo: truck_manager_data

- `images/trucklists/<batch>/` — input screenshots for one capture session.
  Batch folder naming convention: `YYYY-MM-DD-N` (N increments per session on
  days with more than one capture) — not enforced by tooling, just a
  convention.
- `data/trucklists/<batch>/` — this repo's tools write their output here:
  `travelling.json`, `waiting.json`, `processing.json`, `trucks.json`,
  `reports/*.{json,md}`.
