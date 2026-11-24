import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from reviewlens.extractor import check_quotes, normalize
from reviewlens.router import keyword_escalation, route_review
from reviewlens.schemas import AspectItem, Critique, Extraction, Reply, RouteDecision

REVIEW = "Смачна їжа, але чекали годину. Персонал хамить!"


# --- normalize ---

def test_normalize_case_punctuation_and_spaces():
    assert normalize("  Смачна,   ЇЖА!  ") == "смачна їжа"


def test_normalize_only_punctuation_becomes_empty():
    assert normalize("!!! ...") == ""


# --- check_quotes ---

def _extraction(*quotes):
    return Extraction(
        aspects=[AspectItem(aspect="food", sentiment="positive", quote=q) for q in quotes],
        urgency="low", language="uk", needs_human=False,
    )


def test_check_quotes_accepts_different_case_and_spacing():
    check_quotes(_extraction("СМАЧНА   їжа"), REVIEW)  # не кидає


def test_check_quotes_accepts_quote_with_punctuation_difference():
    check_quotes(_extraction("чекали годину"), REVIEW)


def test_check_quotes_rejects_fabricated_quote():
    with pytest.raises(ValueError, match="відсутня в тексті"):
        check_quotes(_extraction("вигадана цитата"), REVIEW)


def test_check_quotes_rejects_quote_empty_after_normalize():
    with pytest.raises(ValueError, match="порожня після нормалізації"):
        check_quotes(_extraction("!!!"), REVIEW)


def test_check_quotes_empty_aspects_is_valid():
    # відгук без змісту («ну таке») має давати порожній список аспектів
    check_quotes(Extraction(aspects=[], urgency="low", language="uk", needs_human=False), REVIEW)


# --- схеми ---

def test_aspect_quote_shorter_than_three_chars_rejected():
    with pytest.raises(ValidationError):
        AspectItem(aspect="food", sentiment="positive", quote="ок")


def test_aspect_outside_enum_rejected():
    with pytest.raises(ValidationError):
        AspectItem(aspect="interior", sentiment="positive", quote="Смачна їжа")


def test_sentiment_outside_enum_rejected():
    with pytest.raises(ValidationError):
        AspectItem(aspect="food", sentiment="great", quote="Смачна їжа")


def test_extraction_urgency_outside_enum_rejected():
    with pytest.raises(ValidationError):
        Extraction(aspects=[], urgency="critical", language="uk", needs_human=False)


def test_route_outside_enum_rejected():
    with pytest.raises(ValidationError):
        RouteDecision(route="ignore", reason="x")


def test_reply_shorter_than_ten_chars_rejected():
    with pytest.raises(ValidationError):
        Reply(reply="Дякуємо")


def test_critique_requires_issues_list():
    with pytest.raises(ValidationError):
        Critique(ok=False)


# --- keyword-страховка роутера ---

@pytest.mark.parametrize("text", [
    "Буду звертатись до суду",
    "Викличу адвоката",
    "Нас отруїли вашою піцою",
    "Викликали поліцію",
    "Ми провели ніч у лікарні",
])
def test_keyword_escalation_matches_inflected_forms(text):
    assert keyword_escalation(text)


@pytest.mark.parametrize("text", [
    "Принесли судно з супом",   # "судно" не суд
    "Суддя з сусіднього столика",
    "Смачна кава і гарний сервіс",
])
def test_keyword_escalation_ignores_false_friends(text):
    assert not keyword_escalation(text)


def test_keyword_overrides_llm_full_route():
    llm_answer = json.dumps({"route": "full", "reason": "звичайна скарга"}, ensure_ascii=False)
    with patch("reviewlens.router.call_llm", return_value=llm_answer):
        decision = route_review("Після вашого салату мене забрала швидка, буду звертатись до суду")
    assert decision.route == "escalate"
    assert "страховка" in decision.reason


def test_keyword_overrides_llm_spam_route():
    llm_answer = json.dumps({"route": "spam", "reason": "реклама"}, ensure_ascii=False)
    with patch("reviewlens.router.call_llm", return_value=llm_answer):
        decision = route_review("Викличу адвоката, ви мене отруїли")
    assert decision.route == "escalate"


def test_llm_route_kept_without_keywords():
    llm_answer = json.dumps({"route": "positive", "reason": "лише похвала"}, ensure_ascii=False)
    with patch("reviewlens.router.call_llm", return_value=llm_answer):
        decision = route_review("Дякую, все було чудово!")
    assert decision.route == "positive"


def test_broken_router_json_falls_back_to_full():
    with patch("reviewlens.router.call_llm", return_value="не JSON"):
        decision = route_review("Смачна їжа, але довго чекали")
    assert decision.route == "full"
    assert "Збій роутера" in decision.reason
