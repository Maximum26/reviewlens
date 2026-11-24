import json
import os

import anthropic
from dotenv import load_dotenv

from reviewlens import cache

load_dotenv()

_MODEL = os.getenv("LLM_MODEL", "claude-haiku-5-5")
_MAX_TOKENS = 1024
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY не задано (перевір .env)")
        # SDK сам робить retry на 429/5xx
        _client = anthropic.Anthropic(timeout=30, max_retries=3)
    return _client


def call_llm(system: str, user: str) -> str:
    """Викликає модель. JSON просимо в system-промпті. Спочатку перевіряє кеш."""
    full_system = system + "\n\nВідповідай ЛИШЕ валідним JSON, без пояснень і markdown."
    key = cache.make_key(_MODEL, full_system, user, _MAX_TOKENS)
    cached = cache.get(key)
    if cached is not None:
        return cached

    response = _get_client().messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=full_system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    # Порожні відповіді в кеш не пишемо, інакше помилка закріпиться назавжди.
    if text.strip():
        cache.put(key, text)
    return text


def parse_json(raw: str) -> dict:
    """Дістає JSON між першою { і останньою }."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise json.JSONDecodeError("JSON не знайдено", raw, 0)
    return json.loads(raw[start : end + 1])
