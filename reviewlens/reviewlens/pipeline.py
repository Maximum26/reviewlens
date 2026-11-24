from dataclasses import dataclass, field

from reviewlens.extractor import ExtractionFailed, extract
from reviewlens.replier import reply_with_critic, thank_positive
from reviewlens.router import route_review
from reviewlens.schemas import Extraction


@dataclass
class Result:
    route: str
    extraction: Extraction | None = None
    reply: str | None = None  # None для spam, escalate і при збої replier
    iterations: int = 0  # переписувань критиком
    logs: list[str] = field(default_factory=list)
    needs_human: bool = False


def process(review: str) -> Result:
    decision = route_review(review)
    logs = [f"Router: {decision.route}. {decision.reason}"]

    # Спам відсікаємо без подальших LLM-викликів.
    if decision.route == "spam":
        return Result(route="spam", logs=logs)

    # escalate, positive і full ідуть однаково: extract. Різниця лише в needs_human.
    try:
        extraction, extract_logs = extract(review)
    except ExtractionFailed as e:
        return Result(route=decision.route, logs=logs + [str(e)], needs_human=True)

    reply: str | None = None
    iterations = 0
    reply_logs: list[str] = []
    # Збій LLM у replier не валить процес: пишемо в logs, reply лишається None.
    try:
        if decision.route == "positive":
            reply = thank_positive(review).reply
        elif decision.route == "full":
            draft, iterations, reply_logs = reply_with_critic(review, extraction)
            reply = draft.reply
    except Exception as e:
        reply_logs.append(f"Replier: помилка LLM ({e}), відповідь не згенеровано")
        reply, iterations = None, 0

    return Result(
        route=decision.route,
        extraction=extraction,
        reply=reply,
        iterations=iterations,
        logs=logs + extract_logs + reply_logs,
        needs_human=decision.route == "escalate" or extraction.needs_human,
    )
