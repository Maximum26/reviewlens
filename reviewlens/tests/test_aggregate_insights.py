import io
import json

import pytest
from fastapi.testclient import TestClient

import server
from reviewlens import insights as ins
from reviewlens.aggregate import aggregate, result_to_dict
from reviewlens.pipeline import Result
from reviewlens.schemas import AspectItem, Extraction


def _ext(*items, needs_human=False):
    return Extraction(
        aspects=[AspectItem(aspect=a, sentiment=s, quote=q) for a, s, q in items],
        urgency="low", language="uk", needs_human=needs_human,
    )


def _rows():
    r1 = Result("full", _ext(("food", "negative", "cold soup"), ("price", "positive", "cheap")),
                reply="ok reply text", iterations=1, logs=["Router: full."])
    r2 = Result("full", _ext(("food", "negative", "cold soup"), ("service", "negative", "rude waiter")),
                reply="ok reply text", logs=["Спроба 1: bad json", "x"])
    r3 = Result("escalate", _ext(("food", "negative", "stale bread"), ("speed", "negative", "slow")),
                needs_human=True)
    r4 = Result("spam")
    r5 = Result("positive", _ext(("food", "positive", "tasty")), reply="thanks a lot!")
    return [(i + 1, f"t{i}", result_to_dict(r)) for i, r in enumerate([r1, r2, r3, r4, r5])]


def test_aggregate_counts_and_top():
    agg = aggregate(_rows())
    assert agg["routes"] == {"full": 2, "escalate": 1, "spam": 1, "positive": 1}
    assert agg["aspects"]["food"] == {"positive": 1, "negative": 3, "neutral": 0}
    assert agg["needs_human_count"] == 1
    assert agg["retry_count"] == 1
    top = agg["top_problems"]
    assert top[0]["aspect"] == "food" and top[0]["negative_count"] == 3
    assert top[0]["quotes"] == ["cold soup", "stale bread"]  # дубль прибраний
    # ничия: service і speed по 1, за назвою service < speed
    assert [t["aspect"] for t in top] == ["food", "service", "speed"]
    assert len(agg["rows"]) == 5
    json.dumps(agg)  # JSON-сумісність


def test_aggregate_empty_and_no_negatives():
    agg = aggregate([])
    assert agg["routes"] == {} and agg["top_problems"] == []
    only_pos = aggregate([(1, "t", result_to_dict(Result("positive", _ext(("food", "positive", "tasty")))))])
    assert only_pos["top_problems"] == []


def test_aggregate_top_limited_to_3_and_quotes_to_3():
    items = [(a, "negative", f"q{a}{i}") for a in ("food", "price") for i in range(5)]
    items += [("service", "negative", "qsvc"), ("speed", "negative", "qsp")]
    agg = aggregate([(1, "t", result_to_dict(Result("full", _ext(*items))))])
    assert len(agg["top_problems"]) == 3
    assert len(agg["top_problems"][0]["quotes"]) == 3


def test_aggregate_extraction_failed_row():
    # ExtractionFailed: extraction=None, логи в одному рядку
    r = Result("full", None, logs=["Router", "Спроба 1: err\nСпроба 2: err"], needs_human=True)
    agg = aggregate([(1, "t", result_to_dict(r))])
    assert agg["retry_count"] == 1 and agg["needs_human_count"] == 1
    assert agg["rows"][0]["aspects"] == []


def test_insights_no_problems_no_llm(monkeypatch):
    monkeypatch.setattr(ins, "call_llm", lambda *a: pytest.fail("LLM не має викликатись"))
    assert ins.make_insights({"top_problems": []}).summary == ins.NO_PROBLEMS_TEXT


def test_insights_payload_only_quotes_and_counts(monkeypatch):
    seen = {}

    def fake(system, user):
        seen["user"] = user
        return 'prefix {"summary": "Основна проблема: їжа холодна."} suffix'

    monkeypatch.setattr(ins, "call_llm", fake)
    agg = aggregate(_rows())
    out = ins.make_insights(agg)
    assert out.summary.startswith("Основна")
    payload = json.loads(seen["user"])
    assert set(payload) == {"routes", "top_problems"}
    assert "t0" not in seen["user"]  # тексти відгуків не передаються


@pytest.mark.parametrize("fake", [
    lambda *a: (_ for _ in ()).throw(RuntimeError("no key")),
    lambda *a: "not json",
    lambda *a: '{"summary": "short"}',
])
def test_insights_failure_fallback(monkeypatch, fake):
    monkeypatch.setattr(ins, "call_llm", fake)
    out = ins.make_insights(aggregate(_rows()))
    assert out.summary == ins.UNAVAILABLE_TEXT


# ---- /dashboard з підміненим process (0 викликів моделі) ----
@pytest.fixture
def client(monkeypatch):
    def fake_process(text):
        if text == "boom":
            raise RuntimeError("fail")
        if text == "spam":
            return Result("spam")
        return Result("full", _ext(("food", "negative", "cold soup")), reply="some reply here", iterations=1)

    monkeypatch.setattr(server, "process", fake_process)
    monkeypatch.setattr(server, "make_insights", lambda agg: ins.Insights(summary="fake insights text"))
    return TestClient(server.app)


def _post(client, csv: str):
    return client.post("/dashboard", files={"file": ("r.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")})


def test_dashboard_ok(client):
    r = _post(client, "id,text\n10,cold soup\n11,spam\n12,boom\n13,\n")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["routes"] == {"full": 1, "spam": 1}
    assert d["errors"] == [{"id": "12", "error": "fail"}]
    assert d["truncated"] is False
    assert d["insights"]["summary"] == "fake insights text"
    assert [x["id"] for x in d["rows"]] == ["10", "11"]  # порожній текст пропущено, id як рядки


def test_dashboard_bom_and_no_id(client):
    r = _post(client, "\ufefftext\ncold soup\nspam\n")
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["rows"]] == [1, 2]


def test_dashboard_string_ids(client):
    r = _post(client, "id,text\nabc,cold soup\n,spam\n")
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["rows"]] == ["abc", 2]


def test_dashboard_id_gaps_no_float(client):
    # пропуск в id раніше робив колонку float: 10 → "10.0", 007 → 7.0
    r = _post(client, "id,text\n10,cold soup\n,spam\n007,cold soup\n12,spam\n")
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["rows"]] == ["10", 2, "007", "12"]


def test_dashboard_numeric_text(client):
    r = _post(client, "text\n12345\n")
    assert r.status_code == 200, r.text


def test_dashboard_no_text_column(client):
    assert _post(client, "a,b\n1,2\n").status_code == 400


def test_dashboard_truncation(client):
    csv = "text\n" + "\n".join(f"r{i}" for i in range(60)) + "\n"
    d = _post(client, csv).json()
    assert d["truncated"] is True and len(d["rows"]) == server.MAX_ROWS


def test_dashboard_empty_csv(client):
    r = _post(client, "text\n")
    assert r.status_code == 200, r.text
