#!/usr/bin/env python3
"""
validate_graph.py -- Validate a project-graph.json against the schema.

Stdlib only, Python 3.8+. Implements a minimal JSON Schema Draft-07 validator
that covers everything in templates/project-graph.schema.json:
  - required / additionalProperties
  - type
  - enum
  - $ref resolution (internal #/$defs/...)
  - minItems / maxItems / minLength / maxLength
  - properties recursion
  - $defs lookup

This avoids a hard `jsonschema` dependency. The validator is intentionally
narrow -- it covers what the project-defense schema actually uses.

Usage:
  python3 validate_graph.py <path-to-project-graph.json>
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ----------------------------------------------------------------------
# Schema resolver
# ----------------------------------------------------------------------


def resolve_ref(schema: Dict[str, Any], ref: str) -> Dict[str, Any]:
    """Resolve an internal $ref like '#/$defs/evidence'."""
    if not ref.startswith("#/"):
        raise ValueError(f"Only internal refs are supported, got: {ref}")
    parts = ref[2:].split("/")
    node: Any = schema
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise ValueError(f"Ref not found: {ref}")
    return node


# ----------------------------------------------------------------------
# Validator
# ----------------------------------------------------------------------


def validate_value(
    value: Any,
    schema: Dict[str, Any],
    root_schema: Dict[str, Any],
    path: str = "$",
) -> List[str]:
    """Return a list of error strings. Empty list = valid."""
    errors: List[str] = []

    # Resolve $ref
    if "$ref" in schema:
        ref_schema = resolve_ref(root_schema, schema["$ref"])
        return validate_value(value, ref_schema, root_schema, path)

    # Type check
    if "type" in schema:
        expected = schema["type"]
        if not _matches_type(value, expected):
            errors.append(f"{path}: expected type {expected}, got {type(value).__name__}")
            return errors  # downstream type checks are meaningless

    # Enum
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']}")

    # String constraints
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: string length {len(value)} < minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: string length {len(value)} > maxLength {schema['maxLength']}")

    # Array constraints
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: array length {len(value)} < minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: array length {len(value)} > maxItems {schema['maxItems']}")
        # Item schema
        if "items" in schema:
            for i, item in enumerate(value):
                errors.extend(validate_value(item, schema["items"], root_schema, f"{path}[{i}]"))

    # Object constraints
    if isinstance(value, dict):
        # required
        if "required" in schema:
            for req in schema["required"]:
                if req not in value:
                    errors.append(f"{path}: missing required property {req!r}")
        # additionalProperties
        if schema.get("additionalProperties") is False and "properties" in schema:
            allowed = set(schema["properties"].keys())
            for k in value.keys():
                if k not in allowed:
                    errors.append(f"{path}: unexpected property {k!r} (not in schema)")
        # properties
        if "properties" in schema:
            for k, sub_schema in schema["properties"].items():
                if k in value:
                    errors.extend(validate_value(value[k], sub_schema, root_schema, f"{path}.{k}"))

    return errors


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_graph.py <project-graph.json> [path-to-schema.json]", file=sys.stderr)
        sys.exit(2)

    graph_path = Path(sys.argv[1]).resolve()
    if not graph_path.exists():
        print(f"Error: {graph_path} does not exist", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) >= 3:
        schema_path = Path(sys.argv[2]).resolve()
    else:
        # Default: alongside the script, in templates/
        script_dir = Path(__file__).parent
        schema_path = script_dir.parent / "templates" / "project-graph.schema.json"

    if not schema_path.exists():
        print(f"Error: schema not found at {schema_path}", file=sys.stderr)
        sys.exit(1)

    try:
        graph = json.loads(graph_path.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL: {graph_path} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        schema = json.loads(schema_path.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL: {schema_path} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate_value(graph, schema, schema)
    if errors:
        print(f"FAIL: {graph_path} has {len(errors)} schema violation(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: {graph_path} validates against {schema_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()