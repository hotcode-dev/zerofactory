#!/usr/bin/env python3
"""Validate a YAML config file against the JSON schema."""
import json
import subprocess
import sys
import os

def main():
    if len(sys.argv) != 3:
        print("Usage: check-schema.py <yaml-file> <schema-file>", file=sys.stderr)
        sys.exit(2)

    yaml_file = sys.argv[1]
    schema_file = sys.argv[2]

    # Convert YAML to JSON
    result = subprocess.run(["yq", "eval", "-o=json", ".", yaml_file],
                          capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAIL: {yaml_file} is not valid YAML", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    json_str = result.stdout
    # Validate it's valid JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"FAIL: {yaml_file} YAML->JSON conversion failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Load schema and check if data passes validation
    try:
        import jsonschema
    except ImportError:
        print("WARN: jsonschema not installed — doing basic validation", file=sys.stderr)
        # Fallback: just check that the output is valid JSON with expected top-level keys
        expected_keys = ["model", "toolsets", "agent"]
        missing = [k for k in expected_keys if k not in data]
        if missing:
            print(f"FAIL: {yaml_file} missing required top-level keys: {missing}", file=sys.stderr)
            sys.exit(1)
        print(f"  OK: {yaml_file} passes basic schema validation")
        sys.exit(0)

    with open(schema_file) as f:
        schema = json.load(f)

    # Ensure $defs is defined at root level for Draft7Validator
    if "$defs" not in schema and "definitions" in schema:
        schema["$defs"] = schema.pop("definitions")
    
    # Ensure $schema is set for Draft7Validator to work properly
    if "$schema" not in schema:
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        print(f"FAIL: {yaml_file} fails schema validation:", file=sys.stderr)
        for err in errors[:10]:  # Show first 10 errors
            path = ".".join(str(p) for p in err.path) if err.path else "(root)"
            print(f"  - {path}: {err.message}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"  OK: {yaml_file} passes schema validation")
        sys.exit(0)

if __name__ == "__main__":
    main()
