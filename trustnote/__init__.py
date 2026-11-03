__version__ = "0.1.0"

from pathlib import Path

try:
    from dotenv import load_dotenv

    _env = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env, override=False)
except ImportError:
    pass
