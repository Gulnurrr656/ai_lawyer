from __future__ import annotations

import logging
import os
from typing import Any, Dict

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext

from app.shared.fsm_scenario import (
    FSM_ACTIVE_FEATURE,
    FSM_ACTIVE_SCENARIO,
    FSM_SCENARIO_ID_KEY,
    FEATURE_PETITION,
    SCENARIO_PETITION,
    scenario_mismatch_for_petition,
)
from app.shared.scenario_registry import SCENARIO_PETITION_ADMIN, SCENARIO_PETITION_CIVIL
from app.shared.main_menu import BTN_PETITION, main_menu_button_matches

from .states import PetitionStates
from .pipeline_admin import generate_petition
from .pipeline_claim import generate_civil_lawsuit
from .intake_interview import (
    PETITION_SLOTS,
    extract_petition_slots_from_story,
    format_petition_preview_for_user,
    merge_petition_slot_updates,
    petition_critical_missing,
    petition_pipeline_ready,
    SLOT_LABEL_RU,
)

from app.shared.free_usage import (
    assert_can_deliver_result,
    free_tier_footer_html,
    free_tier_footer_plain,
    record_completed_result,
)
from app.shared.ux_copy import (
    UX_AFTER_CANCEL_HTML,
    UX_BEFORE_GENERATION_HTML,
    UX_FREE_NARRATIVE_INVITE_HTML,
    UX_RIBBON_HTML,
    UX_RIBBON_PLAIN,
)
from app.shared.legal_engine.config import legal_engine_enabled
from app.shared.legal_engine.run_record import FeatureKey
from app.shared.legal_engine.telemetry_intake import (
    emit_telemetry_clarify_selected,
    emit_telemetry_gate_blocked,
    emit_telemetry_safe_draft_selected,
)
from app.shared.legal_engine.interview_policy_flow import (
    ReadyPolicyBranch,
    classify_ready_policy_branch,
    legal_engine_should_block_generation,
    merge_clarify_queue_policy_first,
    resolve_legal_engine_policy_decision,
)
from app.shared.legal_engine.petitions_policy_flow import (
    format_petition_policy_block_message,
    format_petition_safe_draft_notice,
    merge_petition_clarify_queues_policy_first,
    policy_questions_for_petition_clarify,
)

router = Router()
logger = logging.getLogger(__name__)

# Минимальная длина свободного рассказа (ниже — шум/случайные нажатия; выше порога — полноценный intake)
PETITION_MIN_STORY_CHARS = 15


def _uid(m: Message) -> int | None:
    return m.from_user.id if m.from_user else None

_TG_MAX_CHARS = 3500


def _safe_preview(text: str, limit: int = _TG_MAX_CHARS) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n…(полный текст в DOCX)"


def _safe_tg_text(text: str, limit: int = 3500) -> str:
    """Лимит Telegram для обычных сообщений (~4096; запас под разметку)."""
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 60)].rstrip() + "\n\n… (текст сокращён — лимит Telegram)"


TG_PLAIN_CHUNK = 3200


async def _answer_plain_chunks(message: Message, text: str) -> None:
    """Отправка длинного текста несколькими сообщениями (исключает message too long).

    parse_mode=None — глобальный default бота HTML; иначе символы вроде «<» в тексте
    ошибок или ввода пользователя ломают разбор сущностей Telegram.
    """
    s = (text or "").strip()
    if not s:
        return
    if len(s) <= TG_PLAIN_CHUNK:
        await message.answer(s, parse_mode=None)
        return
    i = 0
    n = len(s)
    part_no = 0
    while i < n:
        part_no += 1
        end = min(i + TG_PLAIN_CHUNK, n)
        chunk = s[i:end]
        if end < n:
            brk = chunk.rfind("\n")
            if brk >= TG_PLAIN_CHUNK // 2:
                chunk = s[i : i + brk]
                i += brk + 1
            else:
                i = end
        else:
            i = n
        body = chunk.strip()
        if body:
            if part_no > 1:
                body = f"(продолжение {part_no})\n\n" + body
            await message.answer(body, parse_mode=None)


