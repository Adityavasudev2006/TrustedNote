"""
TrustNote configuration.

Everything here is overridable via environment variables (see .env.example).
Keeping config in one place means Member 1/2/3 can each swap models without
touching pipeline code.
"""
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_project_env() -> None:
    """Load secrets and defaults from the project `.env` file (if present)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ENV_FILE, override=False)
    # Also allow a cwd `.env` when running from another directory.
    load_dotenv(override=False)


load_project_env()


@dataclass
class Config:
    # --- Generation backend ---
    # "groq"       -> Groq API (key in project `.env` as GROQ_API_KEY)
    # "anthropic"  -> calls the Claude API (fast to get working, good for a baseline)
    # "local_hf"   -> runs a local HuggingFace instruct model (matches the "Local LLM" box
    #                 in the architecture diagram; needs a GPU or a small model for CPU)
    GEN_BACKEND: str = os.getenv("TRUSTNOTE_GEN_BACKEND", "groq")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    GROQ_REQUEST_INTERVAL: float = float(os.getenv("GROQ_REQUEST_INTERVAL", "15"))
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    LOCAL_HF_MODEL: str = os.getenv(
        "TRUSTNOTE_LOCAL_MODEL", "microsoft/Phi-3-mini-4k-instruct"
    )
    GEN_MAX_NEW_TOKENS: int = int(os.getenv("TRUSTNOTE_GEN_MAX_TOKENS", "800"))
    GEN_TEMPERATURE: float = float(os.getenv("TRUSTNOTE_GEN_TEMPERATURE", "0.2"))

    # --- Claim extraction ---
    # "llm"  -> FActScore-style LLM decomposition into atomic claims (better quality)
    # "rule" -> offline sentence-splitter fallback (no API/model needed, useful for quick tests)
    CLAIM_EXTRACTION_MODE: str = os.getenv("TRUSTNOTE_CLAIM_MODE", "llm")

    # --- Evidence retrieval ---
    EMBEDDING_MODEL: str = os.getenv(
        "TRUSTNOTE_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    TOP_K_EVIDENCE: int = int(os.getenv("TRUSTNOTE_TOP_K", "3"))

    # --- Verification ---
    # "nli" -> local entailment model (fast, no API cost, inspired by AlignScore's
    #          "unified alignment function" idea but implemented with an off-the-shelf
    #          NLI checkpoint since we don't have AlignScore's trained weights)
    # "llm" -> Claude-as-judge verification (slower/costlier, often more clinically aware,
    #          inspired by VERISCORE's verify stage)
    VERIFY_MODE: str = os.getenv("TRUSTNOTE_VERIFY_MODE", "nli")
    NLI_MODEL: str = os.getenv(
        "TRUSTNOTE_NLI_MODEL", "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
    )
    # Entailment prob >= this  -> Supported
    NLI_ENTAIL_THRESHOLD: float = float(os.getenv("TRUSTNOTE_ENTAIL_THRESH", "0.55"))
    # Contradiction prob >= this -> Contradicted (checked before entailment)
    NLI_CONTRADICT_THRESHOLD: float = float(os.getenv("TRUSTNOTE_CONTRADICT_THRESH", "0.55"))
    # Anything else -> Unverifiable

    # --- Data ---
    DATA_DIR: str = os.getenv("TRUSTNOTE_DATA_DIR", "./data/aci-bench")

    # --- Misc ---
    RANDOM_SEED: int = int(os.getenv("TRUSTNOTE_SEED", "42"))


CONFIG = Config()
