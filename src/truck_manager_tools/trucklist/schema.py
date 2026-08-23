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

# Fields a vision extraction call fills in per row — every field across all
# three list types except `reg` (always present) and `status`/`source_image`
# (added by our code, not read from the image). Every list type populates
# only its own subset; the rest come back null.
_VISION_OPTIONAL_FIELDS = [f for f in TRUCKS_FIELDS if f not in ("reg", "status", "source_image")]


def vision_response_schema() -> dict:
    """JSON schema for the Claude vision extraction call's structured output."""
    row_properties = {"reg": {"type": "string"}}
    for field in _VISION_OPTIONAL_FIELDS:
        row_properties[field] = {"type": ["string", "null"]}
    return {
        "type": "object",
        "properties": {
            "list_type": {"type": "string", "enum": list(LIST_TYPES)},
            "trucks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": row_properties,
                    "required": ["reg", *_VISION_OPTIONAL_FIELDS],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["list_type", "trucks"],
        "additionalProperties": False,
    }


def project_row(row: dict, list_type: str) -> dict:
    """Keep only the fields that list type's per-type schema defines."""
    return {field: row.get(field) for field in LIST_TYPES[list_type]}
