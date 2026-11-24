import argparse
import datetime
import json
import re
import sys
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reviewlens import cache  # noqa: E402
from reviewlens.llm import _MODEL  # noqa: E402
from reviewlens.pipeline import Result, process  # noqa: E402
from reviewlens.prompts import (  # noqa: E402
    CRITIC_SYSTEM,
    EXTRACT_SYSTEM,
    REWRITE_SYSTEM,
    ROUTER_SYSTEM,
    THANK_SYSTEM,
    WRITER_SYSTEM,
)

GOLD_PATH = ROOT / "data" / "gold.json"
DEFAULT_OUT = ROOT / "eval" / "results.md"

# Журнал extractor: рядки виду "Спроба 2: <помилка>" (див. extractor.extract).
_ATTEMPT_RE = re.compile(r"^Спроба (\d+): (.*)$", re.M)


@dataclass
class Metrics:
    router_ok: int = 0
    router_total: int = 0
    tp: int = 0             # пари (аспект, тональність) збіглися з gold
    pred_pairs: int = 0     # усіх пар у прогнозі, немспам-відгуки
    gold_pairs: int = 0     # усіх пар у gold, немспам-відгуки
    sent_wrong: int = 0     # аспект знайдено за назвою, тональність не збіглася
    attempted: int = 0      # відгуки, що дійшли до extractor
    retried: int = 0        # з них із хоча б однією невдалою спробою
    quote_first_ok: int = 0  # з них перша спроба без помилки цитати
    drafts: int = 0         # чернетки (маршрут full з відповіддю)
    rejected: int = 0       # чернетки, відхилені критиком хоча б раз

    @property
    def precision(self):
        return _ratio(self.tp, self.pred_pairs)

    @property
    def recall(self):
        return _ratio(self.tp, self.gold_pairs)

    @property
    def sentiment(self):
        return _ratio(self.tp, self.tp + self.sent_wrong)


@dataclass
class ErrorRow:
    id: int
    expected: str
    got: str
    kind: str


@dataclass
class Report:
    metrics: Metrics
    errors: list[ErrorRow] = field(default_factory=list)


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def _fmt_pct(a: int, b: int) -> str:
    if not b:
        return "—"
    return f"{a}/{b} = {100 * a / b:.1f}%"


def _fmt_pairs(pairs) -> str:
    return ", ".join(f"{a} ({s})" for a, s in pairs) or "—"


def _pair_stats(gold_pairs, pred_pairs) -> tuple[int, int]:
    """Повертає (збіги пар, аспекти з тим самим назвою але іншою тональністю)."""
    g, p = Counter(gold_pairs), Counter(pred_pairs)
    tp = sum((g & p).values())
    g_rest, p_rest = g - p, p - g  # після віднімання лишаються пари, яких не збіглось
    wrong = 0
    for aspect in {a for a, _ in g_rest} & {a for a, _ in p_rest}:
        gn = sum(c for (a, _), c in g_rest.items() if a == aspect)
        pn = sum(c for (a, _), c in p_rest.items() if a == aspect)
        wrong += min(gn, pn)
    return tp, wrong


def _attempts(result: Result) -> list[tuple[int, str]]:
    """Невдалі спроби extractor з журналу результату."""
    return [(int(n), msg.strip()) for n, msg in _ATTEMPT_RE.findall("\n".join(result.logs))]


def evaluate(gold: list[dict], results: dict[int, Result]) -> Report:
    m = Metrics()
    errors: list[ErrorRow] = []

    for g in gold:
        r = results[g["id"]]
        gold_pairs = [(a["aspect"], a["sentiment"]) for a in g["aspects"]]
        pred_pairs = [(a.aspect, a.sentiment) for a in r.extraction.aspects] if r.extraction else []

        # Router
        m.router_total += 1
        route_ok = r.route == g["route"]
        m.router_ok += route_ok

        # Aspects: spam у precision/recall не входить
        if g["route"] != "spam":
            tp, wrong = _pair_stats(gold_pairs, pred_pairs)
            m.tp += tp
            m.sent_wrong += wrong
            m.gold_pairs += len(gold_pairs)
            m.pred_pairs += len(pred_pairs)

        # Extractor: повтори і цитати (лише відгуки, що дійшли до extractor)
        if r.route not in ("spam", "error"):
            m.attempted += 1
            attempts = _attempts(r)
            if attempts:
                m.retried += 1
            if not any(n == 1 and msg.startswith("Цитата") for n, msg in attempts):
                m.quote_first_ok += 1

        # Critic: чернетки, які критик відхилив
        if r.route == "full" and r.reply is not None:
            m.drafts += 1
            if r.iterations > 0:
                m.rejected += 1

        # Помилки
        if not route_ok or Counter(gold_pairs) != Counter(pred_pairs):
            kinds = []
            if not route_ok:
                kinds.append("маршрут")
            if Counter(gold_pairs) != Counter(pred_pairs):
                kinds.append("аспекти")
            if r.route == "spam":
                got_aspects = "extractor не запускався"
            elif r.extraction is None:
                got_aspects = "extractor не дав валідного результату"
            else:
                got_aspects = _fmt_pairs(pred_pairs)
            errors.append(ErrorRow(
                id=g["id"],
                expected=f"route={g['route']}; {_fmt_pairs(gold_pairs)}",
                got=f"route={r.route}; {got_aspects}",
                kind=", ".join(kinds),
            ))

    return Report(metrics=m, errors=errors)


