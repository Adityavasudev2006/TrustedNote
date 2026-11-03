"""
Member 1's module: Conversation -> Clinical Note.

Fixed interface (per the project plan):
    generate_note(transcript: str) -> str

Keeping the LLM behind a small Backend interface means Member 2 and Member 3
never need to care whether generation is happening via the Anthropic API or a
local HF model — they just call generate_note().
"""
from __future__ import annotations

import abc
import json
import re
import time
import urllib.error
import urllib.request

from config import CONFIG, ENV_FILE

# Groq retired several Meta models for developer/free accounts (see console.groq.com/docs/deprecations).
GROQ_MODEL_REPLACEMENTS = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
    "llama-3.1-70b-versatile": "openai/gpt-oss-120b",
}

SOAP_PROMPT_TEMPLATE = """You are a clinical scribe. Read the following doctor-patient \
conversation transcript and write a structured SOAP note.

Rules:
- Only include information that is stated or clearly implied in the transcript.
- Do not invent vital signs, dates, dosages, or diagnoses that are not mentioned.
- Use standard SOAP sections: Subjective, Objective, Assessment, Plan.
- Be concise and use clinical language.

Transcript:
\"\"\"
{transcript}
\"\"\"

Write only the SOAP note using exactly these four section headers, each on its own line
followed by a colon, then the section content on the following lines:

Subjective:
Objective:
Assessment:
Plan:

Use bullet-style lines (one clinical fact per line) under each section when helpful.
Leave a section empty except for the header if nothing belongs there.
"""


class LLMBackend(abc.ABC):
    """Minimal interface every generation backend must implement."""

    @abc.abstractmethod
    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        ...


class AnthropicBackend(LLMBackend):
    """Baseline / fast-to-set-up backend using the Claude API."""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        import anthropic  # pip install anthropic

        self.model = model or CONFIG.ANTHROPIC_MODEL
        self.client = anthropic.Anthropic(api_key=api_key or CONFIG.ANTHROPIC_API_KEY)

    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in resp.content if block.type == "text").strip()


class LocalHFBackend(LLMBackend):
    """
    Runs a local instruct model, matching the "Local LLM" box in the
    architecture diagram. Loaded lazily so importing this module doesn't
    require a GPU / the model weights unless you actually use this backend.
    """

    def __init__(self, model_name: str | None = None):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        self.model_name = model_name or CONFIG.LOCAL_HF_MODEL
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
        )

    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        import torch

        messages = [{"role": "user", "content": prompt}]
        inputs = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        )
        if torch.cuda.is_available():
            inputs = inputs.to(self.model.device)
        output = self.model.generate(
            inputs,
            max_new_tokens=max_tokens,
            do_sample=temperature > 0,
            temperature=max(temperature, 1e-4),
            pad_token_id=self.tokenizer.eos_token_id,
        )
        new_tokens = output[0][inputs.shape[-1]:]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


class GroqBackend(LLMBackend):
    """Groq OpenAI-compatible chat API; API key is read from the project `.env` file."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        request_interval: float | None = None,
    ):
        self.api_key = (api_key or CONFIG.GROQ_API_KEY).strip()
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY is missing. Paste your key into the `.env` file in the project root."
            )
        self.model = model or CONFIG.GROQ_MODEL
        replacement = GROQ_MODEL_REPLACEMENTS.get(self.model)
        if replacement:
            import sys

            print(
                f"[trustnote] Groq model '{self.model}' is no longer available on your plan. "
                f"Using '{replacement}' instead. Update GROQ_MODEL in {ENV_FILE} to silence this.",
                file=sys.stderr,
            )
            self.model = replacement
        self.interval = (
            CONFIG.GROQ_REQUEST_INTERVAL if request_interval is None else request_interval
        )
        self._last_request: float | None = None

    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        payload = {
            "model": self.model,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "TrustNote/0.1",
            },
        )
        if self._last_request is not None and self.interval > 0:
            wait = self.interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
        self._last_request = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                result = json.load(response)
        except urllib.error.HTTPError as e:
            detail = "Groq request failed."
            try:
                detail = str(json.loads(e.read().decode()).get("error", {}).get("message", detail))
            except (ValueError, UnicodeError):
                pass
            detail = detail.replace(self.api_key, "[REDACTED]")[:800]
            if e.code == 404:
                detail += (
                    f" Set GROQ_MODEL in {ENV_FILE} to a model your key can access "
                    "(e.g. openai/gpt-oss-20b or openai/gpt-oss-120b). "
                    "List models: GET https://api.groq.com/openai/v1/models"
                )
            raise RuntimeError(f"Groq HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise RuntimeError(f"Groq connection failed: {e}") from e

        choices = result.get("choices") or []
        if not choices:
            raise RuntimeError("Groq returned no choices.")
        message = choices[0].get("message") or {}
        text = (message.get("content") or "").strip()
        if not text:
            raise RuntimeError("Groq returned empty text.")
        return text


class MockBackend(LLMBackend):
    """
    No API key, no GPU, no internet: deterministic stand-in used for unit
    tests and for sanity-checking the pipeline wiring end to end.
    """

    def complete(self, prompt: str, max_tokens: int, temperature: float) -> str:
        transcript = prompt.split('"""')[1].strip() if '"""' in prompt else prompt
        sentences = re.split(r"(?<=[.!?])\s+", transcript.strip())
        subjective = " ".join(s for s in sentences if any(
            k in s.lower() for k in ["feel", "pain", "since", "started", "i "]
        ))[:400]
        return (
            "Subjective:\n"
            + (subjective or "Patient-reported symptoms per transcript.")
            + "\n\nObjective:\nNot explicitly stated in transcript.\n\n"
            + "Assessment:\nBased on reported symptoms.\n\n"
            + "Plan:\nFollow up as clinically indicated."
        )


_BACKEND_REGISTRY = {
    "groq": GroqBackend,
    "anthropic": AnthropicBackend,
    "local_hf": LocalHFBackend,
    "mock": MockBackend,
}


def get_backend(name: str | None = None) -> LLMBackend:
    name = name or CONFIG.GEN_BACKEND
    if name not in _BACKEND_REGISTRY:
        raise ValueError(f"Unknown backend '{name}'. Options: {list(_BACKEND_REGISTRY)}")
    return _BACKEND_REGISTRY[name]()


def generate_note(transcript: str, backend: LLMBackend | None = None) -> str:
    """
    Fixed interface: transcript -> clinical note (str).
    Pass an explicit `backend` to reuse one instance across many calls
    (avoids reloading a local model per example).
    """
    backend = backend or get_backend()
    prompt = SOAP_PROMPT_TEMPLATE.format(transcript=transcript.strip())
    return backend.complete(
        prompt, max_tokens=CONFIG.GEN_MAX_NEW_TOKENS, temperature=CONFIG.GEN_TEMPERATURE
    )
