"""Playwright browser E2E tests for the Zero Factory React dashboard UI."""

from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = REPO_ROOT / "dashboard" / "dist"
REACT_UMD = REPO_ROOT / "node_modules" / "react" / "umd" / "react.production.min.js"
REACT_DOM_UMD = (
    REPO_ROOT / "node_modules" / "react-dom" / "umd" / "react-dom.production.min.js"
)


def _find_chromium_executable() -> str | None:
    for candidate in ("chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _start_http_bridge(app: FastAPI) -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    client = TestClient(app)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _forward(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length")
            }
            resp = client.request(
                self.command, self.path, content=body, headers=headers
            )
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ("content-length", "transfer-encoding", "content-encoding"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp.content)))
            self.end_headers()
            self.wfile.write(resp.content)

        def do_GET(self) -> None:
            self._forward()

        def do_POST(self) -> None:
            self._forward()

        def do_PUT(self) -> None:
            self._forward()

        def do_PATCH(self) -> None:
            self._forward()

        def do_DELETE(self) -> None:
            self._forward()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = int(httpd.server_address[1])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread, port


def _build_test_app() -> FastAPI:
    from dashboard.plugin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/zerofactory")

    @app.get("/assets/react.js")
    def _react():
        return FileResponse(REACT_UMD, media_type="application/javascript")

    @app.get("/assets/react-dom.js")
    def _react_dom():
        return FileResponse(REACT_DOM_UMD, media_type="application/javascript")

    @app.get("/dist/index.js")
    def _bundle():
        return FileResponse(DIST_DIR / "index.js", media_type="application/javascript")

    @app.get("/dist/style.css")
    def _css():
        return FileResponse(DIST_DIR / "style.css", media_type="text/css")

    @app.get("/", response_class=HTMLResponse)
    def _index():
        return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Zero Factory UI E2E</title>
  <link rel="stylesheet" href="/dist/style.css" />
</head>
<body class="bg-slate-950 text-slate-100">
  <div id="root"></div>
  <script src="/assets/react.js"></script>
  <script src="/assets/react-dom.js"></script>
  <script>
    window.__HERMES_PLUGIN_SDK__ = {
      React: window.React,
      hooks: window.React,
      fetchJSON: async function(url, opts) {
        const res = await fetch(url, opts || {});
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      },
      utils: {}
    };
    window.__HERMES_PLUGINS__ = {
      _reg: {},
      register: function(name, Comp) { this._reg[name] = Comp; }
    };
  </script>
  <script src="/dist/index.js"></script>
  <script>
    const Comp = window.__HERMES_PLUGINS__._reg["zerofactory"];
    const root = window.ReactDOM.createRoot(document.getElementById("root"));
    root.render(window.React.createElement(Comp));
  </script>
</body>
</html>"""

    return app


def test_dashboard_setup_banner_new_task_and_settings_playwright(tmp_path, monkeypatch):
    sync_api = pytest.importorskip("playwright.sync_api")
    if not (REACT_UMD.is_file() and REACT_DOM_UMD.is_file()):
        pytest.skip("React UMD assets not found in node_modules")
    if not (DIST_DIR / "index.js").is_file():
        pytest.skip("dashboard/dist/index.js not built")

    chromium_bin = _find_chromium_executable()
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    db_path = tmp_path / "zf_ui.db"

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("ZEROFACTORY_DB", str(db_path))
    monkeypatch.setenv("ZEROFACTORY_DISABLE_DISPATCHER", "1")

    import profile_manager
    from dashboard.db import init_db

    monkeypatch.setattr(
        profile_manager, "check_gh_auth_status", lambda use_cache=True: True
    )
    init_db(force=True)

    now = int(time.time())
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO boards (slug, created_at, updated_at) VALUES ('demo', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO board_repositories (board_slug, repo_alias, git_url, created_at, updated_at) "
            "VALUES ('demo', 'main', 'https://example.com/demo.git', ?, ?)",
            (now, now),
        )
        conn.commit()

    httpd, thread, port = _start_http_bridge(_build_test_app())
    try:

        with sync_api.sync_playwright() as p:
            launch_kwargs: dict[str, object] = {"headless": True}
            if chromium_bin:
                launch_kwargs["executable_path"] = chromium_bin
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")

            # 1. Setup Wizard banner renders CLI setup & start commands
            page.get_by_text("hermes zerofactory setup").wait_for(timeout=10000)
            page.get_by_text("hermes zerofactory start").wait_for(timeout=10000)

            # 2. Provision zf-* profiles and reload -> start command remains, setup completed
            profile_manager.ensure_zf_profiles()
            page.reload(wait_until="networkidle")
            page.get_by_text("hermes zerofactory start").wait_for(timeout=10000)

            # 3. Create a task via the + New Task modal
            page.get_by_role("button", name="+ New Task").click()
            page.get_by_placeholder("e.g. Implement caching layer for Redis").fill(
                "Playwright UI Task"
            )
            page.get_by_role("button", name="Create Task").click()
            page.get_by_text("Playwright UI Task").wait_for(timeout=10000)

            # 4. Open Settings modal and verify it renders without errors
            page.get_by_role("button", name="⚙️ Settings").click()
            page.get_by_text("Zero Factory Global Settings").wait_for(timeout=10000)

            assert page_errors == [], f"Uncaught page errors: {page_errors}"
            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
