# app/features/contracts/handlers.py

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile, Message
from aiogram.fsm.context import FSMContext

from app.features.contracts import states
from app.features.contracts.pipeline import generate_contract

# ✅ СЦЕНАРИИ ИМПОРТИРУЕМ ЗДЕСЬ (ЕДИНСТВЕННОЕ МЕСТО)
from app.shared.main_menu import BTN_CONTRACT, main_menu_button_matches
from app.shared.fsm_scenario import (
    FSM_ACTIVE_FEATURE,
    FSM_ACTIVE_SCENARIO,
    FSM_SCENARIO_ID_KEY,
    FEATURE_CONTRACT,
    SCENARIO_CONTRACT,
    scenario_mismatch_for_contract,
)
from app.shared.scenario_registry import register_contract_scenario

from app.features.contracts import intake_config
from app.features.contracts.scenarios import LEGACY_SCENARIOS, SHORT_SCENARIOS
from app.shared.demo_messaging import (
    friendly_contract_generation_message,
    friendly_docx_send_failure_message,
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
    UX_FREE_NARRATIVE_INVITE_PLAIN,
    UX_RIBBON_PLAIN,
)

router = Router(name="contracts")
logger = logging.getLogger(__name__)

SESSION_KEY = "contract_session"


# =====================================================
# SCENARIO REGISTRY
# =====================================================

def get_scenario(profile: str):
    if intake_config.use_short_intake():
        return SHORT_SCENARIOS[profile]
    return LEGACY_SCENARIOS[profile]


def get_current_question(session: dict):
    scenario = get_scenario(session["profile_key"])
    idx = session["step_idx"]
    if idx >= len(scenario):
        return None
    return scenario[idx]


def is_done(session: dict) -> bool:
    scenario = get_scenario(session["profile_key"])
    return session["step_idx"] >= len(scenario)


def render_question(q, step_no: int, total: int) -> str:
    lines = [
        f"📌 Вопрос {step_no} из {total}",
        f"<b>{q.title}</b>",
        "",
        q.prompt,
    ]
    return "\n".join(lines)


# =====================================================
# HELPERS
# =====================================================

def _text(msg: Message) -> str:
    return (msg.text or "").strip()


def _low(msg: Message) -> str:
    return _text(msg).lower()


def _uid(m: Message) -> int | None:
    return m.from_user.id if m.from_user else None


async def _save_session(ctx: FSMContext, session: dict) -> None:
    await ctx.update_data(**{SESSION_KEY: session})


# =====================================================
# ENTRYPOINT
# =====================================================

@router.message(F.text.func(lambda text: main_menu_button_matches(text, BTN_CONTRACT, "contract", "dogovor")))
async def contract_entry(message: Message, state: FSMContext):
    await state.clear()
    session = states.new_session()
    await state.update_data(
        **{
            SESSION_KEY: session,
            FSM_ACTIVE_FEATURE: FEATURE_CONTRACT,
            FSM_ACTIVE_SCENARIO: SCENARIO_CONTRACT,
            FSM_SCENARIO_ID_KEY: "",
        }
    )
    await message.answer(
        states.render_type_menu()
        + "\n\n"
        + UX_RIBBON_PLAIN
        + free_tier_footer_plain(_uid(message)),
    )


# =====================================================
# GLOBAL COMMANDS
# =====================================================

@router.message(lambda m: _low(m) in {"отмена", "cancel", "/cancel", "стоп"})
async def on_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(UX_AFTER_CANCEL_HTML, parse_mode=ParseMode.HTML)


@router.message(lambda m: _low(m) == "назад")
async def on_back(message: Message, state: FSMContext):
    data = await state.get_data()
    session = data.get(SESSION_KEY)
    if not session or not session.get("profile_key"):
        await message.answer(states.render_type_menu())
        return

    states.go_back(session)
    await _save_session(state, session)

    q = get_current_question(session)
    if not q:
        await message.answer(states.render_type_menu())
        return

    await message.answer(
        render_question(
            q,
            step_no=session["step_idx"] + 1,
            total=len(get_scenario(session["profile_key"])),
        )
    )


# =====================================================
# MAIN FSM FLOW
# =====================================================

