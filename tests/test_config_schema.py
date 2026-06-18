#!/usr/bin/env python3
"""Test script for config schema validation."""
import json
import subprocess
import sys
import tempfile
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_SCHEMA = os.path.join(ROOT_DIR, "profiles", "config.schema.json")
OVERRIDE_SCHEMA = os.path.join(ROOT_DIR, "profiles", "config.override.schema.json")
CHECK_SCRIPT = os.path.join(ROOT_DIR, "bin", "check-schema.py")

def validate(yaml_content, schema):
    """Validate YAML content against a schema."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        yaml_file = f.name
    
    try:
        result = subprocess.run(
            [sys.executable, CHECK_SCRIPT, yaml_file, schema],
            capture_output=True, text=True
        )
        return result.returncode == 0, result.stdout + result.stderr
    finally:
        os.unlink(yaml_file)

def test_base_required_keys():
    """Test that base config requires model, toolsets, and agent."""
    # Missing 'model' should fail
    valid = validate('toolsets: [kanban]\nagent: {}\n', BASE_SCHEMA)
    print("test_base_required_keys: missing model → pass" if not valid else "FAIL: should reject config without 'model'")
    
    # Missing 'toolsets' should fail
    valid = validate('model: {default: test, provider: custom}\nagent: {}\n', BASE_SCHEMA)
    print("test_base_required_keys: missing toolsets → pass" if not valid else "FAIL: should reject config without 'toolsets'")
    
    # Missing 'agent' should fail
    valid = validate('model: {default: test, provider: custom}\ntoolsets: [kanban]\n', BASE_SCHEMA)
    print("test_base_required_keys: missing agent → pass" if not valid else "FAIL: should reject config without 'agent'")

def test_base_valid():
    """Test that a valid base config passes."""
    valid = validate('model: {default: test, provider: custom}\ntoolsets: [kanban, file]\nagent: {max_turns: 60}\n', BASE_SCHEMA)
    print("test_base_valid: should pass valid config" if valid else "FAIL: valid config rejected")

def test_override_optional():
    """Test that override configs are optional for any key."""
    # Empty override should pass
    valid = validate('', OVERRIDE_SCHEMA)
    print("test_override_optional: empty config → pass" if valid else "FAIL: empty config rejected")
    
    # Only 'toolsets' should pass
    valid = validate('toolsets: [kanban]\n', OVERRIDE_SCHEMA)
    print("test_override_optional: only toolsets → pass" if valid else "FAIL: toolsets-only rejected")
    
    # Only 'agent' should pass
    valid = validate('agent: {max_turns: 90}\n', OVERRIDE_SCHEMA)
    print("test_override_optional: only agent → pass" if valid else "FAIL: agent-only rejected")

def test_override_with_extra():
    """Test that extra keys are allowed in override (additionalProperties: true)."""
    valid = validate('toolsets: [kanban]\nextra_key: value\n', OVERRIDE_SCHEMA)
    print("test_override_with_extra: extra keys → pass" if valid else "FAIL: extra keys rejected")

def test_agent_properties():
    """Test agent property validation."""
    # Invalid agent property
    valid = validate('agent: {max_turns: 60, extra_prop: value}\n', BASE_SCHEMA)
    print("test_agent_properties: extra agent prop → pass" if not valid else "FAIL: extra agent prop accepted")
    
    # Valid agent with all properties
    valid = validate('agent: {max_turns: 60, tool_use_enforcement: auto, reasoning_effort: medium}\n', BASE_SCHEMA)
    print("test_agent_properties: valid agent → pass" if valid else "FAIL: valid agent rejected")

def run_all_tests():
    """Run all validation tests."""
    print("=== Running validation tests ===\n")
    
    test_base_required_keys()
    test_base_valid()
    test_override_optional()
    test_override_with_extra()
    test_agent_properties()
    
    print("\n=== All tests complete ===")

if __name__ == "__main__":
    run_all_tests()
