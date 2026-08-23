"""Field lists per list type, per docs/specs/trucklist-parser.md."""

TRAVELLING_FIELDS = [
    "reg",
    "route",
    "origin",
    "destination",
    "cargo",
    "cargo_onboard",
    "completed_pct",
    "eta",
    "source_image",
]

WAITING_FIELDS = [
    "reg",
    "tuv",
    "wear_pct",
    "route",
    "origin",
    "destination",
    "cargo",
    "max_load",
    "demand_today",
    "source_image",
]

PROCESSING_FIELDS = [
    "reg",
    "route",
    "location",
    "destination",
    "cargo",
    "max_load",
    "demand_today",
    "ready_in",
    "source_image",
]

# Union of all per-type fields, plus `status`. Fields that don't apply to a
# given truck's current status are null.
TRUCKS_FIELDS = [
    "reg",
    "status",
    "route",
    "origin",
    "destination",
    "location",
    "cargo",
    "cargo_onboard",
    "max_load",
    "demand_today",
    "completed_pct",
    "eta",
    "tuv",
    "wear_pct",
    "ready_in",
    "source_image",
]

LIST_TYPES = {
    "travelling": TRAVELLING_FIELDS,
    "waiting": WAITING_FIELDS,
    "processing": PROCESSING_FIELDS,
}

# In-game panel title text -> our list type name.
PANEL_TITLES = {
    "Unterwegs": "travelling",
    "Im Leerlauf": "waiting",
    "Ausstehend": "processing",
}
