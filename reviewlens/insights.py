from __future__ import annotations

import json
import logging
from typing import Any

from reviewlens.llm import call_llm, parse_json
from reviewlens.prompts import INSIGHTS_SYSTEM
from reviewlens.schemas import Insights

logger = logging.getLogger(__name__)

NO_PROBLEMS_TEXT = "Проблем не знайдено."
UNAVAILABLE_TEXT = "Інсайти недоступні"


def make_insights(agg: dict[str, Any]) -> Insights:
    """Модель бачить лише routes і top_problems (аспекти, лічильники, цитати), не весь CSV."""
    top = agg.get("top_problems") or []
    if not top:
        return Insights(summary=NO_PROBLEMS_TEXT)

    payload = {"routes": agg.get("routes", {}), "top_problems": top}
    user = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        return Insights(**parse_json(call_llm(INSIGHTS_SYSTEM, user)))
    except Exception:
        # Збій мережі, ключа, JSON чи валідації не повинен валити дашборд.
        logger.exception("Не вдалося згенерувати інсайти")
        return Insights(summary=UNAVAILABLE_TEXT)
