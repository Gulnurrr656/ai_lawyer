# app/features/contracts/handlers.py

from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.features.contracts import states
from app.features.contracts.pipeline import generate_contract

# ✅ СЦЕНАРИИ ИМПОРТИРУЕМ ЗДЕСЬ (ЕДИНСТВЕННОЕ МЕСТО)
from app.features.contracts.scenarios import (
    RENT_SCENARIO,
    SERVICE_SCENARIO,
    SUBCONTRACT_SCENARIO,
    SUPPLY_SCENARIO,
    MANUFACTURE_SCENARIO,
)

router = Router(name="contracts")

SESSION_KEY = "contract_session"


# =====================================================
# SCENARIO REGISTRY
# =====================================================

SCENARIOS = {
    "rent": RENT_SCENARIO,
    "service": SERVICE_SCENARIO,
    "subcontract": SUBCONTRACT_SCENARIO,
    "supply": SUPPLY_SCENARIO,
    "manufacture": MANUFACTURE_SCENARIO,
}


def get_scenario(profile: str):
    return SCENARIOS[profile]


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


async def _save_session(ctx: FSMContext, session: dict) -> None:
    await ctx.update_data(**{SESSION_KEY: session})


# =====================================================
# ENTRYPOINT
# =====================================================

@router.message(F.text == "📄 Договор")
async def contract_entry(message: Message, state: FSMContext):
    session = states.new_session()
    await state.update_data(**{SESSION_KEY: session})
    await message.answer(states.render_type_menu())


# =====================================================
# GLOBAL COMMANDS
# =====================================================

@router.message(lambda m: _low(m) in {"отмена", "cancel", "/cancel", "стоп"})
async def on_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Сценарий договора отменён.")


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
    text = _text(message)
    low = text.lower()
    if not text:
        return

    data = await state.get_data()
    session = data.get(SESSION_KEY)
    if not session:
        return

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

        q = get_current_question(session)
        await message.answer(
            render_question(
                q,
                step_no=1,
                total=len(get_scenario(profile)),
            )
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

        await message.answer("⏳ Формирую договор…")

        try:
            result = await generate_contract(facts)
        except Exception as e:
            await message.answer(f"❌ Ошибка генерации:\n{e}")
            await state.clear()
            return

        await state.clear()

        if result.get("text"):
            await message.answer(result["text"])
        if result.get("docx"):
            await message.answer_document(result["docx"])

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