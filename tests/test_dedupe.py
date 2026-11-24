import json
from unittest.mock import patch

from reviewlens import extractor
from reviewlens.schemas import AspectItem, Extraction

REVIEW = "Смачна їжа, але їжа холодна. Персонал добрий."


def _ext(*items):
    return Extraction(
        aspects=[AspectItem(aspect=a, sentiment=s, quote=q) for a, s, q in items],
        urgency="low", language="uk", needs_human=False,
    )


def test_merge_keeps_first_quote_and_one_pair():
    data = _ext(("food", "positive", "Смачна їжа"), ("food", "positive", "їжа холодна"))
    merged, n = extractor.merge_duplicates(data)
    assert n == 1
    assert [(a.aspect, a.sentiment, a.quote) for a in merged.aspects] == [
        ("food", "positive", "Смачна їжа"),
    ]


def test_merge_keeps_different_sentiments_of_same_aspect():
    # id 13 з gold: food negative і food positive в одному відгуку - це дві різні пари
    data = _ext(("food", "negative", "їжа холодна"), ("food", "positive", "Смачна їжа"))
    merged, n = extractor.merge_duplicates(data)
    assert n == 0
    assert len(merged.aspects) == 2


def test_merge_only_exact_duplicates_among_mixed():
    data = _ext(
        ("food", "positive", "Смачна їжа"),
        ("food", "negative", "їжа холодна"),
        ("food", "positive", "Смачна їжа"),
        ("service", "positive", "Персонал добрий"),
    )
    merged, n = extractor.merge_duplicates(data)
    assert n == 1
    assert [(a.aspect, a.sentiment) for a in merged.aspects] == [
        ("food", "positive"), ("food", "negative"), ("service", "positive"),
    ]


def test_extract_returns_deduplicated_aspects_and_logs_merge():
    raw = json.dumps({
        "aspects": [
            {"aspect": "food", "sentiment": "positive", "quote": "Смачна їжа"},
            {"aspect": "food", "sentiment": "positive", "quote": "їжа"},
            {"aspect": "service", "sentiment": "positive", "quote": "Персонал добрий"},
        ],
        "urgency": "low", "language": "uk", "needs_human": False,
    }, ensure_ascii=False)
    with patch("reviewlens.extractor.call_llm", return_value=raw):
        data, logs = extractor.extract(REVIEW)
    assert [(a.aspect, a.sentiment) for a in data.aspects] == [
        ("food", "positive"), ("service", "positive"),
    ]
    assert data.aspects[0].quote == "Смачна їжа"
    assert "Склеєно повторні пари аспект+тональність: 1" in logs
