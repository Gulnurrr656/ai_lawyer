"""
Центральный dispatch пост-LLM качества по ScenarioDefinition.

Связывает verifier_profile / repair_profile с вызовами верификаторов, лимитом repair-раундов
и текстом repair-prompt. Пайплайны могут поэтапно переезжать сюда без смены публичных API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from app.shared.scenario_definitions import (
    VERIFIER_ANALYZE,
    VERIFIER_BANKRUPTCY_ANALYSIS,
    VERIFIER_BANKRUPTCY_STATEMENT,
    VERIFIER_CLAIMS_COMPLAINT,
    VERIFIER_CLAIMS_PRETRIAL,
    VERIFIER_CONSULT,
    VERIFIER_CONTRACT,
    VERIFIER_PETITION_ADMIN,
    VERIFIER_PETITION_CIVIL,
    scenario_definition,
)
from app.shared.scenario_registry import min_output_chars_for_scenario, repair_focus_for_scenario


@dataclass(frozen=True)
class PostLlmVerifyContext:
    """Контекст одной пост-проверки; поля опциональны там, где верификатор text-only."""

    scenario_id: str
    text: str
    generation_mode: str | None = None
    facts: Mapping[str, Any] | None = None
    rag_article_count: int | None = None
    min_output_chars: int | None = None
    bankruptcy_prelim: Any | None = None
    statement_llm_body: str | None = None
    contract_profile: dict[str, Any] | None = None


@dataclass(frozen=True)
class QualityGateSpec:
    scenario_id: str
    verifier_profile_key: str
    repair_profile: str
    repair_focus: str
    max_repair_rounds: int
    min_output_chars: int | None


# Канон по умолчанию; узкий кап — без «бесконечного» repair.
_MAX_REPAIR_ROUNDS_BY_VERIFIER: dict[str, int] = {
    VERIFIER_CONSULT: 2,
    VERIFIER_ANALYZE: 2,
    VERIFIER_PETITION_CIVIL: 2,
    VERIFIER_PETITION_ADMIN: 1,
    VERIFIER_CLAIMS_PRETRIAL: 1,
    VERIFIER_CLAIMS_COMPLAINT: 1,
    VERIFIER_BANKRUPTCY_ANALYSIS: 2,
    VERIFIER_BANKRUPTCY_STATEMENT: 1,
    VERIFIER_CONTRACT: 1,
}


def max_repair_rounds_for_scenario(
    scenario_id: str, *, generation_mode: str | None = None
) -> int:
    d = scenario_definition((scenario_id or "").strip())
    if not d:
        return 1
    key = d.verifier_profile_key(generation_mode=generation_mode)
    base = _MAX_REPAIR_ROUNDS_BY_VERIFIER.get(key, 1)
    ev = os.getenv(f"SCENARIO_QUALITY_MAX_REPAIR__{key}")
    if ev is not None and ev.strip() != "":
        try:
            return max(0, min(int(ev), 3))
        except ValueError:
            pass
    return max(0, min(base, 3))


def quality_gate_spec(
    scenario_id: str, *, generation_mode: str | None = None
) -> QualityGateSpec | None:
    sid = (scenario_id or "").strip()
    d = scenario_definition(sid)
    if not d:
        return None
    vkey = d.verifier_profile_key(generation_mode=generation_mode)
    return QualityGateSpec(
        scenario_id=sid,
        verifier_profile_key=vkey,
        repair_profile=d.repair_profile,
        repair_focus=d.repair_focus,
        max_repair_rounds=max_repair_rounds_for_scenario(sid, generation_mode=generation_mode),
        min_output_chars=d.min_output_chars,
    )


def build_repair_user_prompt(
    *,
    scenario_id: str,
    fail_reason: str,
    body: str,
    generation_mode: str | None = None,
) -> str:
    d = scenario_definition((scenario_id or "").strip())
    focus = repair_focus_for_scenario(scenario_id)
    genre_lines = ""
    if d and d.genre_constraints:
        genre_lines = "\n".join(f"- {g}" for g in d.genre_constraints[:3])
    intro: str
    if d and d.feature == "consult":
        intro = (
            "ИСПРАВЬ ТЕКСТ КОНСУЛЬТАЦИИ (юридическая памятка клиенту, не договор и не иск)."
        )
    elif d and d.feature == "analyze":
        intro = (
            "ИСПРАВЬ ЮРИДИЧЕСКИЙ АНАЛИЗ ДОКУМЕНТА (не переписывай договор целиком и не пиши иск)."
        )
    else:
        intro = "ИСПРАВЬ ТЕКСТ ПО ЗАДАНИЮ СЦЕНАРИЯ."
    gm = (generation_mode or "").strip()
    mode_line = f"Режим генерации: {gm}\n\n" if gm else ""
    repair_canon = (
        "ПРОДУКТОВЫЙ СТАНДАРТ (repair):\n"
        "- Клиент мог формулировать разговорно и с пробелами — дострой профессиональный жанр без занудства.\n"
        "- Недостающие факты/реквизиты: не блокируй ответ; вставь маркеры вида [УТОЧНИТЬ: …] где нужно имя, дата, сумма, реквизит и т.п.\n"
        "- Усиль структуру жанра, риски, практические шаги и (если уместно) просительную часть/выводы; опирайся на уже переданный контекст и RAG.\n"
        "- Не раздувай «водой»; не выходи из жанра; не выдумывай нормы вне исходного правового пакета.\n"
    )
    return (
        f"{intro}\n{mode_line}"
        f"Причина проверки (quality gate):\n{fail_reason}\n\n"
        f"Жанр (из глоссария сценария):\n{genre_lines}\n\n"
        f"Фокус усиления (repair):\n{focus}\n\n"
        f"{repair_canon}\n"
        "Сохрани опору на те же факты и нормы, что в исходном задании.\n"
        "Верни один цельный текст без комментариев исполнителя.\n\n"
        f"ТЕКСТ ДЛЯ ИСПРАВЛЕНИЯ:\n{body}"
    ).strip()


def run_post_llm_verify(ctx: PostLlmVerifyContext) -> tuple[bool, str]:
    """
    Вызывает верификатор, соответствующий verifier_profile сценария.

    Для сложных профилей обязательны поля ctx (facts, prelim и т.д.) — иначе ValueError,
    чтобы не маскировать «тихий» пропуск проверки.
    """
    sid = (ctx.scenario_id or "").strip()
    d = scenario_definition(sid)
    if not d:
        return True, ""

    vkey = d.verifier_profile_key(generation_mode=ctx.generation_mode)
    floor = ctx.min_output_chars if ctx.min_output_chars is not None else d.min_output_chars
    min_c = int(floor) if floor is not None else 0

    if vkey == VERIFIER_CONSULT:
        from app.features.consult.consult_memo_verify import verify_consult_memo_output

        return verify_consult_memo_output(ctx.text, min_chars=max(min_c, 1))

    if vkey == VERIFIER_ANALYZE:
        from app.features.analyze.analyze_document_verify import verify_analyze_document_output

        return verify_analyze_document_output(ctx.text, min_chars=max(min_c, 1))

    if vkey == VERIFIER_PETITION_CIVIL:
        if ctx.facts is None:
            raise ValueError("PostLlmVerifyContext.facts обязателен для petition_civil_lawsuit")
        from app.features.petitions.claim_verifier import verify_claim_document

        return verify_claim_document(
            ctx.text, dict(ctx.facts), min_len=max(min_c, 1)
        )

    if vkey == VERIFIER_PETITION_ADMIN:
        rlen = int(ctx.rag_article_count) if ctx.rag_article_count is not None else 0
        from app.features.petitions.admin_verifier import verify_admin_petition_document

        return verify_admin_petition_document(
            ctx.text, rag_len=rlen, min_len=max(min_c, 1)
        )

    if vkey in (VERIFIER_CLAIMS_PRETRIAL, VERIFIER_CLAIMS_COMPLAINT):
        from app.features.claims.claims_document_verifier import verify_claims_document

        floor_claim = int(min_output_chars_for_scenario(sid) or 1100)
        ml = max(min_c or 0, floor_claim)
        return verify_claims_document(
            ctx.text,
            scenario_id=sid,
            facts=dict(ctx.facts or {}),
            min_len=ml,
        )

    if vkey == VERIFIER_BANKRUPTCY_ANALYSIS:
        if ctx.bankruptcy_prelim is None:
            raise ValueError(
                "PostLlmVerifyContext.bankruptcy_prelim обязателен для bankruptcy_analysis"
            )
        from app.features.bankruptcy.bankruptcy_statement_verifier import (
            verify_bankruptcy_analysis_text,
        )

        m = min_c or int(min_output_chars_for_scenario(sid) or 950)
        return verify_bankruptcy_analysis_text(ctx.text, ctx.bankruptcy_prelim, min_chars=m)

    if vkey == VERIFIER_BANKRUPTCY_STATEMENT:
        if ctx.bankruptcy_prelim is None:
            raise ValueError(
                "PostLlmVerifyContext.bankruptcy_prelim обязателен для bankruptcy_statement"
            )
        from app.features.bankruptcy.bankruptcy_statement_verifier import (
            verify_bankruptcy_statement_text,
        )

        body = (
            ctx.statement_llm_body if ctx.statement_llm_body is not None else ctx.text
        )
        return verify_bankruptcy_statement_text(body, ctx.bankruptcy_prelim)

    if vkey == VERIFIER_CONTRACT:
        if not ctx.contract_profile or ctx.facts is None:
            return True, ""
        from app.features.contracts.verifier import verify_contract_text

        ok, reason, _ = verify_contract_text(
            ctx.text, ctx.contract_profile, dict(ctx.facts)
        )
        return ok, reason

    return True, ""
