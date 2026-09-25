"""Backward-compatible entry point for Zero Factory End-to-End (E2E) Test Suite.

All individual test suites are now modularized under tests/e2e/:
- tests/e2e/test_cli_lifecycle.py
- tests/e2e/test_multi_agent_workflow.py
- tests/e2e/test_automation_scripts.py
- tests/e2e/test_plugin_api.py
- tests/e2e/test_concurrency_resilience.py
"""

from __future__ import annotations

import os
import unittest

# Ensure hermetic test environment defaults
os.environ.setdefault("ZEROFACTORY_SKIP_GIT", "1")
os.environ.setdefault("ZEROFACTORY_SKIP_CRON_SYNC", "1")
os.environ.setdefault("ZEROFACTORY_DISABLE_DISPATCHER", "1")
os.environ.setdefault("ZEROFACTORY_SKIP_WORKER_SPAWN", "1")

from tests.e2e.test_automation_scripts import TestAutomationScriptsE2E
from tests.e2e.test_cli_lifecycle import TestZeroFactoryCLIE2E
from tests.e2e.test_concurrency_resilience import TestConcurrencyAndResilienceE2E
from tests.e2e.test_multi_agent_workflow import TestMultiAgentLifecycleE2E
from tests.e2e.test_plugin_api import TestPluginAPIE2E

__all__ = [
    "TestZeroFactoryCLIE2E",
    "TestMultiAgentLifecycleE2E",
    "TestAutomationScriptsE2E",
    "TestPluginAPIE2E",
    "TestConcurrencyAndResilienceE2E",
]

if __name__ == "__main__":
    unittest.main()
