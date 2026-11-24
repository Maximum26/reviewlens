from typing import Literal

from pydantic import BaseModel, Field

# Для іншого домену змінюєш лише список Aspect.
Aspect = Literal["food", "service", "price", "speed", "atmosphere", "quality", "delivery", "other"]
Sentiment = Literal["positive", "negative", "neutral"]


class RouteDecision(BaseModel):
    route: Literal["spam", "escalate", "positive", "full"]
    reason: str


class AspectItem(BaseModel):
    aspect: Aspect
    sentiment: Sentiment
    quote: str = Field(min_length=3)  # фрагмент з оригіналу


class Extraction(BaseModel):
    aspects: list[AspectItem]
    urgency: Literal["low", "medium", "high"]
    language: str
    needs_human: bool


class Critique(BaseModel):
    ok: bool
    issues: list[str]  # напр. "обіцяє повернення коштів", "не згадує аспект speed"

class Reply(BaseModel):
    reply: str = Field(min_length=10)

class Insights(BaseModel):
    summary: str = Field(min_length=10)

