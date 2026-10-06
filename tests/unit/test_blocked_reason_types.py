"""Unit tests for the deterministic blocked_reason_type taxonomy (paths.py).

`blocked_reason` is display-only free text; `blocked_reason_type` is the
canonical code agents emit verbatim (`block --reason <code>`) and the only
thing routing ever matches on. Classification is exact-match — no prose
heuristics.
"""

from paths import (
    BLOCKED_REASON_TYPE_HUMAN_GATE,
    BLOCKED_REASON_TYPES,
    normalize_blocked_reason_type,
)


class TestNormalizeBlockedReasonType:
    def test_canonical_codes_pass_through(self):
        for code in BLOCKED_REASON_TYPES:
            assert normalize_blocked_reason_type(code) == code

    def test_codes_are_trimmed_and_lowercased(self):
        assert (
            normalize_blocked_reason_type("  Changes-Requested  ")
            == "changes-requested"
        )

    def test_unknown_prose_classifies_as_human_gate(self):
        for prose in (
            "waiting for API keys",
            "needs human review of the design",
            "Human Review & Merge",
            "review-required",
            "",
            None,
        ):
            assert (
                normalize_blocked_reason_type(prose) == BLOCKED_REASON_TYPE_HUMAN_GATE
            )

    def test_taxonomy_is_stable(self):
        assert BLOCKED_REASON_TYPES == {"changes-requested", "approved", "human-gate"}
