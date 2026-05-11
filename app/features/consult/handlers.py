import html
import logging

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.features.consult.consult_triage import (
    CONSULT_CATEGORY_RU,
    consultation_ready_for_generation,
    triage_consultation,
)
from app.features.consult.states import ConsultStates
from app.features.consult.base_pipeline import generate_consultation
from app.shared.fsm_scenario import (
    FSM_ACTIVE_FEATURE,
    FSM_ACTIVE_SCENARIO,
    FSM_SCENARIO_ID_KEY,
    FEATURE_CONSULT,
    SCENARIO_CONSULT,
    scenario_mismatch_for_consult,
)
from app.shared.scenario_registry import SCENARIO_CONSULT_MEMO
from app.shared.main_menu import BTN_CONSULT, main_menu_button_matches
from app.shared.telegram_chunks import (
    split_html_message_chunks_for_telegram,
    split_plain_chunks_for_telegram,
)
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
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.telemetry_intake import (
    emit_telemetry_clarify_selected,
    emit_telemetry_gate_blocked,
    emit_telemetry_safe_draft_selected,
)
from app.shared.legal_engine.consult_policy_flow import (
    consult_policy_slot_for_question,
    format_consult_policy_block_message,
    format_consult_safe_draft_notice,
    merge_consult_clarify_queues_policy_first,
    policy_questions_for_consult_clarify,
)
from app.shared.legal_engine.intake_interpreter import (
    extra_clarify_questions_from_interpretation,
    interpret_consult_intake,
    merge_consult_interpretation,
)
from app.shared.legal_engine.interview_policy_flow import (
    ReadyPolicyBranch,
    classify_ready_policy_branch,
    legal_engine_should_block_generation,
    resolve_legal_engine_policy_decision,
)

router = Router()
logger = logging.getLogger(__name__)
CONFIRM_WORDS = {
    "да",
    "подтверждаю",
    "подтвердить",
    "ок",
    "верно",
    "все верно",
    "всё верно",
}


_PREVIEW_TOPIC = 500
_PREVIEW_SITUATION = 900
_PREVIEW_GOAL = 450
_PREVIEW_CONSTRAINTS = 450
_PREVIEW_CLAR_EXCERPT = 950


