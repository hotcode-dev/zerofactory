"""Unit tests for dashboard/memory_service.py: rule extraction, normalization, deduplication."""

import sqlite3

from dashboard.memory_service import (
    compute_dedup_key,
    extract_and_record_memory,
    normalize_file_path,
    normalize_memory_content,
)


def _init_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE boards (
            slug TEXT PRIMARY KEY,
            auto_record_memory INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE board_memories (
            id TEXT PRIMARY KEY,
            board_slug TEXT,
            task_id TEXT,
            category TEXT,
            content TEXT,
            tags TEXT,
            author TEXT,
            created_at INTEGER,
            updated_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            actor TEXT,
            board_slug TEXT,
            details TEXT,
            created_at INTEGER
        )
        """
    )
    conn.commit()
    return conn


def test_normalize_memory_content_and_file_path():
    """Verify stripping of quotes, backticks, casefolding, and path normalizing."""
    assert normalize_memory_content("  `*Important Rule*`  ") == "important rule"
    assert normalize_file_path("./src/utils/file.ts") == "src/utils/file.ts"
    assert normalize_file_path("src\\utils\\file.ts") == "src/utils/file.ts"


def test_compute_dedup_key():
    """Deterministic fingerprint from file list and category."""
    files = ["src/b.py", "src/a.py", "./src/b.py"]
    key = compute_dedup_key(files, category="bug-fix")
    assert key == "src/a.py,src/b.py:bug-fix"

    assert compute_dedup_key([]) is None
    assert compute_dedup_key(None) is None


def test_extract_and_record_memory_basic():
    """Reviewer feedback containing GOTCHA: is extracted and stored."""
    conn = _init_memory_db()
    conn.execute(
        "INSERT INTO boards (slug, auto_record_memory) VALUES ('test-board', 1)"
    )
    conn.commit()

    feedback = "LGTM! One note for future: **GOTCHA**: Always run db migrations before starting worker."
    recorded = extract_and_record_memory(
        conn, "test-board", feedback, task_id="t-1", author="zf-reviewer"
    )

    assert len(recorded) == 1
    assert recorded[0]["category"] == "gotcha"
    assert "Always run db migrations before starting worker" in recorded[0]["content"]

    # Verify stored in DB
    rows = conn.execute(
        "SELECT * FROM board_memories WHERE board_slug = 'test-board'"
    ).fetchall()
    assert len(rows) == 1

    # Second run with same feedback should deduplicate and return empty
    duplicate_run = extract_and_record_memory(
        conn, "test-board", feedback, task_id="t-2"
    )
    assert duplicate_run == []
    rows_after = conn.execute(
        "SELECT * FROM board_memories WHERE board_slug = 'test-board'"
    ).fetchall()
    assert len(rows_after) == 1


def test_extract_and_record_memory_board_disabled():
    """When board has auto_record_memory disabled, nothing is extracted."""
    conn = _init_memory_db()
    conn.execute(
        "INSERT INTO boards (slug, auto_record_memory) VALUES ('disabled-board', 0)"
    )
    conn.commit()

    feedback = "GOTCHA: Should not be saved."
    recorded = extract_and_record_memory(conn, "disabled-board", feedback)
    assert recorded == []

    rows = conn.execute(
        "SELECT * FROM board_memories WHERE board_slug = 'disabled-board'"
    ).fetchall()
    assert len(rows) == 0


def test_mem0_disabled_setting():
    """When mem0_enabled is false, get_mem0_client returns None."""
    from dashboard.memory_service import get_mem0_client

    conn = _init_memory_db()
    conn.execute("INSERT INTO settings (key, value) VALUES ('mem0_enabled', 'false')")
    conn.commit()

    client = get_mem0_client(conn)
    assert client is None


def test_mem0_default_disabled_and_no_private_defaults(monkeypatch, tmp_path):
    """Mem0 defaults to disabled, with no private host or model fallbacks."""
    import settings as S
    from dashboard.memory_service import get_hermes_model_defaults, get_mem0_client

    assert S.DEFAULT_MEM0_ENABLED is False
    assert S.DEFAULT_MEM0_MODEL == ""

    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    for var in (
        "MEM0_LLM_MODEL",
        "OPENAI_MODEL",
        "MEM0_BASE_URL",
        "OPENAI_BASE_URL",
        "MEM0_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    model, base_url, api_key = get_hermes_model_defaults()
    assert model == ""
    assert base_url == ""
    assert api_key == ""
    assert "spark.ntsd.dev" not in base_url
    assert "RadixArk" not in model

    conn = _init_memory_db()
    assert get_mem0_client(conn) is None


def test_openai_api_key_isolated_from_custom_base_url(monkeypatch):
    """OPENAI_API_KEY is only sent to https://api.openai.com or empty base_url."""
    from dashboard.memory_service import (
        _is_openai_official_url,
        _resolve_api_key_for_url,
    )

    assert _is_openai_official_url("") is True
    assert _is_openai_official_url("https://api.openai.com/v1") is True
    assert _is_openai_official_url("http://api.openai.com/v1") is False
    assert _is_openai_official_url("api.openai.com") is False
    assert _is_openai_official_url("https://custom.example.com/v1") is False

    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-openai")
    monkeypatch.delenv("MEM0_API_KEY", raising=False)

    assert _resolve_api_key_for_url("https://api.openai.com/v1") == "sk-secret-openai"
    assert (
        _resolve_api_key_for_url("https://custom.example.com/v1") != "sk-secret-openai"
    )
    assert (
        _resolve_api_key_for_url(
            "https://custom.example.com/v1", allow_dummy_for_custom=False
        )
        == ""
    )


def test_extract_and_record_memory_passes_infer_false(monkeypatch):
    """extract_and_record_memory passes infer=False to client.add."""
    import dashboard.memory_service as ms

    calls = []

    class _FakeClient:
        def add(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(ms, "get_mem0_client", lambda conn=None: _FakeClient())

    conn = _init_memory_db()
    conn.execute(
        "INSERT INTO boards (slug, auto_record_memory) VALUES ('test-board', 1)"
    )
    conn.commit()

    recorded = ms.extract_and_record_memory(
        conn, "test-board", "GOTCHA: Always pass infer=False.", task_id="t-1"
    )
    assert len(recorded) == 1
    assert len(calls) == 1
    assert calls[0][1].get("infer") is False