def render(report: Report, mode: str, api_calls: int | None, non_spam: int) -> str:
    m = report.metrics
    today = datetime.date.today().isoformat()
    rows = [
        ("Router accuracy", _fmt_pct(m.router_ok, m.router_total),
         "маршрут збігся з gold, усі відгуки"),
        ("Aspect precision", _fmt_pct(m.tp, m.pred_pairs),
         "пари (аспект, тональність), немспам-відгуки"),
        ("Aspect recall", _fmt_pct(m.tp, m.gold_pairs),
         "пари (аспект, тональність), немспам-відгуки"),
        ("Sentiment accuracy", _fmt_pct(m.tp, m.tp + m.sent_wrong),
         "серед аспектів, знайдених за назвою"),
        ("Validation retry rate", _fmt_pct(m.retried, m.attempted),
         "відгуки з ≥1 невдалою спробою extractor / ті, що дійшли до extractor"),
        ("Quote validity (1-ша спроба)", _fmt_pct(m.quote_first_ok, m.attempted),
         "перша відповідь extractor без цитати поза текстом / ті, що дійшли до extractor"),
        ("Critic effect", _fmt_pct(m.rejected, m.drafts),
         "чернетки, відхилені критиком хоча б раз / чернетки full"),
    ]
    lines = [
        "# Результати оцінки",
        "",
        f"Режим: **{mode}**. Дата: {today}. Модель: `{_MODEL}`. "
        f"Відгуків: {m.router_total} (`data/gold.json`), немспам для aspect-метрик: {non_spam}.",
        "",
        "## Метрики",
        "",
        "| Метрика | Значення | Як рахується |",
        "|---|---|---|",
    ]
    lines += [f"| {name} | {val} | {how} |" for name, val, how in rows]
    lines += [
        "",
        "## Помилки",
        "",
        "Відгуки, де маршрут або набір пар (аспект, тональність) не збігся з gold.",
        "",
        "| id | Очікувалось | Отримано | Тип |",
        "|---|---|---|---|",
    ]
    if report.errors:
        lines += [f"| {e.id} | {e.expected} | {e.got} | {e.kind} |" for e in report.errors]
    else:
        lines.append("| — | — | — | помилок немає |")
    lines += [
        "",
        "## Технічне",
        "",
        f"- Нових записів у кеші (≈ викликів API): {api_calls if api_calls is not None else 'н/д'}.",
        "",
    ]
    return "\n".join(lines)


def run_pipeline(gold: list[dict]) -> dict[int, Result]:
    results: dict[int, Result] = {}
    for g in gold:
        try:
            results[g["id"]] = process(g["text"])
        except Exception as e:  # один збій не зриває весь прогін; він піде в таблицю помилок
            results[g["id"]] = Result(route="error", logs=[f"Помилка: {e}"], needs_human=True)
    return results


# --- Фейковий LLM: детермінована відповідь за gold, з кількома навмисними помилками ---

FAKE_ROUTE_OVERRIDE = {19: "positive"}          # роутер помиляється
FAKE_BAD_JSON_FIRST = {6}                       # перша відповідь extractor не JSON
FAKE_BAD_QUOTE_FIRST = {4}                      # перша відповідь з вигаданою цитатою
FAKE_DROP = {13: ("food", "positive")}          # extractor пропускає аспект
FAKE_FLIP = {40: (("speed", "negative"), ("speed", "positive"))}  # хибна тональність
FAKE_EXTRA = {1: ("price", "negative")}         # зайвий аспект
FAKE_CRITIC_REJECT_FIRST = {4}                  # критик відхиляє першу чернетку


