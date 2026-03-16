from __future__ import annotations

from typing import Any, Dict

from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext

from .states import PetitionStates
from .pipeline_admin import generate_petition
from .pipeline_claim import generate_claim

router = Router()

_TG_MAX_CHARS = 3500


def _safe_preview(text: str, limit: int = _TG_MAX_CHARS) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n…(полный текст в DOCX)"


_GATE_TEXT = (
    "⚖️ УТОЧНЕНИЕ ПРОЦЕССУАЛЬНОЙ ФОРМЫ\n\n"
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

    # A — административное заявление
    if s in {"a", "а"}:
        return "A"
    if "адм" in s or "администра" in s:
        return "A"
    if "оспор" in s or "незакон" in s or "госорган" in s:
        return "A"
    if s == "заявление" or "заявлен" in s:
        return "A"

    # B — исковое заявление (ГПО)
    if s in {"b", "б"}:
        return "B"
    if "иск" in s or "исков" in s:
        return "B"
    if "гпо" in s:
        return "B"
    if "взыск" in s or "деньг" in s or "ден" in s or "убыт" in s or "долг" in s:
        return "B"

    return None


def _doc_label(legal_goal: str | None) -> str:
    return (
        "Административное заявление (АДМ)"
        if legal_goal == "A"
        else "Исковое заявление (ГПО)"
    )


# =====================================================
# START
# =====================================================

@router.message(F.text.lower().contains("заявление"))
async def petitions_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PetitionStates.legal_goal)
    await message.answer(_GATE_TEXT)


# =====================================================
# LEGAL QUALIFICATION GATE (A/B)
# =====================================================

@router.message(PetitionStates.legal_goal)
async def petitions_legal_goal(message: Message, state: FSMContext) -> None:
    choice = _normalize_ab(message.text or "")

    if choice in {"A", "B"}:
        await state.update_data(legal_goal=choice)
        await state.set_state(PetitionStates.addressee)
        await message.answer("Введите АДРЕСАТА (орган/суд/инстанция):")
        return

    await message.answer("Пожалуйста, укажите вариант: А или Б.")


# =====================================================
# FSM STEPS
# =====================================================

@router.message(PetitionStates.addressee)
async def petitions_addressee(message: Message, state: FSMContext) -> None:
    await state.update_data(addressee=(message.text or "").strip())
    await state.set_state(PetitionStates.applicant)
    await message.answer(
        "Введите ЗАЯВИТЕЛЯ / ИСТЦА (ФИО/наименование, ИИН/БИН при наличии):"
    )


@router.message(PetitionStates.applicant)
async def petitions_applicant(message: Message, state: FSMContext) -> None:
    await state.update_data(applicant=(message.text or "").strip())
    await state.set_state(PetitionStates.opponent)
    await message.answer(
        "Введите ВТОРУЮ СТОРОНУ / ОТВЕТЧИКА (если есть) или напишите «нет»:"
    )


@router.message(PetitionStates.opponent)
async def petitions_opponent(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    opponent = "" if txt.lower() in {"нет", "не", "нету", "-"} else txt
    await state.update_data(opponent=opponent)
    await state.set_state(PetitionStates.situation)
    await message.answer("Опишите СУТЬ СИТУАЦИИ (факты):")


@router.message(PetitionStates.situation)
async def petitions_situation(message: Message, state: FSMContext) -> None:
    await state.update_data(situation=(message.text or "").strip())
    await state.set_state(PetitionStates.requests)
    await message.answer(
        "Опишите ПРОСИМОЕ ДЕЙСТВИЕ / ИСКОВЫЕ ТРЕБОВАНИЯ:"
    )


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

    preview = (
        "Проверьте данные:\n\n"
        f"ТИП ДОКУМЕНТА: {_doc_label(legal_goal)}\n"
        f"АДРЕСАТ: {data.get('addressee')}\n"
        f"СТОРОНА 1: {data.get('applicant')}\n"
        f"СТОРОНА 2: {data.get('opponent') or 'не указана'}\n\n"
        f"СИТУАЦИЯ:\n{data.get('situation')}\n\n"
        f"ТРЕБОВАНИЯ:\n{data.get('requests')}\n\n"
        "Напишите: «да» — сформировать, «нет» — отмена."
    )
    await message.answer(preview)


# =====================================================
# CONFIRM + PIPELINE DISPATCH
# =====================================================

@router.message(PetitionStates.confirm)
async def petitions_confirm(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip().lower()

    if txt in {"нет", "no", "отмена", "cancel"}:
        await state.clear()
        await message.answer("❌ Отменено.")
        return

    if txt not in {"да", "yes", "ок", "ok"}:
        await message.answer(
            "Напишите «да» для генерации или «нет» для отмены."
        )
        return

    data: Dict[str, Any] = await state.get_data()
    legal_goal = data.get("legal_goal")

    progress_msg = await message.answer(
        "⏳ Формирую документ… Это может занять 1–2 минуты."
    )

    try:
        if legal_goal == "A":
            result = await generate_petition(data)
        elif legal_goal == "B":
            result = await generate_claim(data)
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
        await message.answer(
            f"❌ Ошибка формирования документа:\n{e}"
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

    preview_text = _safe_preview(result.get("text", ""))
    if preview_text:
        await message.answer(preview_text)

    caption = "📄 " + _doc_label(legal_goal) + " — полный текст в DOCX"

    await message.answer_document(
        FSInputFile(docx_path),
        caption=caption,
    )

    await state.clear()