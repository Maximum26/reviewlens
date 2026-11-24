import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from reviewlens.aggregate import aggregate, result_to_dict
from reviewlens.insights import make_insights
from reviewlens.pipeline import process

MAX_ROWS = 50

app = FastAPI(title="ReviewLens")


class ReviewIn(BaseModel):
    text: str


def _row_id(value, row_number: int):
    """id з колонки id (рядок, читається з dtype=str), якщо є і не порожній; інакше номер рядка."""
    if value is None or pd.isna(value):
        return row_number
    return str(value)


@app.post("/analyze")
def analyze(body: ReviewIn):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Порожній текст відгуку")
    return result_to_dict(process(body.text))


@app.post("/dashboard")
def dashboard(file: UploadFile):
    try:
        # id читаємо як рядок: інакше pandas з пропусками робить його float (10 → 10.0)
        df = pd.read_csv(file.file, encoding="utf-8-sig", dtype={"id": str})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не вдалося прочитати CSV: {e}")

    if "text" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="У CSV немає обов'язкової колонки 'text'. Назви колонку з текстами відгуків 'text'.",
        )

    # index після reset_index відповідає номеру рядка даних (з 0), далі фільтрація його не змінює.
    df = df.reset_index(drop=True)
    df = df[df["text"].notna() & (df["text"].astype(str).str.strip() != "")]
    truncated = len(df) > MAX_ROWS
    df = df.head(MAX_ROWS)

    has_id = "id" in df.columns
    rows, errors = [], []
    for idx, row in df.iterrows():
        rid = _row_id(row["id"] if has_id else None, int(idx) + 1)
        text = str(row["text"])
        try:
            rows.append((rid, text, result_to_dict(process(text))))
        except Exception as e:
            errors.append({"id": rid, "error": str(e)})

    agg = aggregate(rows)
    agg["insights"] = make_insights(agg).model_dump()
    agg["errors"] = errors
    agg["truncated"] = truncated
    return agg


app.mount("/", StaticFiles(directory="static", html=True), name="static")
