import json

from pydantic import ValidationError

from reviewlens.llm import call_llm, parse_json
from reviewlens.prompts import (
    CRITIC_SYSTEM,
    REWRITE_SYSTEM,
    THANK_SYSTEM,
    WRITER_SYSTEM,
    build_critic_user,
    build_rewrite_user,
    build_writer_user,
)
from reviewlens.schemas import Critique, Extraction, Reply


def thank_positive(review: str) -> Reply:
    return Reply(**parse_json(call_llm(THANK_SYSTEM, review)))


def write_reply(review: str, extraction: Extraction) -> Reply:
    return Reply(**parse_json(call_llm(WRITER_SYSTEM, build_writer_user(review, extraction))))


def critique(review: str, extraction: Extraction, reply: Reply) -> Critique:
    return Critique(**parse_json(call_llm(CRITIC_SYSTEM, build_critic_user(review, extraction, reply.reply))))


def rewrite(review: str, extraction: Extraction, reply: Reply, critique: Critique) -> Reply:
    user = build_rewrite_user(review, extraction, reply.reply, critique.issues)
    return Reply(**parse_json(call_llm(REWRITE_SYSTEM, user)))


def reply_with_critic(review: str, extraction: Extraction, max_iter: int = 2) -> tuple[Reply, int, list[str]]:
    """write → critique → rewrite, до max_iter переписувань. Зупиняється, коли критик схвалив."""
    logs: list[str] = []
    reply = write_reply(review, extraction)
    logs.append("Writer: чернетку написано")
    iterations = 0

    while True:
        try:
            verdict = critique(review, extraction, reply)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            # Не зациклюємось на битій відповіді критика: вважаємо схваленим.
            logs.append(f"Critic: відповідь не розібрано ({e}), вважаю схваленим")
            break

        if verdict.ok:
            logs.append(f"Critic: схвалено після {iterations} переписувань")
            break

        logs.append(f"Critic: не схвалено. Зауваження: {verdict.issues}")
        if iterations >= max_iter:
            logs.append("Ліміт переписувань вичерпано, остання чернетка не схвалена критиком")
            break

        reply = rewrite(review, extraction, reply, verdict)
        iterations += 1
        logs.append(f"Rewrite: чернетку переписано (ітерація {iterations})")

    return reply, iterations, logs
