"""Start the Next.js UI and publish interactive pipeline results for the dashboard."""
from __future__ import annotations

import atexit
import cgi
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from config import CONFIG
from interactive_pipeline import PipelineOptions, run_interactive_pipeline
from session_store import list_session_rows, load_session, new_session_id, save_session
from transcription import transcribe_audio

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
NEXT_BIN = FRONTEND_DIR / "node_modules" / "next" / "dist" / "bin" / "next"
LIVE_SESSION_PUBLIC = FRONTEND_DIR / "public" / "live-session.json"
LIVE_SESSION_DATA = PROJECT_ROOT / "data" / "live-session.json"
FALLBACK_HTML = FRONTEND_DIR / "public" / "fallback-dashboard.html"
DEV_LOG = FRONTEND_DIR / ".trustnote-dev.log"
DEFAULT_NEXT_PORT = 3000
DEFAULT_API_PORT = 8765

_next_proc: subprocess.Popen | None = None
_dev_log_handle: object | None = None
_api_server: ThreadingHTTPServer | None = None
_browser_opened = False
_ui_base_url: str = ""
_pipeline_options: PipelineOptions | None = None
_pipeline_lock = threading.Lock()
_session_jobs: dict[str, dict[str, Any]] = {}


def _run_web_session_job(
    session_id: str,
    transcript: str,
    meta: dict[str, Any],
    options: PipelineOptions,
) -> None:
    _session_jobs[session_id] = {"status": "processing", "sessionId": session_id}
    try:
        print()
        print("=" * 72)
        print(f"  TrustNote — Web session {session_id}")
        print("=" * 72)
        print(f"  Patient: {meta.get('patientName')} · Clinician: {meta.get('doctorName')}", flush=True)
        with _pipeline_lock:
            dashboard = run_interactive_pipeline(transcript, options, meta=meta, echo=True)
        save_session(dashboard, source="Web")
        publish_live_session(dashboard)
        rows = list_session_rows()
        list_row = next((r for r in rows if r.get("id") == session_id), rows[0] if rows else None)
        _session_jobs[session_id] = {
            "status": "complete",
            "sessionId": session_id,
            "listRow": list_row,
        }
        print(f"[trustnote] Web session {session_id} complete.", flush=True)
    except Exception as exc:
        print(f"[trustnote] Web session failed: {exc}", file=sys.stderr)
        _session_jobs[session_id] = {
            "status": "error",
            "sessionId": session_id,
            "error": str(exc),
        }


def configure_pipeline(options: PipelineOptions) -> None:
    global _pipeline_options
    _pipeline_options = options


def _pipeline_options_or_default() -> PipelineOptions:
    if _pipeline_options is not None:
        return _pipeline_options
    return PipelineOptions(
        gen_backend=CONFIG.GEN_BACKEND,
        verify_mode=CONFIG.VERIFY_MODE,
        dense=False,
        soap_only=False,
    )


def _node_executable() -> str:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is not installed. Install Node 18+ and run `npm install` in frontend/.")
    return node


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_url(url: str, timeout: float = 120.0, proc: subprocess.Popen | None = None) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if 200 <= resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.75)
    return False


def _tail_log(path: Path, lines: int = 25) -> str:
    if not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except OSError:
        return ""


def _next_dev_command(port: int) -> list[str]:
    if not NEXT_BIN.is_file():
        raise RuntimeError(
            f"Next.js is not installed. Run:\n  cd {FRONTEND_DIR}\n  npm install"
        )
    return [_node_executable(), str(NEXT_BIN), "dev", "-H", "127.0.0.1", "-p", str(port)]


def _open_browser(url: str) -> None:
    global _browser_opened
    if _browser_opened:
        return
    opened = webbrowser.open(url)
    if not opened:
        print(f"[trustnote] Open this URL in your browser: {url}", flush=True)
    _browser_opened = True