def make_fake_llm(gold: list[dict]):
    by_text = {g["text"]: g for g in gold}
    by_id = {g["id"]: g for g in gold}
    calls: Counter = Counter()

    def rid_of(user: str) -> int:
        for text, g in by_text.items():
            if text in user:
                return g["id"]
        raise AssertionError("fake LLM: відгук не знайдено у запиті")

    def fake(system: str, user: str) -> str:
        if system == ROUTER_SYSTEM:
            rid = rid_of(user)
            route = FAKE_ROUTE_OVERRIDE.get(rid, by_id[rid]["route"])
            return json.dumps({"route": route, "reason": "фейкова відповідь"}, ensure_ascii=False)

        if system == EXTRACT_SYSTEM:
            rid = rid_of(user)
            calls[("extract", rid)] += 1
            first = calls[("extract", rid)] == 1
            if first and rid in FAKE_BAD_JSON_FIRST:
                return "це не JSON"
            pairs = [(a["aspect"], a["sentiment"]) for a in by_id[rid]["aspects"]]
            if rid in FAKE_DROP:
                pairs.remove(FAKE_DROP[rid])
            if rid in FAKE_FLIP:
                old, new = FAKE_FLIP[rid]
                pairs[pairs.index(old)] = new
            if rid in FAKE_EXTRA:
                pairs.append(FAKE_EXTRA[rid])
            review = by_id[rid]["text"]
            quote_bad = first and rid in FAKE_BAD_QUOTE_FIRST
            aspects = [
                {"aspect": a, "sentiment": s,
                 "quote": "вигадана цитата якої немає" if quote_bad else review}
                for a, s in pairs
            ]
            return json.dumps({"aspects": aspects, "urgency": "low", "language": "uk",
                               "needs_human": False}, ensure_ascii=False)

        if system == THANK_SYSTEM:
            return json.dumps({"reply": "Дякуємо за ваш відгук!"}, ensure_ascii=False)

        if system == WRITER_SYSTEM:
            return json.dumps({"reply": "Дякуємо за ваш відгук, ми передамо його команді."},
                              ensure_ascii=False)

        if system == CRITIC_SYSTEM:
            rid = rid_of(user)
            calls[("critic", rid)] += 1
            if rid in FAKE_CRITIC_REJECT_FIRST and calls[("critic", rid)] == 1:
                return json.dumps({"ok": False, "issues": ["тестове зауваження"]}, ensure_ascii=False)
            return json.dumps({"ok": True, "issues": []}, ensure_ascii=False)

        if system == REWRITE_SYSTEM:
            return json.dumps({"reply": "Дякуємо за ваш відгук, ми вже працюємо над цим."},
                              ensure_ascii=False)

        raise AssertionError("fake LLM: невідомий системний промпт")

    return fake


def _cache_count() -> int:
    return len(list(cache.CACHE_DIR.glob("*.json"))) if cache.CACHE_DIR.exists() else 0


def main(argv=None) -> Report:
    sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows інакше ламає кирилицю
    parser = argparse.ArgumentParser(description="Оцінка ReviewLens на gold.json")
    parser.add_argument("--fake", action="store_true", help="фейковий LLM, без API і без кешу")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="куди записати таблицю")
    args = parser.parse_args(argv)

    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))

    if args.fake:
        mode = "fake (без API)"
        with ExitStack() as stack:
            fake = make_fake_llm(gold)
            for mod in ("reviewlens.router", "reviewlens.extractor", "reviewlens.replier"):
                stack.enter_context(patch(f"{mod}.call_llm", side_effect=fake))
            before = _cache_count()
            results = run_pipeline(gold)
            api_calls = _cache_count() - before
    else:
        mode = "реальний (Claude API, з кешем)"
        before = _cache_count()
        results = run_pipeline(gold)
        api_calls = _cache_count() - before

    report = evaluate(gold, results)
    non_spam = sum(1 for g in gold if g["route"] != "spam")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(report, mode, api_calls, non_spam), encoding="utf-8")

    m = report.metrics
    print(f"Режим: {mode}")
    print(f"Router: {_fmt_pct(m.router_ok, m.router_total)}")
    print(f"Aspect P/R: {_fmt_pct(m.tp, m.pred_pairs)} / {_fmt_pct(m.tp, m.gold_pairs)}")
    print(f"Sentiment: {_fmt_pct(m.tp, m.tp + m.sent_wrong)}")
    print(f"Retry: {_fmt_pct(m.retried, m.attempted)}; quote 1-ша спроба: {_fmt_pct(m.quote_first_ok, m.attempted)}")
    print(f"Critic: {_fmt_pct(m.rejected, m.drafts)}")
    print(f"Помилок у таблиці: {len(report.errors)}; нових записів у кеші: {api_calls}")
    print(f"Записано: {args.out}")
    return report


if __name__ == "__main__":
    main()