def _ellipsize(s: str, max_len: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    if max_len <= 1:
        return "…"
    return s[: max_len - 1].rstrip() + "…"


async def _consult_send_html(message: Message, html_body: str) -> None:
    html_body = (html_body or "").strip()
    if not html_body:
        return
    chunks = split_html_message_chunks_for_telegram(html_body)
    n = len(chunks)
    for i, ch in enumerate(chunks):
        body = ch
        if i > 0:
            body = f"<i>(продолжение {i + 1}/{n})</i>\n\n{ch}"
        await message.answer(body, parse_mode=ParseMode.HTML)


def _uid(m: Message) -> int | None:
    return m.from_user.id if m.from_user else None


async def _consult_send_consult_preview_routed(
    message: Message,
    state: FSMContext,
    data: dict,
    policy_dec,
    *,
    thanks_prefix: str = "",
) -> None:
    """Превью confirm: normal / safe_draft по политике (только смысл при LEGAL_ENGINE=1)."""
    engine_on = legal_engine_enabled()
    pq = policy_questions_for_consult_clarify(policy_dec) if policy_dec else []
    branch = classify_ready_policy_branch(engine_on, policy_dec, pq)
    prev = _consult_preview_html(data, _uid(message))
    if branch == ReadyPolicyBranch.SAFE_DRAFT:
        sid_td = (data.get(FSM_SCENARIO_ID_KEY) or "").strip() or SCENARIO_CONSULT_MEMO
        emit_telemetry_safe_draft_selected(scenario_id=sid_td, feature="consult")
        await state.update_data(consult_legal_engine_safe_draft="1")
        notice = format_consult_safe_draft_notice(policy_dec)
        mid = f"{notice}\n\n{prev}"
    else:
        await state.update_data(consult_legal_engine_safe_draft="")
        mid = prev
    body = f"{thanks_prefix}{mid}" if thanks_prefix else mid
    await _consult_send_html(message, body)
    await state.set_state(ConsultStates.confirm)


async def _consult_send_plain(message: Message, text: str) -> None:
    chunks = split_plain_chunks_for_telegram(text)
    n = len(chunks)
    for i, ch in enumerate(chunks):
        body = ch
        if i > 0:
            body = f"(продолжение {i + 1}/{n})\n\n{ch}"
        await message.answer(body)


def _consult_preview_html(data: dict, user_id: int | None = None) -> str:
    clar = (data.get("consult_clarifications") or "").strip()
    cat = (data.get("consult_primary_category") or "").strip()
    labels = (data.get("consult_labels") or "").strip()
    meta_lines: list[str] = []
    if cat:
        cat_h = html.escape(CONSULT_CATEGORY_RU.get(cat, cat))
        meta_lines.append(f"<b>Классификация (черновик):</b> {cat_h}")
    if labels:
        parts = [
            CONSULT_CATEGORY_RU.get(p.strip(), p.strip())
            for p in labels.split(",")
            if p.strip()
        ]
        meta_lines.append("<b>Метки тем:</b> " + html.escape(", ".join(parts)))
    meta = "\n".join(meta_lines)
    if clar:
        excerpt = _ellipsize(clar, _PREVIEW_CLAR_EXCERPT)
        tail_note = ""
        if len(clar) > _PREVIEW_CLAR_EXCERPT:
            tail_note = (
                f"\n\n<i>…полный текст уточнений ({len(clar)} симв.) "
                f"передан в консультацию; здесь только начало.</i>"
            )
        meta += (
            "\n\n<b>Уточнения (начало):</b>\n<pre>"
            + html.escape(excerpt)
            + "</pre>"
            + tail_note
        )

    topic_str = _ellipsize(str(data.get("topic") or ""), _PREVIEW_TOPIC)
    sit_str = _ellipsize(str(data.get("situation") or ""), _PREVIEW_SITUATION)
    goal_str = _ellipsize(str(data.get("goal") or ""), _PREVIEW_GOAL)
    cons_raw = str(data.get("constraints") or "").strip()
    cons_str = _ellipsize(cons_raw if cons_raw else "не указаны", _PREVIEW_CONSTRAINTS)

    return (
        "<b>Проверь данные перед консультацией</b>\n"
        + (f"\n{meta}\n" if meta else "\n")
        + f"\n<b>Тема:</b>\n{html.escape(topic_str)}\n\n"
        f"<b>Ситуация:</b>\n{html.escape(sit_str)}\n\n"
        f"<b>Цель:</b>\n{html.escape(goal_str)}\n\n"
        f"<b>Риски / ограничения:</b>\n"
        f"{html.escape(cons_str)}\n\n"
        "<i>Полные формулировки и ответы на уточнения уже в состоянии сценария — "
        "здесь краткая сводка для проверки.</i>\n\n"
        "Если всё верно — напиши <b>подтвердить</b>."
        + free_tier_footer_html(user_id)
    )


# =====================================================
# START
# =====================================================


async def _start_consult(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ConsultStates.topic)
    await state.update_data(
        **{
            FSM_ACTIVE_SCENARIO: SCENARIO_CONSULT,
            FSM_ACTIVE_FEATURE: FEATURE_CONSULT,
            FSM_SCENARIO_ID_KEY: SCENARIO_CONSULT_MEMO,
            "consult_legal_engine_safe_draft": "",
        }
    )
    uid = _uid(message)
    await message.answer(
        "💬 <b>Юридическая консультация</b>\n\n"
        + UX_FREE_NARRATIVE_INVITE_HTML
        + "\n\n"
        "<b>Шаг 1.</b> Для удобства начните с короткой сути (долг, банк, спор, договор…). "
        "Дальше попросим ситуацию, цель и ограничения — или задам уточняющие вопросы.\n\n"
        + UX_RIBBON_HTML
        + free_tier_footer_html(uid),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("consult"))
@router.message(F.text.func(lambda text: main_menu_button_matches(text, BTN_CONSULT, "consult")))
async def start(message: Message, state: FSMContext):
    await _start_consult(message, state)


# =====================================================
# FSM — СБОР ФАКТОВ
# =====================================================


@router.message(ConsultStates.topic)
async def get_topic(message: Message, state: FSMContext):
    await state.update_data(topic=(message.text or "").strip())
    await state.set_state(ConsultStates.situation)
    await message.answer(
        "<b>Шаг 2.</b> Опишите ситуацию: что произошло, кто участвует, в чём проблема.",
        parse_mode=ParseMode.HTML,
    )


@router.message(ConsultStates.situation)
async def get_situation(message: Message, state: FSMContext):
    await state.update_data(situation=(message.text or "").strip())
    await state.set_state(ConsultStates.goal)
    await message.answer(
        "<b>Шаг 3.</b> Чего хотите добиться?\n"
        "Например: понять права, выбрать стратегию, снизить риски, подготовиться к спору.",
        parse_mode=ParseMode.HTML,
    )


@router.message(ConsultStates.goal)
async def get_goal(message: Message, state: FSMContext):
    await state.update_data(goal=(message.text or "").strip())
    await state.set_state(ConsultStates.constraints)
    await message.answer(
        "<b>Шаг 4.</b> Есть ли ограничения или риски?\n"
        "Сроки, давление, проверки, угрозы. Если нет — «нет».",
        parse_mode=ParseMode.HTML,
    )


@router.message(ConsultStates.constraints)
async def get_constraints(message: Message, state: FSMContext):
    constraints_text = (message.text or "").strip()
    engine_on = legal_engine_enabled()
    if constraints_text.lower() in {"нет", "нету", "no"}:
        constraints_text = "нет" if engine_on else ""

    await state.update_data(constraints=constraints_text)
    data = await state.get_data()

    interp = None
    if engine_on:
        try:
            interp = await interpret_consult_intake(data)
            patch = merge_consult_interpretation(data, interp)
            if patch:
                await state.update_data(**patch)
                data = await state.get_data()
        except Exception:
            logger.exception("consult LEGAL_ENGINE intake interpreter failed")
            interp = None

    triage = triage_consultation(data)
    await state.update_data(
        consult_primary_category=triage.primary,
        consult_labels=",".join(triage.labels),
        consult_triage_mixed="1" if triage.is_mixed else "0",
    )
    data = await state.get_data()

    sid = (data.get(FSM_SCENARIO_ID_KEY) or "").strip() or SCENARIO_CONSULT_MEMO
    policy_dec = resolve_legal_engine_policy_decision(engine_on, sid, data)
    if policy_dec is not None and policy_dec.action == "block":
        emit_telemetry_gate_blocked(
            scenario_id=sid,
            feature="consult",
            outcome_code="consult_policy_block",
        )
        await _consult_send_html(message, format_consult_policy_block_message(policy_dec))
        return

    q_from_triage = list(triage.clarifying_questions or [])[:3]
    q_from_interp = (
        extra_clarify_questions_from_interpretation(interp) if interp is not None and engine_on else []
    )
    base_queue = q_from_triage if q_from_triage else q_from_interp[:3]
    clarify_questions = merge_consult_clarify_queues_policy_first(
        engine_on, policy_dec, base_queue
    )

    if clarify_questions:
        qlist = clarify_questions
        emit_telemetry_clarify_selected(
            scenario_id=sid,
            feature="consult",
            clarify_depth=len(qlist),
        )
        await state.update_data(
            consult_clarify_queue=qlist,
            consult_clarify_index=0,
            consult_clarify_answers=[],
        )
        await state.set_state(ConsultStates.clarify)
        intro = ""
        if triage.is_mixed:
            intro = (
                "Похоже, вопрос <b>смешанный</b> или в нём <b>несколько тем</b>. "
                "Сначала коротко уточним факты — так консультация будет точнее и без «воды».\n\n"
            )
        await _consult_send_html(
            message,
            intro + f"<b>Уточнение 1 из {len(qlist)}</b>\n{qlist[0]}",
        )
        return

    await _consult_send_consult_preview_routed(message, state, data, policy_dec)


@router.message(ConsultStates.clarify)
async def consult_clarify(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужен текстовый ответ на вопрос.", parse_mode=ParseMode.HTML)
        return

    data = await state.get_data()
    queue = list(data.get("consult_clarify_queue") or [])
    idx = int(data.get("consult_clarify_index") or 0)
    answers = list(data.get("consult_clarify_answers") or [])

    if idx >= len(queue):
        sid = (data.get(FSM_SCENARIO_ID_KEY) or "").strip() or SCENARIO_CONSULT_MEMO
        policy_dec = resolve_legal_engine_policy_decision(
            legal_engine_enabled(), sid, data
        )
        if policy_dec is not None and policy_dec.action == "block":
            emit_telemetry_gate_blocked(
                scenario_id=sid,
                feature="consult",
                outcome_code="consult_policy_block",
            )
            await _consult_send_html(message, format_consult_policy_block_message(policy_dec))
            return
        await _consult_send_consult_preview_routed(message, state, data, policy_dec)
        return

    slot_key = consult_policy_slot_for_question(queue[idx])
    answers.append(text)
    next_idx = idx + 1
    patch: dict = {
        "consult_clarify_index": next_idx,
        "consult_clarify_answers": answers,
    }
    if slot_key:
        patch[slot_key] = text.strip()

    if next_idx < len(queue):
        await state.update_data(**patch)
        await _consult_send_html(
            message,
            f"<b>Уточнение {next_idx + 1} из {len(queue)}</b>\n{queue[next_idx]}",
        )
        return

    await state.update_data(**patch)
    data_after_slot = await state.get_data()
    sid = (data_after_slot.get(FSM_SCENARIO_ID_KEY) or "").strip() or SCENARIO_CONSULT_MEMO
    policy_mid = resolve_legal_engine_policy_decision(
        legal_engine_enabled(), sid, data_after_slot
    )
    if policy_mid is not None and policy_mid.action == "block":
        await _consult_send_html(
            message, format_consult_policy_block_message(policy_mid)
        )
        return

    blob = "\n\n".join(
        f"• {queue[i]}\n— {answers[i]}" for i in range(len(queue))
    )
    await state.update_data(
        consult_clarifications=blob,
        consult_clarify_queue=[],
        consult_clarify_index=0,
        consult_clarify_answers=[],
    )
    fresh = await state.get_data()
    await _consult_send_consult_preview_routed(
        message,
        state,
        fresh,
        resolve_legal_engine_policy_decision(legal_engine_enabled(), sid, fresh),
        thanks_prefix="<b>Спасибо</b>, уточнения учтены. Проверьте сводку:\n\n",
    )


# =====================================================
# CONFIRM → PIPELINE
# =====================================================


@router.message(ConsultStates.confirm)
async def confirm(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() not in CONFIRM_WORDS:
        await message.answer(
            "Если данные верны — напиши <b>подтвердить</b>.\n"
            "Или начни заново: /consult",
            parse_mode=ParseMode.HTML,
        )
        return

    facts = await state.get_data()
    sid_confirm = (facts.get(FSM_SCENARIO_ID_KEY) or "").strip() or SCENARIO_CONSULT_MEMO
    blocked, pol_block = legal_engine_should_block_generation(
        legal_engine_enabled(), sid_confirm, facts
    )
    if blocked and pol_block is not None:
        await _consult_send_html(message, format_consult_policy_block_message(pol_block))
        return

    if scenario_mismatch_for_consult(facts):
        await state.clear()
        await message.answer(
            "Активен другой сценарий (не консультация). Откройте <b>«💬 Консультация»</b> в меню "
            "или команду /consult.",
            parse_mode=ParseMode.HTML,
        )
        return
    if facts.get("legal_goal") in ("A", "B"):
        await state.clear()
        await message.answer(
            "В данных обнаружен сценарий заявления/иска. Для консультации начните заново: "
            "<b>«💬 Консультация»</b> или /consult.",
            parse_mode=ParseMode.HTML,
        )
        return

    ready, ready_msg = consultation_ready_for_generation(facts)
    if not ready:
        await message.answer(
            f"{ready_msg}\n\n{UX_THIN_DATA_HTML}",
            parse_mode=ParseMode.HTML,
        )
        return

    uid = _uid(message)
    ok, wall = assert_can_deliver_result(uid)
    if not ok:
        await message.answer(wall, parse_mode=ParseMode.HTML)
        return

    await state.clear()

    await message.answer(
        f"{UX_BEFORE_GENERATION_HTML}\n\n"
        "⚖️ Формирую консультацию с учётом ваших ответов…"
        + free_tier_footer_html(uid),
        parse_mode=ParseMode.HTML,
    )

    try:
        result = await generate_consultation(facts)
    except Exception as e:
        await message.answer(
            "❌ <b>Не удалось сформировать консультацию</b>\n\n"
            f"Причина:\n<code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    out_text = (result.get("text") or "").strip()
    await _consult_send_plain(message, result.get("text") or "")
    if out_text:
        record_completed_result(uid)
    await message.answer(
        "<b>Следующие шаги в боте</b> (выберите по делу):\n"
        "• <b>Претензия / жалоба</b> — досудебное обращение к контрагенту или организации\n"
        "• <b>Заявление</b> — административное или иное (сценарий заявлений)\n"
        "• <b>Иск</b> — гражданский иск из того же меню сценариев\n"
        "• <b>Анализ документа</b> — разбор текста договора/акта\n"
        "• <b>Банкротство</b> — если речь о несостоятельности/долговом контуре\n\n"
        "Соберите документы по теме консультации (переписка, договоры, акты, уведомления) "
        "перед запуском следующего сценария — так ответ будет точнее.",
        parse_mode=ParseMode.HTML,
    )