def start_frontend_dev(open_browser: bool = True, next_port: int = DEFAULT_NEXT_PORT) -> str:
    """Spawn Next.js dev server. Returns the URL users should open."""
    global _next_proc, _ui_base_url
    base = f"http://127.0.0.1:{next_port}"

    if not FRONTEND_DIR.is_dir():
        print("[trustnote] frontend/ not found — using fallback dashboard only.", file=sys.stderr)
        return f"http://127.0.0.1:{DEFAULT_API_PORT}/"

    if _port_in_use(next_port) and _wait_for_url(base, timeout=5):
        print(f"[trustnote] Web UI already running at {base}", flush=True)
        _ui_base_url = base
        if open_browser:
            _open_browser(base)
        return base

    try:
        cmd = _next_dev_command(next_port)
    except RuntimeError as exc:
        print(f"[trustnote] {exc}", file=sys.stderr)
        fallback = f"http://127.0.0.1:{DEFAULT_API_PORT}/"
        _ui_base_url = fallback
        if open_browser:
            _open_browser(fallback)
        return fallback

    env = os.environ.copy()
    env["PORT"] = str(next_port)
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env.pop("npm_config_package_manager", None)
    # Next 16 reads packageManager from package.json; we removed pnpm — force npm-style installs.
    env["npm_config_user_agent"] = "npm"

    DEV_LOG.parent.mkdir(parents=True, exist_ok=True)
    global _dev_log_handle
    _dev_log_handle = DEV_LOG.open("w", encoding="utf-8")
    print(f"[trustnote] Starting web UI: {' '.join(cmd)}", flush=True)
    print(f"[trustnote] Dev server log: {DEV_LOG}", flush=True)

    popen_kw: dict[str, Any] = {
        "cwd": str(FRONTEND_DIR),
        "env": env,
        "stdout": _dev_log_handle,
        "stderr": subprocess.STDOUT,
    }
    if sys.platform != "win32":
        popen_kw["start_new_session"] = True

    _next_proc = subprocess.Popen(cmd, **popen_kw)
    atexit.register(stop_frontend_dev)

    if _wait_for_url(base, timeout=120, proc=_next_proc):
        print(f"[trustnote] Web UI ready at {base}", flush=True)
        _ui_base_url = base
        if open_browser:
            _open_browser(base)
        return base

    proc_dead = _next_proc.poll() is not None
    log_tail = _tail_log(DEV_LOG)
    fallback = f"http://127.0.0.1:{DEFAULT_API_PORT}/"
    print(
        "[trustnote] Next.js dev server did not become ready in time.",
        file=sys.stderr,
    )
    if proc_dead:
        print("[trustnote] The dev server process exited early.", file=sys.stderr)
    if log_tail:
        print(f"[trustnote] Last lines from {DEV_LOG}:\n{log_tail}", file=sys.stderr)
    print(
        f"[trustnote] Using fallback dashboard at {fallback}\n"
        f"  Fix Next.js: cd frontend && npm install && npm run dev\n"
        f"  See full log: {DEV_LOG}",
        file=sys.stderr,
    )
    _ui_base_url = fallback
    if open_browser:
        _open_browser(fallback)
    return fallback


def stop_frontend_dev() -> None:
    global _next_proc
    if _next_proc and _next_proc.poll() is None:
        _next_proc.terminate()
        try:
            _next_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _next_proc.kill()
    _next_proc = None


