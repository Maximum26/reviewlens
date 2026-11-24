import json
import re

from pydantic import ValidationError

from reviewlens.llm import call_llm, parse_json
from reviewlens.prompts import ROUTER_SYSTEM
from reviewlens.schemas import RouteDecision

# Основи шукаються від початку слова, щоб покрити відмінки (отруїли, поліцію, лікарні).
# "суд" лише в точних формах, щоб не спрацьовувало на "судно" і "суддя".
ESCALATE_PATTERN = re.compile(
    r"\b(?:адвокат|отру|поліці|лікарн)|\bсуд(?:у|і|ом|ові)?\b"
)


def keyword_escalation(review: str) -> bool:
    """True, якщо в тексті є ключове слово для ескалації. Без LLM."""
    return ESCALATE_PATTERN.search(review.lower()) is not None


def route_review(review: str) -> RouteDecision:
    """Спершу LLM, потім страховка по ключових словах, яка має останнє слово."""
    try:
        decision = RouteDecision(**parse_json(call_llm(ROUTER_SYSTEM, review)))
    except (json.JSONDecodeError, ValidationError) as e:
        decision = RouteDecision(route="full", reason=f"Збій роутера, відгук іде в повний пайплайн: {e}")

    if keyword_escalation(review):
        return RouteDecision(
            route="escalate",
            reason=f"Спрацювала страховка за ключовим словом. Рішення роутера: {decision.route} ({decision.reason})",
        )
    return decision
