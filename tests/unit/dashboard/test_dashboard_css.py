"""Unit tests for dashboard stylesheet portability, variant class coverage, and build reproducibility."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def _zf_css_selectors(tokens):
    out = []
    for tok in tokens:
        esc = "."
        for ch in tok:
            if ch in ":/.[]":
                esc += "\\" + ch
            else:
                esc += ch
        out.append(esc)
    return out


_ZF_VARIANT_STACK = re.compile(
    r"^(?:hover|focus|focus-within|active|disabled|group-hover|md|lg|sm|xl|2xl):"
)
_ZF_NAMED_COLORS = {
    "black",
    "white",
    "transparent",
    "currentColor",
    "inherit",
    "initial",
    "unset",
}


def _zf_is_genuine_value_utility(token):
    """True if a non-variant class token is a value-bearing Tailwind utility.

    These are the plain utilities (``bg-sky-950/20``, ``mb-3.5``,
    ``text-[9px]``, ``max-w-[130px]``) that part (b)'s variant-prefixed check
    never inspects — so a stale stylesheet can pass the variant delta while
    silently dropping them. Tailwind v4's dynamic spacing/scale accepts
    integer or ``.25``/``.75`` steps, so e.g. ``py-0.2`` is not a real
    utility (the
    compiler emits nothing for it); we exclude those so the in-sync check
    cannot flag dead classes.
    """
    if _ZF_VARIANT_STACK.match(token):
        return False
    body = token
    if "/" in token:
        pre, post = token.rsplit("/", 1)
        if not re.fullmatch(r"\d{1,3}", post):
            return False  # opacity / not a Tailwind value ratio
        body = pre
    m = re.search(r"\[([^\[\]]+)\]$", body)
    if m:
        v = m.group(1)
        return bool(re.search(r"\d", v)) or v in _ZF_NAMED_COLORS
    m = re.match(r"^(-?[A-Za-z][A-Za-z0-9-]*?)-(\d+(?:\.\d+)?)$", body)
    if m:
        # v4 dynamic spacing/scale accepts whole numbers and .25 steps.
        return re.fullmatch(r"\d+|\d+\.(25|5|75)", m.group(2)) is not None
    m = re.match(r"^([A-Za-z][A-Za-z0-9-]*?)-([a-zA-Z]+)$", body)
    if m:
        return m.group(2) in _ZF_NAMED_COLORS
    return False


def _zf_js_class_tokens(source):
    token_charset = re.compile(r"[A-Za-z0-9_:\[\]/%#!.-]+")
    strings = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch == "/" and i + 1 < n and source[i + 1] == "/":  # line comment
            e = source.find("\n", i)
            i = n if e == -1 else e + 1
        elif ch == "/" and i + 1 < n and source[i + 1] == "*":  # block comment
            e = source.find("*/", i + 2)
            i = n if e == -1 else e + 2
        elif ch in ("'", '"', "`"):
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == ch:
                    j += 1
                    break
                j += 1
            strings.append(source[i + 1 : j - 1])
            i = j
        else:
            i += 1
    tokens = set()
    for s in strings:
        for tok in s.split():
            if (
                len(tok) >= 2
                and re.fullmatch(token_charset, tok)
                and re.search(r"[a-z]", tok)
                and not tok.startswith("//")
            ):
                tokens.add(tok)
    return tokens


def test_dashboard_css_is_portable_and_in_sync_with_js():
    """Verify stylesheet portability, variant selectors, and build reproducibility."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    dash = repo_root / "dashboard"
    input_css = (dash / "input.css").read_text(encoding="utf-8")
    style_css = (dash / "dist" / "style.css").read_text(encoding="utf-8")
    js_src = (dash / "dist" / "index.js").read_text(encoding="utf-8")

    # (a) No machine-specific absolute paths
    for label, text in (("input.css", input_css), ("style.css", style_css)):
        assert not re.search(r"/home/|/Users/|C:\\", text), (
            f"{label} contains absolute machine-specific paths"
        )

    # (b) Every variant-prefixed class token has a selector
    tokens = _zf_js_class_tokens(js_src)
    variant_tokens = [t for t in tokens if _ZF_VARIANT_STACK.match(t)]
    assert len(variant_tokens) >= 10, "Expected UI to reference variant classes"

    missing = [
        t for t in sorted(variant_tokens) if _zf_css_selectors((t,))[0] not in style_css
    ]
    assert missing == [], f"dist/style.css missing selectors for: {missing[:10]}"

    # (b2) Every plain (non-variant) value utility has a selector. Pure text
    # comparison (no node/tailwind required) and non-skippable: this is the
    # guard that catches a stale committed stylesheet even when node_modules
    # is absent, so drift can no longer ship silently.
    value_tokens = [t for t in tokens if _zf_is_genuine_value_utility(t)]
    assert len(value_tokens) >= 100, "Expected UI to reference plain value utilities"
    missing_value = [
        t for t in sorted(value_tokens) if _zf_css_selectors((t,))[0] not in style_css
    ]
    assert missing_value == [], (
        "dist/style.css is stale — missing selectors for plain utilities: "
        f"{missing_value[:10]}"
    )

    # Smoke: each interaction state family must be present at least once
    for family in (
        r"\.hover\\:",
        r"\.focus-within\\:",
        r"\.active\\:",
        r"\.disabled\\:",
    ):
        assert re.search(family, style_css), (
            f"committed stylesheet has no {family} selector"
        )

    # (c) Build reproducibility check if node is available
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH; cannot verify CSS build reproducibility")

    build_mjs = dash / "build_css.mjs"
    env = dict(os.environ)
    env["ZEROFACTORY_SKIP_DISPATCHER"] = "1"
    try:
        r = subprocess.run(
            [node, str(build_mjs)],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as e:
        pytest.skip(f"cannot run node build ({e}); skipping")

    if r.returncode != 0:
        if "Cannot locate the tailwindcss package" in (r.stderr or ""):
            pytest.skip("tailwindcss not installed; run npm install")
        pytest.fail(f"dashboard/build_css.mjs failed:\n{r.stdout}\n{r.stderr}")

    rebuilt = (dash / "dist" / "style.css").read_text(encoding="utf-8")
    assert rebuilt == style_css, (
        "committed dist/style.css does not match output of build_css.mjs"
    )