class _LiveSessionHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {"status": "waiting", "message": "Run a conversation in the terminal."}

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_bytes(self, code: int, body: bytes, content_type: str) -> None:
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, code: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self._send_bytes(code, data, "application/json; charset=utf-8")

    def _read_uploaded_audio(self) -> tuple[bytes, str, str] | None:
        """Return (bytes, filename, mime) from multipart or raw audio body."""
        content_type = self.headers.get("Content-Type", "") or ""
        length = int(self.headers.get("Content-Length", 0))
        if "multipart/form-data" in content_type:
            environ = {
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": str(length),
            }
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=environ)
            item = form["audio"] if "audio" in form else form["file"] if "file" in form else None
            if item is None or not getattr(item, "file", None):
                self._send_json(400, {"error": "Expected multipart field 'audio' or 'file'"})
                return None
            data = item.file.read()
            filename = getattr(item, "filename", None) or "recording.webm"
            mime = getattr(item, "type", None) or "audio/webm"
            return data, filename, mime

        mime = content_type.split(";", 1)[0].strip().lower()
        if mime.startswith("audio/") or mime == "application/octet-stream":
            data = self.rfile.read(length) if length else b""
            ext = ".webm" if "webm" in mime else ".wav" if "wav" in mime else ".mp3"
            return data, f"recording{ext}", mime or "audio/webm"

        self._send_json(400, {"error": "Send audio as multipart/form-data (audio) or audio/* body"})
        return None

    def _read_json_body(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return None

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = unquote(self.path.split("?", 1)[0])
        if path in {"/api/live-session", "/live-session.json"}:
            self._send_json(200, _LiveSessionHandler.payload)
            return
        if path == "/api/sessions":
            self._send_json(200, {"sessions": list_session_rows()})
            return
        if path.startswith("/api/sessions/"):
            rest = path.split("/api/sessions/", 1)[1].strip("/")
            parts = [p for p in rest.split("/") if p]
            if not parts or parts[0] == "generate":
                self._send_json(404, {"error": "Not found"})
                return
            session_id = parts[0]
            if len(parts) >= 2 and parts[1] == "status":
                job = _session_jobs.get(session_id)
                if job:
                    self._send_json(200, job)
                    return
                if load_session(session_id):
                    self._send_json(200, {"status": "complete", "sessionId": session_id})
                    return
                self._send_json(404, {"error": "Unknown session", "sessionId": session_id})
                return
            data = load_session(session_id)
            if not data:
                self._send_json(404, {"error": "Session not found"})
                return
            self._send_json(200, {"session": data})
            return
        if path in {"/", "/dashboard", "/fallback-dashboard.html"}:
            html_path = FALLBACK_HTML if FALLBACK_HTML.is_file() else None
            if html_path:
                self._send_bytes(200, html_path.read_bytes(), "text/html; charset=utf-8")
                return
        self.send_error(404)

    def do_POST(self) -> None:
        path = unquote(self.path.split("?", 1)[0])
        if path == "/api/live-session":
            body = self._read_json_body()
            if body is None:
                return
            _LiveSessionHandler.payload = body
            self._send_json(200, {"ok": True})
            return

        if path == "/api/transcribe":
            uploaded = self._read_uploaded_audio()
            if uploaded is None:
                return
            audio_bytes, filename, mime = uploaded
            try:
                result = transcribe_audio(audio_bytes, filename=filename, mime=mime)
            except Exception as exc:
                print(f"[trustnote] Transcription failed: {exc}", file=sys.stderr)
                self._send_json(500, {"error": str(exc)})
                return
            self._send_json(200, {"ok": True, **result})
            return

        if path == "/api/sessions/generate":
            body = self._read_json_body()
            if body is None:
                return
            transcript = (body.get("transcript") or "").strip()
            if not transcript:
                self._send_json(400, {"error": "transcript is required"})
                return

            session_id = new_session_id()
            patient_name = (body.get("patientName") or "Patient").strip()
            doctor_name = (body.get("doctorName") or "Dr. Clinician").strip()
            if doctor_name and not doctor_name.lower().startswith("dr"):
                doctor_name = f"Dr. {doctor_name}"

            meta = {
                "sessionId": session_id,
                "patientName": patient_name,
                "patientId": body.get("patientId") or f"p-{session_id[-4:]}",
                "mrn": body.get("mrn") or f"TN-{session_id[-6:].upper()}",
                "age": body.get("age"),
                "sex": body.get("sex"),
                "doctorName": doctor_name,
                "specialty": body.get("specialty") or "General practice",
                "consultationType": (body.get("consultationType") or "Web consultation").strip(),
            }

            options = _pipeline_options_or_default()
            _session_jobs[session_id] = {"status": "processing", "sessionId": session_id}
            worker = threading.Thread(
                target=_run_web_session_job,
                args=(session_id, transcript, meta, options),
                daemon=True,
            )
            worker.start()
            self._send_json(
                202,
                {
                    "ok": True,
                    "sessionId": session_id,
                    "status": "processing",
                    "message": "Generation started. Watch the terminal for progress.",
                },
            )
            return

        self.send_error(404)


def start_live_session_api(port: int = DEFAULT_API_PORT) -> str:
    global _api_server
    base = f"http://127.0.0.1:{port}/"
    if _api_server is not None:
        return base
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), _LiveSessionHandler)
    except OSError as exc:
        print(f"[trustnote] Could not start API on port {port}: {exc}", file=sys.stderr)
        return base
    _api_server = server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    atexit.register(stop_live_session_api)
    print(f"[trustnote] Live session API: http://127.0.0.1:{port}/live-session.json", flush=True)
    return base


def stop_live_session_api() -> None:
    global _api_server
    if _api_server:
        _api_server.shutdown()
        _api_server = None


def publish_live_session(payload: dict[str, Any], *, status: str = "ready") -> None:
    """Write session JSON for the Next.js app and in-memory API."""
    envelope: dict[str, Any] = {
        "status": status,
        "updatedAt": time.time(),
        "session": payload,
    }
    LIVE_SESSION_DATA.parent.mkdir(parents=True, exist_ok=True)
    LIVE_SESSION_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(envelope, indent=2, ensure_ascii=False)
    LIVE_SESSION_DATA.write_text(text, encoding="utf-8")
    LIVE_SESSION_PUBLIC.write_text(text, encoding="utf-8")
    _LiveSessionHandler.payload = envelope


def publish_waiting_message() -> None:
    envelope = {
        "status": "waiting",
        "updatedAt": time.time(),
        "message": "Paste your conversation in the terminal, then type END.",
        "session": None,
    }
    text = json.dumps(envelope, indent=2, ensure_ascii=False)
    LIVE_SESSION_DATA.parent.mkdir(parents=True, exist_ok=True)
    LIVE_SESSION_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    LIVE_SESSION_DATA.write_text(text, encoding="utf-8")
    LIVE_SESSION_PUBLIC.write_text(text, encoding="utf-8")
    _LiveSessionHandler.payload = envelope


def bootstrap_interactive_ui() -> str:
    """Call once at the start of interactive main.py."""
    start_live_session_api()
    publish_waiting_message()
    return start_frontend_dev(open_browser=True)


def dashboard_url() -> str:
    return _ui_base_url or f"http://127.0.0.1:{DEFAULT_NEXT_PORT}"
