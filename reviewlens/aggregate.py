from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # уникаємо імпорту pipeline (а з ним llm/anthropic) під час тестів
    from reviewlens.pipeline import Result

SENTIMENTS = ("positive", "negative", "neutral")
TOP_PROBLEMS = 3
QUOTES_PER_PROBLEM = 3

# extractor.py на кожній невдалій спробі пише logs.append(f"Спроба {attempt}: {error}").
# Рядок з таким префіксом у logs означає, що екстрактор ретраївся.
# MULTILINE потрібен, бо при ExtractionFailed усі рядки логу склеєні в один str.
_EXTRACT_RETRY_LINE = re.compile(r"^Спроба \d+: ", re.MULTILINE)


def result_to_dict(result: Result) -> dict[str, Any]:
    """Result -> JSON-сумісний dict. Pydantic-об'єкт перетворюємо через model_dump."""
    ext = result.extraction
    return {
        "route": result.route,
        "extraction": ext.model_dump() if ext is not None else None,
        "reply": result.reply,
        "iterations": result.iterations,
        "logs": list(result.logs),
        "needs_human": result.needs_human,
    }


def _has_extract_retry(logs: list[str]) -> bool:
    """True, якщо в логах є слід ретраю екстрактора."""
    return any(_EXTRACT_RETRY_LINE.search(line) for line in logs)


def aggregate(rows: list[tuple[Any, str, dict[str, Any]]]) -> dict[str, Any]:
    """rows: список (id, text, result_dict), де result_dict з result_to_dict()."""
    routes: Counter[str] = Counter()
    aspect_counts: dict[str, dict[str, int]] = {}
    negative_quotes: dict[str, list[str]] = {}
    needs_human_count = 0
    retry_count = 0
    out_rows: list[dict[str, Any]] = []

    for rid, text, res in rows:
        routes[res["route"]] += 1

        ext = res.get("extraction") or {}
        aspects = list(ext.get("aspects", []))
        for a in aspects:
            name, sentiment, quote = a["aspect"], a["sentiment"], a["quote"]
            counts = aspect_counts.setdefault(name, {s: 0 for s in SENTIMENTS})
            counts[sentiment] += 1
            if sentiment == "negative":
                quotes = negative_quotes.setdefault(name, [])
                if quote not in quotes:
                    quotes.append(quote)

        if res["needs_human"]:
            needs_human_count += 1
        if _has_extract_retry(res["logs"]):
            retry_count += 1

        out_rows.append({
            "id": rid,
            "text": text,
            "route": res["route"],
            "aspects": aspects,
            "reply": res["reply"],
            "iterations": res["iterations"],
            "needs_human": res["needs_human"],
            "logs": res["logs"],
        })

    # Топ за кількістю негативів; при однаковій кількості сортуємо за назвою аспекту.
    negatives = [
        (name, counts["negative"])
        for name, counts in aspect_counts.items()
        if counts["negative"] > 0
    ]
    negatives.sort(key=lambda item: (-item[1], item[0]))
    top_problems = [
        {
            "aspect": name,
            "negative_count": n,
            "quotes": negative_quotes[name][:QUOTES_PER_PROBLEM],
        }
        for name, n in negatives[:TOP_PROBLEMS]
    ]

    return {
        "routes": dict(routes),
        "aspects": aspect_counts,
        "top_problems": top_problems,
        "needs_human_count": needs_human_count,
        "retry_count": retry_count,
        "rows": out_rows,
    }