_GATE_TEXT = (
    "⚖️ УТОЧНЕНИЕ ПРОЦЕССУАЛЬНОЙ ФОРМЫ\n\n"
    "Сначала выберите вариант А или Б ниже. После выбора можно описать ситуацию своими словами (текст или голос); "
    "при необходимости бот задаст уточняющие вопросы; в любой момент — «отмена».\n\n"
    "Выберите, какой документ вам нужен (это влияет на форму и принятие судом):\n\n"
    "Вариант А — Административное заявление (АДМ)\n"
    "— оспорить решение/действие/бездействие;\n"
    "— обязать госорган совершить действие/устранить нарушение;\n"
    "— НЕ исковое заявление.\n\n"
    "Вариант Б — Исковое заявление (ГПО)\n"
    "— гражданско-правовой спор (взыскание, обязанность, признание права и т.п.).\n\n"
    "👉 Напишите: А или Б"
)


def _norm_text(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = s.replace("📝", "").strip()
    return s


def _normalize_ab(raw: str) -> str | None:
    s = _norm_text(raw)
    if not s:
        return None

    # Б — иск (ГПО): раньше А, иначе «исковое заявление» попадает на «…заявлен…» и уходит в АДМ.
    if s in {"b", "б"}:
        return "B"
    if "гпо" in s:
        return "B"
    if "исков" in s:
        return "B"
    if "иск" in s:
        return "B"
    if "взыск" in s or "деньг" in s or "убыт" in s or "долг" in s:
        return "B"

    # А — административное заявление
    if s in {"a", "а"}:
        return "A"
    if "адм" in s or "администра" in s:
        return "A"
    if "оспор" in s or "незакон" in s or "госорган" in s:
        return "A"
    if s == "заявление" or ("заявлен" in s and "исков" not in s):
        return "A"

    return None


def _doc_label(legal_goal: str | None) -> str:
    return (
        "Административное заявление (АДМ)"
        if legal_goal == "A"
        else "Исковое заявление (ГПО)"
    )


def _petition_legacy_intake_enabled() -> bool:
    return os.getenv("PETITION_LEGACY_INTAKE", "").strip().lower() in ("1", "true", "yes", "on")


async def _persist_petition_slots(ctx: FSMContext, merged: dict[str, str]) -> None:
    await ctx.update_data(**{k: (merged.get(k) or "").strip() for k in PETITION_SLOTS})


def _slots_from_data(data: Dict[str, Any]) -> dict[str, str]:
    return {k: (data.get(k) or "").strip() for k in PETITION_SLOTS}


async def _send_interview_preview(message: Message, state: FSMContext) -> None:
    await state.update_data(petition_legal_engine_safe_draft="")
    data = await state.get_data()
    lg = data.get("legal_goal")
    prev = format_petition_preview_for_user(str(lg or ""), _slots_from_data(data))
    await _answer_plain_chunks(message, prev)
    await state.set_state(PetitionStates.confirm)


async def _send_interview_preview_safe(
    message: Message, state: FSMContext, policy_dec, lg: str
) -> None:
    snap = await state.get_data()
    sid_sd = (snap.get(FSM_SCENARIO_ID_KEY) or "").strip() or SCENARIO_PETITION_CIVIL
    emit_telemetry_safe_draft_selected(
        scenario_id=sid_sd,
        feature=_petition_telemetry_feature(sid_sd),
    )
    await state.update_data(petition_legal_engine_safe_draft="1")
    data = await state.get_data()
    notice = format_petition_safe_draft_notice(policy_dec, lg)
    prev = format_petition_preview_for_user(lg, _slots_from_data(data))
    await _answer_plain_chunks(message, notice + "\n\n" + prev)
    await state.set_state(PetitionStates.confirm)


# =====================================================
# START
# =====================================================

@router.message(Command("petition"))
@router.message(F.text.func(lambda text: main_menu_button_matches(text, BTN_PETITION, "petition")))
async def petitions_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PetitionStates.legal_goal)
    await state.update_data(
        **{
            FSM_ACTIVE_SCENARIO: SCENARIO_PETITION,
            FSM_ACTIVE_FEATURE: FEATURE_PETITION,
            FSM_SCENARIO_ID_KEY: "",
        }
    )
    await message.answer(_GATE_TEXT + "\n\n" + UX_RIBBON_PLAIN + free_tier_footer_plain(_uid(message)))


# =====================================================
# LEGAL QUALIFICATION GATE (A/B)
# =====================================================

