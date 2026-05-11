import logging

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext

from app.features.claims.intake_interview import (
    claims_required_ok,
    extract_claims_from_narrative,
)
from app.features.claims.states import ClaimsStates
from app.features.claims.pipeline import generate_claims_document
from app.shared.fsm_scenario import (
    FSM_ACTIVE_FEATURE,
    FSM_ACTIVE_SCENARIO,
    FSM_SCENARIO_ID_KEY,
    FEATURE_CLAIMS,
    SCENARIO_CLAIM,
    scenario_mismatch_for_claim,
)
from app.shared.scenario_registry import SCENARIO_CLAIMS_COMPLAINT, SCENARIO_CLAIMS_PRETRIAL
from app.shared.main_menu import BTN_CLAIM, main_menu_button_matches
from app.shared.free_usage import (
    assert_can_deliver_result,
    free_tier_footer_html,
    record_completed_result,
)
from app.shared.ux_copy import (
    UX_BEFORE_GENERATION_HTML,
    UX_FREE_NARRATIVE_INVITE_HTML,
    UX_RIBBON_HTML,
    UX_THIN_DATA_HTML,
)
from app.shared.legal_engine.claims_policy_flow import (
    format_claims_policy_block_message,
    format_claims_safe_draft_notice,
    merge_claims_clarify_queues_policy_first,
    policy_questions_for_claims_clarify,
)
from app.shared.legal_engine.clarify_policy import ClarifyDecision
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.telemetry_intake import (
    emit_telemetry_clarify_selected,
    emit_telemetry_gate_blocked,
    emit_telemetry_safe_draft_selected,
)
from app.shared.legal_engine.intake_interpreter import enrich_claims_merged_after_extract
from app.shared.legal_engine.interview_policy_flow import (
    ReadyPolicyBranch,
    classify_ready_policy_branch,
    legal_engine_should_block_generation,
    merge_clarify_queue_policy_first,
    resolve_legal_engine_policy_decision,
)

router = Router()
logger = logging.getLogger(__name__)


def _uid(m: Message) -> int | None:
    return m.from_user.id if m.from_user else None


CONFIRM_WORDS = {
    "да",
    "подтверждаю",
    "подтвердить",
    "ок",
    "верно",
    "все верно",
    "всё верно",
}


