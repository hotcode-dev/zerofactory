"""Unit tests for paths.py profile-path and assignee resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dispatcher as D
import paths as P
from dashboard.plugin_api import (
    PROFILE_MAP as PA_PROFILE_MAP,
    VALID_ASSIGNEES as PA_VALID_ASSIGNEES,
    get_profile_state_db,
    normalize_assignee as PA_normalize_assignee,
)


class TestPathsResolution(unittest.TestCase):
    """Dedup + correctness tests for shared profile-path / assignee helpers in paths.py."""

    def _mk(self, base: Path, *parts: str) -> Path:
        """Create base/parts... and return the file path."""
        p = base.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch(exist_ok=True)
        return p

    def _with_fake_home(self, home_root: Path, plugin_root):
        """Context manager pointing paths.Path.home at home_root and plugin-relative root at plugin_root."""
        return (
            mock.patch("pathlib.Path.home", return_value=home_root),
            mock.patch.object(P, "_plugin_profiles_root", return_value=plugin_root),
        )

    # --- state.db resolution strategy --------------------------------------

    def test_state_db_per_profile(self):
        """Per-profile path wins when it exists (primary layout)."""
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            self._mk(home_root, ".hermes", "profiles", "zf-builder", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=None)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    home_root / ".hermes" / "profiles" / "zf-builder" / "state.db",
                )

    def test_state_db_plugin_relative_fallback(self):
        """Plugin-relative fallback is returned when ONLY that exists."""
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            plugin_root = Path(td) / "plugin_profiles"
            self._mk(plugin_root, "zf-builder", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=plugin_root)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    plugin_root / "zf-builder" / "state.db",
                )

    def test_state_db_global_fallback_and_none(self):
        """Global ~/.hermes/state.db is the last resort, and None when nothing exists."""
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            self._mk(home_root, ".hermes", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=None)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    home_root / ".hermes" / "state.db",
                )

        # Nothing present -> None.
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=None)
            with home_ctx, plug_ctx:
                self.assertIsNone(P.resolve_profile_state_db("zf-builder"))

    def test_state_db_legacy_unprefixed_and_priority(self):
        """Legacy un-prefixed profile dir is honored, and priority is honored."""
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            self._mk(home_root, ".hermes", "profiles", "builder", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=None)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    home_root / ".hermes" / "profiles" / "builder" / "state.db",
                )

        # Priority: canonical beats plugin-relative beats global.
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            plugin_root = Path(td) / "plugin_profiles"
            self._mk(home_root, ".hermes", "state.db")
            self._mk(plugin_root, "zf-builder", "state.db")
            self._mk(home_root, ".hermes", "profiles", "zf-builder", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=plugin_root)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    home_root / ".hermes" / "profiles" / "zf-builder" / "state.db",
                )
            # Remove the canonical one; plugin-relative now wins over global.
            (home_root / ".hermes" / "profiles" / "zf-builder" / "state.db").unlink()
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    plugin_root / "zf-builder" / "state.db",
                )

    # --- assignee normalization --------------------------------------------

    def test_normalize_assignee_roundtrip_and_unknown(self):
        """Round-trips valid profiles and maps unknown/empty assignees to unassigned."""
        self.assertEqual(P.normalize_assignee("zf-builder"), "zf-builder")
        self.assertEqual(P.normalize_assignee("zf-reviewer"), "zf-reviewer")
        self.assertEqual(P.normalize_assignee("zf-orchestrator"), "zf-orchestrator")
        self.assertEqual(P.normalize_assignee("human"), "human")
        self.assertEqual(P.normalize_assignee("unassigned"), "unassigned")
        self.assertEqual(P.normalize_assignee(None), "unassigned")
        self.assertEqual(P.normalize_assignee(""), "unassigned")
        self.assertEqual(P.normalize_assignee("antigravity"), "unassigned")
        self.assertEqual(P.normalize_assignee("some-custom-tool"), "unassigned")

    def test_dispatcher_and_dashboard_agree(self):
        """The dispatcher's spawn-path resolver and dashboard's get_profile_state_db agree."""
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            plugin_root = Path(td) / "plugin_profiles"
            self._mk(plugin_root, "zf-reviewer", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=plugin_root)
            with home_ctx, plug_ctx:
                expected = plugin_root / "zf-reviewer" / "state.db"
                self.assertEqual(D.resolve_profile_state_db("zf-reviewer"), expected)
                self.assertEqual(get_profile_state_db("zf-reviewer"), expected)
                self.assertIs(D.resolve_profile_state_db, P.resolve_profile_state_db)
                self.assertEqual(get_profile_state_db("zf-reviewer"), P.resolve_profile_state_db("zf-reviewer"))

    def test_single_source_of_truth_identity(self):
        """dispatcher and dashboard re-export the SAME objects from paths.py."""
        self.assertIs(D.PROFILE_MAP, P.PROFILE_MAP)
        self.assertIs(PA_PROFILE_MAP, P.PROFILE_MAP)
        self.assertIs(D.normalize_assignee, P.normalize_assignee)
        self.assertIs(PA_normalize_assignee, P.normalize_assignee)
        self.assertIs(PA_VALID_ASSIGNEES, P.VALID_ASSIGNEES)
        self.assertCountEqual(
            PA_VALID_ASSIGNEES,
            {"unassigned", "human", "zf-builder", "zf-reviewer", "zf-orchestrator"},
        )
        self.assertCountEqual(
            D.VALID_PROFILES,
            {"zf-builder", "zf-reviewer", "zf-orchestrator"},
        )
        self.assertNotIn("unassigned", D.VALID_PROFILES)
        self.assertNotIn("human", D.VALID_PROFILES)


if __name__ == "__main__":
    unittest.main()