@router.message(PetitionStates.legal_goal)
async def petitions_legal_goal(message: Message, state: FSMContext) -> None:
    choice = _normalize_ab(message.text or "")

    if choice in {"A", "B"}:
        lock = SCENARIO_PETITION_ADMIN if choice == "A" else SCENARIO_PETITION_CIVIL
        await state.update_data(legal_goal=choice, **{FSM_SCENARIO_ID_KEY: lock})
        if _petition_legacy_intake_enabled():
            await state.set_state(PetitionStates.addressee)
            if choice == "B":
                await message.answer(
                    "Укажите суд, в который подаётся иск — полное наименование, если знаете.\n"
                    "Если суд ещё не определён — «подлежит уточнению по подсудности» или город."
                )
            else:
                await message.answer(
                    "Укажите адресата — полное наименование административного суда "
                    "(ст. 102 АППК РК). Если неизвестно — город и «уточнить по подсудности»."
                )
            return

        await state.set_state(PetitionStates.free_story)
        uid = _uid(message)
        await message.answer(
            UX_FREE_NARRATIVE_INVITE_HTML
            + "\n\n"
            + UX_RIBBON_HTML
            + free_tier_footer_html(uid),
            parse_mode=ParseMode.HTML,
        )
        return

    await message.answer("Пожалуйста, укажите вариант: А или Б.")


# =====================================================
# INTERVIEW INTAKE (свободный рассказ → уточнения)
# =====================================================


