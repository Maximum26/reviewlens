import json
import re

from pydantic import ValidationError

from reviewlens.llm import call_llm, parse_json
from reviewlens.prompts import EXTRACT_SYSTEM, build_extract_user
from reviewlens.schemas import Extraction

MAX_ATTEMPTS = 3


class ExtractionFailed(Exception):
    """Усі спроби витягнути валідний результат невдалі."""


def normalize(text: str) -> str:
    """Нижній регістр, без розділових знаків, стиснуті пробіли."""
    text = re.sub(r"[^\w\s]", "", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def check_quotes(data: Extraction, review: str) -> None:
    """Кидає ValueError, якщо цитата з аспекту не знайдена в оригінальному відгуку."""
    norm_review = normalize(review)
    for a in data.aspects:
        quote = normalize(a.quote)
        if not quote:
            raise ValueError(f"Цитата '{a.quote}' порожня після нормалізації")
        if quote not in norm_review:
            raise ValueError(f"Цитата '{a.quote}' відсутня в тексті")


def extract(review: str) -> tuple[Extraction, list[str]]:
    """Повертає результат і логи: що було не так на кожній невдалій спробі."""
    logs: list[str] = []
    error: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = call_llm(EXTRACT_SYSTEM, build_extract_user(review, error))
        try:
            data = Extraction(**parse_json(raw))
            check_quotes(data, review)
            return data, logs
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            error = str(e)
            logs.append(f"Спроба {attempt}: {error}")
    raise ExtractionFailed(
        f"Не вдалося витягнути валідний результат за {MAX_ATTEMPTS} спроби.\n" + "\n".join(logs)
    )
