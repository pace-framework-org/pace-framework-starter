"""YAML schema definitions for PACE artifacts."""

STORY_CARD_SCHEMA = {
    "type": "object",
    "required": ["day", "agent", "story", "given", "when", "then", "acceptance", "out_of_scope"],
    "properties": {
        "day": {"type": "integer"},
        "agent": {"type": "string", "const": "PRIME"},
        "story": {"type": "string"},
        "given": {"type": "string"},
        "when": {"type": "string"},
        "then": {"type": "string"},
        "acceptance": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "out_of_scope": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": True,
}

HANDOFF_SCHEMA = {
    "type": "object",
    "required": ["day", "agent", "commit", "approach", "risk", "dependencies", "built", "edge_cases_tested", "known_gaps"],
    "properties": {
        "day": {"type": "integer"},
        "agent": {"type": "string", "const": "FORGE"},
        "commit": {"type": "string"},
        "approach": {"type": "string"},
        "risk": {"type": "string"},
        "dependencies": {"type": "string"},
        "built": {"type": "string"},
        "edge_cases_tested": {"type": "array", "items": {"type": "string"}},
        "known_gaps": {"type": "array", "items": {"type": "string"}},
        "iterations_used": {"type": "integer"},
    },
    "additionalProperties": True,
}

_FINDINGS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["check", "result", "evidence"],
        "properties": {
            "check": {"type": "string"},
            "result": {"type": "string", "enum": ["PASS", "FAIL", "ADVISORY"]},
            "evidence": {"type": "string"},
        },
    },
}

GATE_REPORT_SCHEMA = {
    "type": "object",
    "required": ["day", "agent", "criteria_results", "blockers", "deferred", "gate_decision", "hold_reason"],
    "properties": {
        "day": {"type": "integer"},
        "agent": {"type": "string", "const": "GATE"},
        "criteria_results": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["criterion", "result", "evidence"],
                "properties": {
                    "criterion": {"type": "string"},
                    "result": {"type": "string", "enum": ["PASS", "FAIL", "PARTIAL"]},
                    "evidence": {"type": "string"},
                },
            },
        },
        "blockers": {"type": "array", "items": {"type": "string"}},
        "deferred": {"type": "array", "items": {"type": "string"}},
        "gate_decision": {"type": "string", "enum": ["SHIP", "HOLD"]},
        "hold_reason": {"type": "string"},
    },
    "additionalProperties": True,
}

SENTINEL_REPORT_SCHEMA = {
    "type": "object",
    "required": ["day", "agent", "findings", "advisories", "blockers", "sentinel_decision", "hold_reason"],
    "properties": {
        "day": {"type": "integer"},
        "agent": {"type": "string", "const": "SENTINEL"},
        "findings": _FINDINGS_SCHEMA,
        "advisories": {"type": "array", "items": {"type": "string"}},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "sentinel_decision": {"type": "string", "enum": ["SHIP", "HOLD", "ADVISORY"]},
        "hold_reason": {"type": "string"},
    },
    "additionalProperties": True,
}

CONDUIT_REPORT_SCHEMA = {
    "type": "object",
    "required": ["day", "agent", "findings", "advisories", "blockers", "conduit_decision", "hold_reason"],
    "properties": {
        "day": {"type": "integer"},
        "agent": {"type": "string", "const": "CONDUIT"},
        "findings": _FINDINGS_SCHEMA,
        "advisories": {"type": "array", "items": {"type": "string"}},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "conduit_decision": {"type": "string", "enum": ["SHIP", "HOLD", "ADVISORY"]},
        "hold_reason": {"type": "string"},
    },
    "additionalProperties": True,
}

CONTEXT_MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["release", "generated_at", "source_hashes", "files"],
    "properties": {
        "release": {"type": "string"},
        "generated_at": {"type": "string"},  # ISO-8601 UTC timestamp
        "source_hashes": {
            "type": "object",
            "additionalProperties": {"type": "string"},  # filename → SHA-256 hex
        },
        "files": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "additionalProperties": True,
}