@router.message(PetitionStates.free_story, F.text)
async def petitions_free_story(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < PETITION_MIN_STORY_CHARS:
        await message.answer(
            f"Сообщение слишком короткое (нужно хотя бы ~{PETITION_MIN_STORY_CHARS} символов). "
            "Опишите ситуацию одним связным текстом: стороны, что случилось, чего добиваетесь.",
            parse_mode=None,
        )
        return

    data = await state.get_data()
    lg = data.get("legal_goal")
    sid = (data.get(FSM_SCENARIO_ID_KEY) or "").strip()
    if lg not in {"A", "B"} or not sid:
        await state.clear()
        await message.answer("Сессия устарела. Начните снова: /petition", parse_mode=None)
        return

    await state.update_data(petition_raw_narrative=text)
    await message.answer("Разбираю текст и извлекаю факты…", parse_mode=None)

    try:
        merged, questions = await extract_petition_slots_from_story(text, str(lg))
    except Exception:
        logger.exception("petition intake extraction failed")
        merged, questions = {k: "" for k in PETITION_SLOTS}, []

    if not any((merged.get(k) or "").strip() for k in PETITION_SLOTS) and not questions:
        await message.answer(
            "Не удалось разобрать текст. Попробуйте перефразировать одним сообщением "
            "или включите линейный режим: переменная окружения PETITION_LEGACY_INTAKE=1 и перезапуск бота.",
            parse_mode=None,
        )
        return

    base = {k: "" for k in PETITION_SLOTS}
    merged_f = merge_petition_slot_updates(base, merged)
    await _persist_petition_slots(state, merged_f)

    data_for_policy = await state.get_data()
    sid = (data_for_policy.get(FSM_SCENARIO_ID_KEY) or "").strip()
    policy_dec = resolve_legal_engine_policy_decision(
        legal_engine_enabled(), sid, data_for_policy
    )
    if policy_dec is not None and policy_dec.action == "block":
        emit_telemetry_gate_blocked(
            scenario_id=sid,
            feature=_petition_telemetry_feature(sid),
            outcome_code="petition_policy_block",
        )
        await message.answer(
            format_petition_policy_block_message(policy_dec),
            parse_mode=None,
        )
        return

    if not petition_pipeline_ready(str(lg), merged_f):
        questions = merge_petition_clarify_queues_policy_first(
            legal_engine_enabled(),
            policy_dec,
            str(lg),
            questions,
        )
        if not questions:
            miss = petition_critical_missing(str(lg), merged_f)
            lbl = ", ".join(SLOT_LABEL_RU.get(m, m) for m in miss) if miss else "обязательные поля"
            await message.answer(
                f"Недостаточно данных для документа ({lbl}). Дополните рассказ одним сообщением.",
                parse_mode=None,
            )
            return

        emit_telemetry_clarify_selected(
            scenario_id=sid,
            feature=_petition_telemetry_feature(sid),
            clarify_depth=len(questions),
        )
        await state.update_data(
            petition_clarify_queue=questions,
            petition_clarify_index=0,
            petition_clarify_answers=[],
        )
        await state.set_state(PetitionStates.interview_clarify)
        await message.answer(
            f"Уточнение 1 из {len(questions)}\n\n{questions[0]}",
            parse_mode=None,
        )
        return

    if policy_dec is not None:
        pq_ready = policy_questions_for_petition_clarify(policy_dec, str(lg))
        branch = classify_ready_policy_branch(
            legal_engine_enabled(), policy_dec, pq_ready
        )
        if branch == ReadyPolicyBranch.CLARIFY_QUEUE and pq_ready:
            emit_telemetry_clarify_selected(
                scenario_id=sid,
                feature=_petition_telemetry_feature(sid),
                clarify_depth=len(pq_ready),
            )
            await state.update_data(
                petition_clarify_queue=pq_ready,
                petition_clarify_index=0,
                petition_clarify_answers=[],
            )
            await state.set_state(PetitionStates.interview_clarify)
            await message.answer(
                f"Уточнение 1 из {len(pq_ready)}\n\n{pq_ready[0]}",
                parse_mode=None,
            )
            return
        if branch == ReadyPolicyBranch.SAFE_DRAFT:
            await _send_interview_preview_safe(message, state, policy_dec, str(lg))
            return

    await _send_interview_preview(message, state)


@router.message(PetitionStates.interview_clarify, F.text)
async def petitions_interview_clarify(message: Message, state: FSMContext) -> None:
    reply = (message.text or "").strip()
    if not reply:
        await message.answer("Нужен текстовый ответ.", parse_mode=None)
        return

    data = await state.get_data()
    queue = list(data.get("petition_clarify_queue") or [])
    idx = int(data.get("petition_clarify_index") or 0)
    answers = list(data.get("petition_clarify_answers") or [])
    lg = str(data.get("legal_goal") or "")

    if idx >= len(queue):
        fresh = await state.get_data()
        cur = _slots_from_data(fresh)
        if petition_pipeline_ready(lg, cur):
            sid_q = (fresh.get(FSM_SCENARIO_ID_KEY) or "").strip()
            pd = resolve_legal_engine_policy_decision(
                legal_engine_enabled(), sid_q, fresh
            )
            if pd is not None and pd.action == "block":
                emit_telemetry_gate_blocked(
                    scenario_id=sid_q or SCENARIO_PETITION_CIVIL,
                    feature=_petition_telemetry_feature(sid_q or SCENARIO_PETITION_CIVIL),
                    outcome_code="petition_policy_block",
                )
                await message.answer(
                    format_petition_policy_block_message(pd),
                    parse_mode=None,
                )
                return
            pq0 = policy_questions_for_petition_clarify(pd, lg) if pd else []
            br0 = classify_ready_policy_branch(legal_engine_enabled(), pd, pq0)
            if br0 == ReadyPolicyBranch.CLARIFY_QUEUE and pq0:
                emit_telemetry_clarify_selected(
                    scenario_id=sid_q or SCENARIO_PETITION_CIVIL,
                    feature=_petition_telemetry_feature(sid_q or SCENARIO_PETITION_CIVIL),
                    clarify_depth=len(pq0),
                )
                await state.update_data(
                    petition_clarify_queue=pq0,
                    petition_clarify_index=0,
                    petition_clarify_answers=[],
                )
                await message.answer(
                    f"Уточнение 1 из {len(pq0)}\n\n{pq0[0]}",
                    parse_mode=None,
                )
                return
            if br0 == ReadyPolicyBranch.SAFE_DRAFT:
                await _send_interview_preview_safe(message, state, pd, lg)
                return
            await _send_interview_preview(message, state)
        else:
            await state.set_state(PetitionStates.free_story)
            await message.answer(
                "Очередь уточнений пуста или сессия сбита. Пришлите снова полный рассказ одним сообщением.",
                parse_mode=None,
            )
        return

    answers.append(reply)
    next_idx = idx + 1

    if next_idx < len(queue):
        await state.update_data(
            petition_clarify_index=next_idx,
            petition_clarify_answers=answers,
        )
        await message.answer(
            f"Уточнение {next_idx + 1} из {len(queue)}\n\n{queue[next_idx]}",
            parse_mode=None,
        )
        return

    blob = "\n\n".join(f"• {queue[i]}\n— {answers[i]}" for i in range(len(queue)))
    base_story = (data.get("petition_raw_narrative") or "").strip()
    cur_slots = _slots_from_data(data)
    slots_block = "\n".join(f"{k}: {v}" for k, v in cur_slots.items() if v)
    narrative = (base_story + "\n\n" if base_story else "") + slots_block + f"\n\nУТОЧНЕНИЯ:\n{blob}"

    try:
        merged_new, extra = await extract_petition_slots_from_story(narrative, lg)
    except Exception:
        logger.exception("petition clarify merge failed")
        merged_new, extra = {}, []

    merged_new = merge_petition_slot_updates(cur_slots, merged_new)
    await _persist_petition_slots(state, merged_new)
    await state.update_data(
        petition_clarify_queue=[],
        petition_clarify_index=0,
        petition_clarify_answers=[],
    )

    if petition_pipeline_ready(lg, merged_new):
        data_ok = await state.get_data()
        sid_ok = (data_ok.get(FSM_SCENARIO_ID_KEY) or "").strip()
        policy_ok = resolve_legal_engine_policy_decision(
            legal_engine_enabled(), sid_ok, data_ok
        )
        if policy_ok is not None and policy_ok.action == "block":
            emit_telemetry_gate_blocked(
                scenario_id=sid_ok,
                feature=_petition_telemetry_feature(sid_ok),
                outcome_code="petition_policy_block",
            )
            await message.answer(
                format_petition_policy_block_message(policy_ok),
                parse_mode=None,
            )
            return
        pq_ok = policy_questions_for_petition_clarify(policy_ok, lg) if policy_ok else []
        br_ok = classify_ready_policy_branch(
            legal_engine_enabled(), policy_ok, pq_ok
        )
        if br_ok == ReadyPolicyBranch.CLARIFY_QUEUE and pq_ok:
            emit_telemetry_clarify_selected(
                scenario_id=sid_ok,
                feature=_petition_telemetry_feature(sid_ok),
                clarify_depth=len(pq_ok),
            )
            await state.update_data(
                petition_clarify_queue=pq_ok,
                petition_clarify_index=0,
                petition_clarify_answers=[],
            )
            await message.answer(
                f"Уточнение 1 из {len(pq_ok)}\n\n{pq_ok[0]}",
                parse_mode=None,
            )
            return
        if br_ok == ReadyPolicyBranch.SAFE_DRAFT:
            await _send_interview_preview_safe(message, state, policy_ok, lg)
            return
        await _send_interview_preview(message, state)
        return

    extra = [e for e in extra if e][:3]
    data_x = await state.get_data()
    sid_x = (data_x.get(FSM_SCENARIO_ID_KEY) or "").strip()
    dec_x = resolve_legal_engine_policy_decision(
        legal_engine_enabled(), sid_x, data_x
    )
    if dec_x is not None and dec_x.action == "block":
        emit_telemetry_gate_blocked(
            scenario_id=sid_x,
            feature=_petition_telemetry_feature(sid_x),
            outcome_code="petition_policy_block",
        )
        await message.answer(
            format_petition_policy_block_message(dec_x),
            parse_mode=None,
        )
        return
    pq_x = policy_questions_for_petition_clarify(dec_x, lg) if dec_x else []
    extra = merge_clarify_queue_policy_first(
        legal_engine_enabled(), dec_x, extra, pq_x
    )
    if extra:
        emit_telemetry_clarify_selected(
            scenario_id=sid_x,
            feature=_petition_telemetry_feature(sid_x),
            clarify_depth=len(extra),
        )
        await state.update_data(
            petition_clarify_queue=extra,
            petition_clarify_index=0,
            petition_clarify_answers=[],
        )
        await state.set_state(PetitionStates.interview_clarify)
        await message.answer(
            f"Уточнение 1 из {len(extra)}\n\n{extra[0]}",
            parse_mode=None,
        )
        return

    await state.set_state(PetitionStates.free_story)
    miss = petition_critical_missing(lg, merged_new)
    lbl = ", ".join(SLOT_LABEL_RU.get(m, m) for m in miss) if miss else ""
    await message.answer(
        "После уточнений всё ещё не хватает обязательных полей"
        + (f" ({lbl})" if lbl else "")
        + ". Пришлите одним сообщением недостающее или полный рассказ заново.",
        parse_mode=None,
    )


# =====================================================
# FSM STEPS (legacy линейная анкета при PETITION_LEGACY_INTAKE)
# =====================================================

@router.message(PetitionStates.addressee)
async def petitions_addressee(message: Message, state: FSMContext) -> None:
    await state.update_data(addressee=(message.text or "").strip())
    await state.set_state(PetitionStates.applicant)
    data = await state.get_data()
    if data.get("legal_goal") == "A":
        await message.answer(
            "Введите ЗАЯВИТЕЛЯ (ФИО/наименование, ИИН/БИН при наличии):"
        )
    else:
        await message.answer(
            "Введите ИСТЦА: ФИО или наименование, при наличии ИИН/БИН и **адрес** "
            "(для шапки иска)."
        )


@router.message(PetitionStates.applicant)
async def petitions_applicant(message: Message, state: FSMContext) -> None:
    await state.update_data(applicant=(message.text or "").strip())
    await state.set_state(PetitionStates.opponent)
    data = await state.get_data()
    if data.get("legal_goal") == "A":
        await message.answer(
            "Введите заинтересованную сторону / оппонента по делу (если есть) "
            "или напишите «нет»:"
        )
    else:
        await message.answer(
            "Введите ОТВЕТЧИКА: наименование или ФИО, при наличии ИИН/БИН и **полный адрес** "
            "(для иска ответчик обязателен)."
        )


@router.message(PetitionStates.opponent)
async def petitions_opponent(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    data = await state.get_data()
    is_lawsuit = data.get("legal_goal") == "B"
    if is_lawsuit:
        if not txt or txt.lower() in {"нет", "не", "нету", "-"}:
            await message.answer(
                "Для искового заявления ответчик обязателен. Укажите наименование/ФИО и адрес ответчика."
            )
            return
        opponent = txt
    else:
        opponent = "" if txt.lower() in {"нет", "не", "нету", "-"} else txt
    await state.update_data(opponent=opponent)
    await state.set_state(PetitionStates.situation)
    await message.answer("Опишите СУТЬ СИТУАЦИИ (факты):")


@router.message(PetitionStates.situation)
async def petitions_situation(message: Message, state: FSMContext) -> None:
    await state.update_data(situation=(message.text or "").strip())
    await state.set_state(PetitionStates.requests)
    data = await state.get_data()
    if data.get("legal_goal") == "A":
        await message.answer(
            "Опишите, ЧТО ВЫ ПРОСИТЕ У ОРГАНА (действия, обязать, оспорить и т.д.):"
        )
    else:
        await message.answer("Опишите ИСКОВЫЕ ТРЕБОВАНИЯ:")


@router.message(PetitionStates.requests)
async def petitions_requests(message: Message, state: FSMContext) -> None:
    await state.update_data(requests=(message.text or "").strip())
    await state.set_state(PetitionStates.evidence)
    await message.answer("Перечислите ДОКАЗАТЕЛЬСТВА или напишите «нет»:")


@router.message(PetitionStates.evidence)
async def petitions_evidence(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    evidence = "" if txt.lower() in {"нет", "не", "нету", "-"} else txt
    await state.update_data(evidence=evidence)
    await state.set_state(PetitionStates.attachments)
    await message.answer("Перечислите ПРИЛОЖЕНИЯ или напишите «нет»:")


@router.message(PetitionStates.attachments)
async def petitions_attachments(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    attachments = "" if txt.lower() in {"нет", "не", "нету", "-"} else txt
    await state.update_data(attachments=attachments)
    await state.set_state(PetitionStates.confirm)

    data = await state.get_data()
    legal_goal = data.get("legal_goal")

    if legal_goal == "A":
        preview = (
            "Проверьте данные:\n\n"
            f"ТИП ДОКУМЕНТА: {_doc_label(legal_goal)}\n"
            f"АДРЕСАТ: {data.get('addressee')}\n"
            f"ЗАЯВИТЕЛЬ: {data.get('applicant')}\n"
            f"ИНАЯ СТОРОНА / ОППОНЕНТ: {data.get('opponent') or 'не указана'}\n\n"
            f"СИТУАЦИЯ:\n{data.get('situation')}\n\n"
            f"ПРОСИМОЕ:\n{data.get('requests')}\n\n"
            "Напишите: «да» — сформировать, «нет» — отмена."
        )
    else:
        preview = (
            "Проверьте данные:\n\n"
            f"ТИП ДОКУМЕНТА: {_doc_label(legal_goal)}\n"
            f"СУД / ИНСТАНЦИЯ: {data.get('addressee')}\n"
            f"ИСТЕЦ: {data.get('applicant')}\n"
            f"ОТВЕТЧИК: {data.get('opponent') or 'не указан'}\n\n"
            f"СИТУАЦИЯ:\n{data.get('situation')}\n\n"
            f"ИСКОВЫЕ ТРЕБОВАНИЯ:\n{data.get('requests')}\n\n"
            "Напишите: «да» — сформировать, «нет» — отмена."
        )
    await _answer_plain_chunks(message, preview)


# =====================================================
# CONFIRM + PIPELINE DISPATCH
# =====================================================

@router.message(PetitionStates.confirm)
async def petitions_confirm(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip().lower()

    if txt in {"нет", "no", "отмена", "cancel"}:
        await state.clear()
        await message.answer(UX_AFTER_CANCEL_HTML, parse_mode=ParseMode.HTML)
        return

    if txt not in {"да", "yes", "ок", "ok"}:
        await message.answer(
            "Напишите «да» для генерации или «нет» для отмены."
        )
        return

    data: Dict[str, Any] = await state.get_data()
    if scenario_mismatch_for_petition(data):
        await state.clear()
        await message.answer(
            "Это не сценарий «Заявление / иск». Выберите «📝 Заявление (ГПО / Адм)» в меню "
            "или «💬 Консультация» для правового разъяснения.",
            parse_mode=None,
        )
        return

    legal_goal = data.get("legal_goal")
    sid = (data.get(FSM_SCENARIO_ID_KEY) or "").strip()
    if legal_goal == "A" and sid != SCENARIO_PETITION_ADMIN:
        await state.clear()
        await message.answer(
            "Сессия заявления не согласована (ожидался административный режим). Начните сценарий заново через меню.",
            parse_mode=None,
        )
        return
    if legal_goal == "B" and sid != SCENARIO_PETITION_CIVIL:
        await state.clear()
        await message.answer(
            "Сессия иска не согласована (ожидался гражданский иск). Начните сценарий заново через меню.",
            parse_mode=None,
        )
        return

    slot_map = _slots_from_data(data)
    if legal_goal in {"A", "B"} and not petition_pipeline_ready(str(legal_goal), slot_map):
        miss = petition_critical_missing(str(legal_goal), slot_map)
        lbl = ", ".join(SLOT_LABEL_RU.get(m, m) for m in miss) if miss else "обязательные поля"
        await message.answer(
            f"Нельзя сформировать документ: не заполнены обязательные сведения ({lbl}). "
            "В режиме интервью заново опишите ситуацию в открытом сообщении или начните сценарий заново: /petition",
            parse_mode=None,
        )
        return

    blocked, pol = legal_engine_should_block_generation(
        legal_engine_enabled(), sid, data
    )
    if blocked and pol is not None:
        await message.answer(
            format_petition_policy_block_message(pol),
            parse_mode=None,
        )
        return

    uid = _uid(message)
    ok, wall = assert_can_deliver_result(uid)
    if not ok:
        await message.answer(wall, parse_mode=ParseMode.HTML)
        return

    progress_msg = await message.answer(
        f"{UX_BEFORE_GENERATION_HTML}\n\n"
        "⏳ Формирую документ… Это может занять 1–2 минуты."
        + free_tier_footer_html(uid),
        parse_mode=ParseMode.HTML,
    )

    try:
        if legal_goal == "A":
            result = await generate_petition(data)
        elif legal_goal == "B":
            result = await generate_civil_lawsuit(data)
        else:
            raise RuntimeError("Неизвестный процессуальный тип документа")
    except Exception as e:
        await state.clear()
        try:
            await progress_msg.edit_text(
                "❌ Ошибка формирования документа."
            )
        except Exception:
            pass
        await _answer_plain_chunks(
            message,
            _safe_tg_text(f"❌ Ошибка формирования документа:\n{e}", TG_PLAIN_CHUNK),
        )
        return

    docx_path = result.get("docx")
    if not docx_path:
        await state.clear()
        try:
            await progress_msg.edit_text(
                "❌ Не удалось сформировать файл."
            )
        except Exception:
            pass
        await message.answer("❌ Не удалось сформировать файл.")
        return

    try:
        await progress_msg.edit_text("✅ Документ сформирован.")
    except Exception:
        await message.answer("✅ Документ сформирован.")

    preview_text = result.get("text", "") or ""
    if preview_text.strip():
        await _answer_plain_chunks(message, preview_text)

    caption = "📄 " + _doc_label(legal_goal) + " — полный текст в DOCX"

    await message.answer_document(
        FSInputFile(docx_path),
        caption=caption,
    )

    record_completed_result(uid)
    await state.clear()
