"""Speech-to-text for web session capture (Groq Whisper API or local faster-whisper)."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
import urllib.error
import urllib.request
from pathlib import Path

from config import CONFIG

GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_WHISPER = "whisper-large-v3"


def _groq_api_key() -> str:
    return (CONFIG.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")).strip()


def _multipart_body(
    fields: dict[str, str],
    file_field: str,
    filename: str,
    file_bytes: bytes,
    mime: str,
) -> tuple[bytes, str]:
    boundary = f"TrustNote{uuid.uuid4().hex}"
    crlf = b"\r\n"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}".encode())
        chunks.append(crlf)
        chunks.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        chunks.append(crlf + crlf)
        chunks.append(value.encode("utf-8"))
        chunks.append(crlf)
    chunks.append(f"--{boundary}".encode())
    chunks.append(crlf)
    chunks.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode()
    )
    chunks.append(crlf)
    chunks.append(f"Content-Type: {mime}".encode())
    chunks.append(crlf + crlf)
    chunks.append(file_bytes)
    chunks.append(crlf)
    chunks.append(f"--{boundary}--".encode())
    chunks.append(crlf)
    return b"".join(chunks), boundary


def transcribe_with_groq(
    audio_bytes: bytes,
    *,
    filename: str = "recording.webm",
    mime: str = "audio/webm",
    language: str = "en",
) -> str:
    key = _groq_api_key()
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to `.env` for Whisper transcription, "
            "or set TRUSTNOTE_TRANSCRIBE_BACKEND=local and install faster-whisper."
        )
    model = os.getenv("GROQ_WHISPER_MODEL", DEFAULT_GROQ_WHISPER)
    fields = {
        "model": model,
        "response_format": "json",
        "language": language,
        "temperature": "0",
        "prompt": "Doctor and patient medical consultation. Speaker turns may include clinical symptoms and plans.",
    }
    body, boundary = _multipart_body(fields, "file", filename, audio_bytes, mime)
    req = urllib.request.Request(
        GROQ_TRANSCRIBE_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "TrustNote/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        detail = "Transcription failed."
        try:
            detail = str(json.loads(e.read().decode()).get("error", {}).get("message", detail))
        except (ValueError, UnicodeError, json.JSONDecodeError):
            pass
        raise RuntimeError(f"Groq Whisper HTTP {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Could not reach Groq for transcription: {e}") from e

    text = (payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("Whisper returned empty text. Try speaking closer to the mic or use a longer recording.")
    return text


def transcribe_with_faster_whisper(audio_bytes: bytes, *, suffix: str = ".webm") -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            "Local Whisper is not installed. Run: pip install faster-whisper "
            "or use Groq (default) with GROQ_API_KEY in `.env`."
        ) from None

    model_size = os.getenv("TRUSTNOTE_WHISPER_LOCAL_MODEL", "base")
    device = os.getenv("TRUSTNOTE_WHISPER_DEVICE", "cpu")
    compute = os.getenv("TRUSTNOTE_WHISPER_COMPUTE", "int8")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        path = tmp.name

    try:
        model = WhisperModel(model_size, device=device, compute_type=compute)
        segments, _ = model.transcribe(path, language="en", vad_filter=True)
        text = " ".join(s.text.strip() for s in segments if s.text.strip())
    finally:
        Path(path).unlink(missing_ok=True)

    if not text:
        raise RuntimeError("Local Whisper returned empty text.")
    return text


def transcribe_audio(
    audio_bytes: bytes,
    *,
    filename: str = "recording.webm",
    mime: str = "audio/webm",
) -> dict[str, str]:
    if not audio_bytes:
        raise ValueError("No audio received.")
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise ValueError("Recording is too large (max 25 MB). Stop and start a shorter clip.")

    backend = os.getenv("TRUSTNOTE_TRANSCRIBE_BACKEND", "groq").strip().lower()
    print(f"[trustnote] Transcribing {len(audio_bytes):,} bytes via {backend}…", flush=True)

    if backend == "local":
        suffix = Path(filename).suffix or ".webm"
        text = transcribe_with_faster_whisper(audio_bytes, suffix=suffix)
        engine = f"faster-whisper ({os.getenv('TRUSTNOTE_WHISPER_LOCAL_MODEL', 'base')})"
    else:
        text = transcribe_with_groq(audio_bytes, filename=filename, mime=mime)
        engine = os.getenv("GROQ_WHISPER_MODEL", DEFAULT_GROQ_WHISPER)

    print(f"[trustnote] Transcription complete ({len(text):,} characters).", flush=True)
    return {"text": text, "engine": engine}