@router.message()
async def contract_flow(message: Message, state: FSMContext):
    data = await state.get_data()
    session = data.get(SESSION_KEY)
    if not session:
        # Без активной сессии этот fallback не должен потреблять апдейт —
        # иначе не доходят petitions/claims/consult/bankruptcy/analyze.
        raise SkipHandler()

    text = _text(message)
    low = text.lower()
    if not text:
        raise SkipHandler()

    # -------------------------------------------------
    # 1) ВЫБОР ТИПА ДОГОВОРА
    # -------------------------------------------------
    if not session.get("profile_key"):
        profile = states.normalize_contract_type(text)
        if not profile:
            await message.answer(
                "❗ Не распознал тип договора.\n\n" + states.render_type_menu()
            )
            return

        states.set_profile(session, profile)
        await _save_session(state, session)
        await state.update_data(**{FSM_SCENARIO_ID_KEY: register_contract_scenario(profile)})

        q = get_current_question(session)
        await message.answer(
            render_question(
                q,
                step_no=1,
                total=len(get_scenario(profile)),
            )
            + "\n\n"
            + UX_FREE_NARRATIVE_INVITE_PLAIN
        )
        return

    # -------------------------------------------------
    # 2) ТЕКУЩИЙ ВОПРОС
    # -------------------------------------------------
    q = get_current_question(session)
    if not q:
        await message.answer("⚠️ Сценарий повреждён.")
        await state.clear()
        return

    if q.key == "confirm" and low not in {"подтвердить", "подтверждаю", "ok", "да"}:
        await message.answer("❗ Напишите «подтвердить» для генерации договора.")
        return

    value, err = q.parser(text)
    if err:
        await message.answer(f"❗ {err}")
        return

    states.store_answer(session, q.key, value)
    states.advance(session)
    await _save_session(state, session)

    # -------------------------------------------------
    # 3) КОНЕЦ → PIPELINE
    # -------------------------------------------------
    if is_done(session):
        facts = states.build_facts_from_answers(session)
        top = await state.get_data()
        if scenario_mismatch_for_contract(top):
            await message.answer(
                "⚠️ Активен другой сценарий. Договор — только через кнопку «Договор» в меню."
            )
            return
        _sid = top.get(FSM_SCENARIO_ID_KEY)
        _feat = top.get(FSM_ACTIVE_FEATURE)
        if _sid:
            facts[FSM_SCENARIO_ID_KEY] = _sid
        if _feat:
            facts[FSM_ACTIVE_FEATURE] = _feat

        uid = _uid(message)
        ok, wall = assert_can_deliver_result(uid)
        if not ok:
            await message.answer(wall, parse_mode=ParseMode.HTML)
            return

        await message.answer(
            f"{UX_BEFORE_GENERATION_HTML}\n\n⏳ Формирую договор…" + free_tier_footer_html(uid),
            parse_mode=ParseMode.HTML,
        )

        try:
            result = await generate_contract(facts)
        except Exception as e:
            logger.exception("contract generation failed")
            await message.answer(friendly_contract_generation_message(e))
            await state.clear()
            return

        await state.clear()

        preview = (result.get("text") or "").strip()
        norms = (result.get("rag_sources_summary") or "").strip()
        # Лимит Telegram ~4096; превью договора + список норм не должны резаться посередине без смысла.
        _tg_body_limit = 4000
        if preview and norms:
            combined = f"{preview}\n\n{norms}"
            if len(combined) <= _tg_body_limit:
                await message.answer(combined)
            else:
                await message.answer(preview)
                await message.answer(norms)
        elif preview:
            await message.answer(preview)
        elif norms:
            await message.answer(norms)

        docx_path = result.get("docx")
        if docx_path:
            try:
                await message.answer_document(FSInputFile(docx_path))
            except Exception:
                logger.exception("contract docx telegram send failed | path=%s", docx_path)
                await message.answer(friendly_docx_send_failure_message())

        if preview or norms or docx_path:
            record_completed_result(uid)
        return

    # -------------------------------------------------
    # 4) СЛЕДУЮЩИЙ ВОПРОС
    # -------------------------------------------------
    next_q = get_current_question(session)
    await message.answer(
        render_question(
            next_q,
            step_no=session["step_idx"] + 1,
            total=len(get_scenario(session["profile_key"])),
        )
    )
