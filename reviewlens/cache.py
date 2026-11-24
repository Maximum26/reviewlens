import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


def make_key(model: str, system: str, user: str, max_tokens: int) -> str:
    """sha256 від (model, system, user, max_tokens). json.dumps не дає склеїтися різним полям."""
    raw = json.dumps([model, system, user, max_tokens], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get(key: str) -> str | None:
    """Повертає закешовану відповідь або None, якщо запису немає чи він пошкоджений."""
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))["response"]
    except (OSError, ValueError, KeyError):
        # Пошкоджений файл вважаємо промахом, він перезапишеться після виклику API.
        return None


def put(key: str, response: str) -> None:
    """Зберігає відповідь LLM у файл кешу."""
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps({"response": response}, ensure_ascii=False), encoding="utf-8")