def _parse_claim_branch(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    if s in ("1", "а", "a"):
        return SCENARIO_CLAIMS_PRETRIAL
    if s in ("2", "б", "b"):
        return SCENARIO_CLAIMS_COMPLAINT
    return None


async def _claims_merge_and_persist(state: FSMContext, fields: dict[str, str]) -> None:
    await state.update_data(
        claim_type=fields.get("claim_type") or "",
        applicant=fields.get("applicant") or "",
        respondent=fields.get("respondent") or "",
        relationship=fields.get("relationship") or "",
        violation=fields.get("violation") or "",
        demands=fields.get("demands") or "",
        attachments=fields.get("attachments") or "",
    )


async def _claims_show_preview(message: Message, state: FSMContext) -> None:
    await state.update_data(claims_legal_engine_safe_draft="")
    data = await state.get_data()
    attachments_text = (data.get("attachments") or "").strip() or "нет"
    await message.answer(
        f"<b>Проверьте данные:</b>\n\n"
        f"Тип: {data.get('claim_type')}\n"
        f"Заявитель: {data.get('applicant')}\n"
        f"Адресат: {data.get('respondent')}\n\n"
        f"Отношения сторон:\n{data.get('relationship') or '—'}\n\n"
        f"Нарушение:\n{data.get('violation')}\n\n"
        f"Требования:\n{data.get('demands')}\n\n"
        f"Приложения:\n{attachments_text}\n\n"
        f"Если всё верно — напишите <b>подтвердить</b>."
        + free_tier_footer_html(_uid(message)),
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(ClaimsStates.confirm)


async def _claims_show_safe_preview(
    message: Message, state: FSMContext, policy_dec: ClarifyDecision
) -> None:
    snap = await state.get_data()
    sid_sd = (snap.get(FSM_SCENARIO_ID_KEY) or "").strip() or SCENARIO_CLAIMS_PRETRIAL
    emit_telemetry_safe_draft_selected(scenario_id=sid_sd, feature="claims")
    await state.update_data(claims_legal_engine_safe_draft="1")
    data = await state.get_data()
    attachments_text = (data.get("attachments") or "").strip() or "нет"
    notice = format_claims_safe_draft_notice(policy_dec)
    await message.answer(
        f"{notice}\n\n"
        f"<b>Проверьте данные:</b>\n\n"
        f"Тип: {data.get('claim_type')}\n"
        f"Заявитель: {data.get('applicant')}\n"
        f"Адресат: {data.get('respondent')}\n\n"
        f"Отношения сторон:\n{data.get('relationship') or '—'}\n\n"
        f"Нарушение:\n{data.get('violation')}\n\n"
        f"Требования:\n{data.get('demands')}\n\n"
        f"Приложения:\n{attachments_text}\n\n"
        f"Если согласны с осторожным черновиком — напишите <b>подтвердить</b>."
        + free_tier_footer_html(_uid(message)),
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(ClaimsStates.confirm)


# =====================================================
# START
# =====================================================


async def _start_claim(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ClaimsStates.branch_select)
    await state.update_data(
        **{
            FSM_ACTIVE_SCENARIO: SCENARIO_CLAIM,
            FSM_ACTIVE_FEATURE: FEATURE_CLAIMS,
            FSM_SCENARIO_ID_KEY: "",
        }
    )
    uid = _uid(message)
    await message.answer(
        "✍️ <b>Претензия / Жалоба</b>\n\n"
        "<b>Шаг 1.</b> Выберите юридический жанр (ответьте <b>1</b> или <b>2</b>):\n\n"
        "<b>1</b> — досудебная <b>претензия</b> контрагенту (банк, ТОО, ИП и т.д.)\n"
        "<b>2</b> — <b>жалоба</b> / обращение в <b>госорган</b> или иной публичный орган с контрольными функциями\n\n"
        "После выбора жанр <b>фиксируется</b> до конца сценария.\n\n"
        + UX_RIBBON_HTML
        + free_tier_footer_html(uid),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("claim"))
@router.message(F.text.func(lambda text: main_menu_button_matches(text, BTN_CLAIM, "claim")))
async def start(message: Message, state: FSMContext):
    await _start_claim(message, state)


# =====================================================
# FSM — ВЕТКА → СВОБОДНЫЙ РАССКАЗ → УТОЧНЕНИЯ → ПОДТВЕРЖДЕНИЕ
# =====================================================


@router.message(ClaimsStates.branch_select)
async def get_claim_branch(message: Message, state: FSMContext):
    sid = _parse_claim_branch(message.text or "")
    if not sid:
        await message.answer(
            "Нужно ответить числом: <b>1</b> (претензия контрагенту) или <b>2</b> (жалоба в орган).",
            parse_mode=ParseMode.HTML,
        )
        return
    await state.update_data(**{FSM_SCENARIO_ID_KEY: sid})
    await state.set_state(ClaimsStates.free_story)
    uid = _uid(message)
    await message.answer(
        UX_FREE_NARRATIVE_INVITE_HTML
        + "\n\n"
        + UX_RIBBON_HTML
        + free_tier_footer_html(uid),
        parse_mode=ParseMode.HTML,
    )


@router.message(ClaimsStates.free_story, F.text)
async def get_claim_free_story(message: Message, state: FSMContext):
    narrative = (message.text or "").strip()
    if len(narrative) < 15:
        await message.answer(
            f"Рассказ пока слишком короткий.\n\n{UX_THIN_DATA_HTML}",
            parse_mode=ParseMode.HTML,
        )
        return

    data = await state.get_data()
    sid = (data.get(FSM_SCENARIO_ID_KEY) or "").strip()
    if not sid:
        await state.clear()
        await message.answer("Сессия сброшена. Начните снова: /claim")
        return

    await message.answer("Разбираю текст и пополняю черновик фактов…", parse_mode=ParseMode.HTML)
    try:
        merged, questions = await extract_claims_from_narrative(narrative, sid)
    except Exception:
        logger.exception("claims intake extraction failed")
        await message.answer(
            "Не удалось разобрать рассказ. Попробуйте чуть подробнее одним сообщением или /claim.",
            parse_mode=ParseMode.HTML,
        )
        return

    merged, meta_patch, questions = await enrich_claims_merged_after_extract(
        narrative,
        sid,
        merged,
        questions,
        legal_engine_on=legal_engine_enabled(),
    )

    await _claims_merge_and_persist(state, merged)
    await state.update_data(claims_raw_narrative=narrative)
    if meta_patch:
        await state.update_data(**meta_patch)

    policy_dec = resolve_legal_engine_policy_decision(
        legal_engine_enabled(), sid, await state.get_data()
    )
    if policy_dec is not None and policy_dec.action == "block":
        emit_telemetry_gate_blocked(
            scenario_id=sid or SCENARIO_CLAIMS_PRETRIAL,
            feature="claims",
            outcome_code="claims_policy_block",
        )
        await message.answer(
            format_claims_policy_block_message(policy_dec),
            parse_mode=ParseMode.HTML,
        )
        return

    if not claims_required_ok(merged):
        questions = merge_claims_clarify_queues_policy_first(
            legal_engine_enabled(),
            policy_dec,
            questions,
        )
        if not questions:
            await message.answer(
                "Не хватает обязательных полей. Опишите ситуацию чуть подробнее одним сообщением.",
                parse_mode=ParseMode.HTML,
            )
            return

        emit_telemetry_clarify_selected(
            scenario_id=sid or SCENARIO_CLAIMS_PRETRIAL,
            feature="claims",
            clarify_depth=len(questions),
        )
        await state.update_data(
            claims_clarify_queue=questions,
            claims_clarify_index=0,
            claims_clarify_answers=[],
        )
        await state.set_state(ClaimsStates.interview_clarify)
        await message.answer(
            f"<b>Уточнение 1 из {len(questions)}</b>\n{questions[0]}",
            parse_mode=ParseMode.HTML,
        )
        return

    if policy_dec is not None:
        pq_ready = policy_questions_for_claims_clarify(policy_dec)
        branch = classify_ready_policy_branch(legal_engine_enabled(), policy_dec, pq_ready)
        if branch == ReadyPolicyBranch.CLARIFY_QUEUE and pq_ready:
            emit_telemetry_clarify_selected(
                scenario_id=sid or SCENARIO_CLAIMS_PRETRIAL,
                feature="claims",
                clarify_depth=len(pq_ready),
            )
            await state.update_data(
                claims_clarify_queue=pq_ready,
                claims_clarify_index=0,
                claims_clarify_answers=[],
            )
            await state.set_state(ClaimsStates.interview_clarify)
            await message.answer(
                f"<b>Уточнение 1 из {len(pq_ready)}</b>\n{pq_ready[0]}",
                parse_mode=ParseMode.HTML,
            )
            return
        if branch == ReadyPolicyBranch.SAFE_DRAFT:
            await _claims_show_safe_preview(message, state, policy_dec)
            return

    await _claims_show_preview(message, state)


@router.message(ClaimsStates.interview_clarify, F.text)
async def claims_interview_clarify(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужен текстовый ответ.", parse_mode=ParseMode.HTML)
        return

    data = await state.get_data()
    queue = list(data.get("claims_clarify_queue") or [])
    idx = int(data.get("claims_clarify_index") or 0)
    answers = list(data.get("claims_clarify_answers") or [])

    if idx >= len(queue):
        await _claims_show_preview(message, state)
        return

    answers.append(text)
    next_idx = idx + 1

    if next_idx < len(queue):
        await state.update_data(
            claims_clarify_index=next_idx,
            claims_clarify_answers=answers,
        )
        await message.answer(
            f"<b>Уточнение {next_idx + 1} из {len(queue)}</b>\n{queue[next_idx]}",
            parse_mode=ParseMode.HTML,
        )
        return

    blob = "\n\n".join(f"{queue[i]}\n— {answers[i]}" for i in range(len(queue)))
    prior = {
        "claim_type": (data.get("claim_type") or "").strip(),
        "applicant": (data.get("applicant") or "").strip(),
        "respondent": (data.get("respondent") or "").strip(),
        "relationship": (data.get("relationship") or "").strip(),
        "violation": (data.get("violation") or "").strip(),
        "demands": (data.get("demands") or "").strip(),
        "attachments": (data.get("attachments") or "").strip(),
    }
    sid = (data.get(FSM_SCENARIO_ID_KEY) or "").strip()
    enrich = f"\n\nДОПОЛНЕНИЯ ИЗ ДИАЛОГА:\n{blob}"
    base_story = (data.get("claims_raw_narrative") or "").strip()
    slots_line = "\n".join(f"{k}: {v}" for k, v in prior.items() if v)
    narrative = (base_story + "\n\n" if base_story else "") + slots_line + enrich

    try:
        merged2, extra = await extract_claims_from_narrative(narrative, sid)
    except Exception:
        logger.exception("claims clarify merge failed")
        merged2, extra = prior, []

    await _claims_merge_and_persist(state, merged2)
    await state.update_data(
        claims_clarify_queue=[],
        claims_clarify_index=0,
        claims_clarify_answers=[],
    )

    if claims_required_ok(merged2):
        policy_dec2 = resolve_legal_engine_policy_decision(
            legal_engine_enabled(), sid, await state.get_data()
        )
        if policy_dec2 is not None and policy_dec2.action == "block":
            emit_telemetry_gate_blocked(
                scenario_id=sid or SCENARIO_CLAIMS_PRETRIAL,
                feature="claims",
                outcome_code="claims_policy_block",
            )
            await message.answer(
                format_claims_policy_block_message(policy_dec2),
                parse_mode=ParseMode.HTML,
            )
            return
        pq2 = policy_questions_for_claims_clarify(policy_dec2) if policy_dec2 else []
        branch2 = classify_ready_policy_branch(
            legal_engine_enabled(), policy_dec2, pq2
        )
        if branch2 == ReadyPolicyBranch.CLARIFY_QUEUE and pq2:
            emit_telemetry_clarify_selected(
                scenario_id=sid or SCENARIO_CLAIMS_PRETRIAL,
                feature="claims",
                clarify_depth=len(pq2),
            )
            await state.update_data(
                claims_clarify_queue=pq2,
                claims_clarify_index=0,
                claims_clarify_answers=[],
            )
            await message.answer(
                f"<b>Уточнение 1 из {len(pq2)}</b>\n{pq2[0]}",
                parse_mode=ParseMode.HTML,
            )
            return
        if branch2 == ReadyPolicyBranch.SAFE_DRAFT:
            await _claims_show_safe_preview(message, state, policy_dec2)
            return
        await _claims_show_preview(message, state)
        return

    if extra:
        ex = list(extra[:3])
        dec2 = resolve_legal_engine_policy_decision(
            legal_engine_enabled(), sid, await state.get_data()
        )
        if dec2 is not None and dec2.action == "block":
            emit_telemetry_gate_blocked(
                scenario_id=sid or SCENARIO_CLAIMS_PRETRIAL,
                feature="claims",
                outcome_code="claims_policy_block",
            )
            await message.answer(
                format_claims_policy_block_message(dec2),
                parse_mode=ParseMode.HTML,
            )
            return
        pq_e = policy_questions_for_claims_clarify(dec2) if dec2 else []
        ex = merge_clarify_queue_policy_first(legal_engine_enabled(), dec2, ex, pq_e)
        if ex:
            emit_telemetry_clarify_selected(
                scenario_id=sid or SCENARIO_CLAIMS_PRETRIAL,
                feature="claims",
                clarify_depth=len(ex),
            )
            await state.update_data(
                claims_clarify_queue=ex,
                claims_clarify_index=0,
                claims_clarify_answers=[],
            )
            await message.answer(
                f"<b>Ещё уточнение 1 из {len(ex)}</b>\n{ex[0]}",
                parse_mode=ParseMode.HTML,
            )
            return

    await state.set_state(ClaimsStates.free_story)
    await message.answer(
        "Всё ещё не хватает данных для документа. Пришлите <b>одним сообщением</b> недостающее "
        "(адресат, суть нарушения, требования) или заново опишите ситуацию целиком.",
        parse_mode=ParseMode.HTML,
    )


@router.message(ClaimsStates.confirm)
async def confirm(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() not in CONFIRM_WORDS:
        await message.answer(
            "Если данные верны — напиши <b>подтвердить</b>.\n"
            "Или начни заново командой /claim.",
            parse_mode=ParseMode.HTML,
        )
        return

    facts = await state.get_data()

    if scenario_mismatch_for_claim(facts):
        await state.clear()
        await message.answer(
            "Это не сценарий претензии. Откройте «✍️ Претензия / Жалоба» в меню или /claim.",
            parse_mode=None,
        )
        return

    if not (facts.get(FSM_SCENARIO_ID_KEY) or "").strip():
        await state.clear()
        await message.answer(
            "Не зафиксирован жанр (претензия / жалоба). Начните сценарий заново: меню или /claim.",
            parse_mode=None,
        )
        return

    uid = _uid(message)
    ok, wall = assert_can_deliver_result(uid)
    if not ok:
        await message.answer(wall, parse_mode=ParseMode.HTML)
        return

    sid_confirm = (facts.get(FSM_SCENARIO_ID_KEY) or "").strip()
    blocked, pol = legal_engine_should_block_generation(
        legal_engine_enabled(), sid_confirm, facts
    )
    if blocked and pol is not None:
        await message.answer(
            format_claims_policy_block_message(pol),
            parse_mode=ParseMode.HTML,
        )
        return

    await state.clear()

    await message.answer(
        f"{UX_BEFORE_GENERATION_HTML}\n\n"
        "⚖️ Формирую претензию / жалобу, подожди…"
        + free_tier_footer_html(uid),
        parse_mode=ParseMode.HTML,
    )

    try:
        result = await generate_claims_document(facts)
    except Exception as e:
        await message.answer(
            "❌ <b>Не удалось сформировать документ</b>\n\n"
            f"Причина:\n<code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    summary = (result.get("rag_sources_summary") or "").strip()
    if summary:
        cap = 3900
        if len(summary) > cap:
            summary = summary[: cap - 40].rstrip() + "\n\n… [список норм усечён]"
        await message.answer(summary, parse_mode=ParseMode.HTML)

    await message.answer_document(FSInputFile(result["docx"]))
    await message.answer_document(FSInputFile(result["pdf"]))
    await message.answer("✅ <b>Документ готов.</b>", parse_mode=ParseMode.HTML)
    record_completed_result(uid)
