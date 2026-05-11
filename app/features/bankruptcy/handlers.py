import html
from pathlib import Path

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message
from aiogram.fsm.context import FSMContext

from app.shared.main_menu import BTN_BANKRUPTCY, main_menu_button_matches
from app.shared.fsm_scenario import (
    FSM_ACTIVE_FEATURE,
    FSM_ACTIVE_SCENARIO,
    FSM_SCENARIO_ID_KEY,
    FEATURE_BANKRUPTCY,
    SCENARIO_BANKRUPTCY,
    scenario_mismatch_for_bankruptcy,
)
from app.shared.scenario_registry import scenario_id_for_bankruptcy_route
from app.shared.telegram_chunks import split_text_to_html_chunks_for_telegram
from app.shared.free_usage import assert_can_deliver_result, free_tier_footer_html, record_completed_result
from app.shared.ux_copy import UX_AFTER_BRANCH_HTML, UX_BEFORE_GENERATION_HTML, UX_RIBBON_HTML

from .bankruptcy_qualification import (
    BANKRUPTCY_INTAKE_KEYS,
    BANKRUPTCY_LEGACY_KEYS,
    _misplaced_field_label_ru,
    apply_bankruptcy_session_migrations,
    build_preliminary_qualification,
    evaluate_application_draft_gate,
    first_incomplete_intake_field,
    followup_menu_text_html,
    format_qualification_telegram_html,
    infer_subject_kind,
    merge_legacy_bankruptcy_fields,
    next_step_menu_text_html,
    parse_output_focus,
    resolved_subject_kind_for_qualification,
    suggest_misplaced_intake_block,
)
from .pipeline import assess_bankruptcy_case, generate_bankruptcy_result
from .states import BankruptcyStates

router = Router()

_TELEGRAM_PREVIEW_CHARS = 3600


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

SUMMARY_REJECT_WORDS = {
    "нет",
    "не верно",
    "неверно",
    "ошибка",
    "исправить",
    "не так",
    "подправить",
    "неправильно",
    "не согласен",
    "не согласна",
    "исправление",
    "редактировать",
}

MISPLACED_YES = {"да", "да.", "yes", "y", "lf", "ок", "ок.", "ага", "угу"}
MISPLACED_NO = {"нет", "нет.", "no", "не", "неа", "не-а"}

_GENERATION_BUSY_HTML = (
    "Сейчас формирую ответ по выбранному пункту.\n"
    "Дождитесь сообщения с материалом или начните заново: /bankruptcy"
)


def _opt(text: str) -> str:
    t = (text or "").strip()
    if t.lower() in {
        "нет",
        "нету",
        "no",
        "-",
        "не требуется",
        "отсутствует",
        "не знаю",
        "н/д",
    }:
        return ""
    return t


def _preserved_no(text: str) -> str:
    """«Нет» сохраняем текстом — чтобы отличать от пустого ответа в safety-гейтах."""
    t = (text or "").strip()
    low = t.lower()
    if low in {
        "нет",
        "нету",
        "no",
        "-",
        "не требуется",
        "отсутствует",
        "не знаю",
        "н/д",
        "ничего",
    }:
        return "нет"
    return t


def _session_payload_from_raw(raw: dict) -> dict:
    out: dict = {}
    for k in BANKRUPTCY_INTAKE_KEYS:
        v = raw.get(k)
        out[k] = v if v is not None else ""
    for k in BANKRUPTCY_LEGACY_KEYS:
        v = raw.get(k)
        if v is not None and str(v).strip():
            out[k] = str(v).strip()
    return out


_CAUTIONS_FOOTER = (
    "\n\n<b>Не делайте без юриста:</b> отчуждение активов, крупные подарки/займы родственникам, "
    "лживые сведения перед органом или судом."
)

_ROUTE_SUMMARY_RU = {
    "individual": "физическое лицо",
    "sole_prop": "ИП",
    "company": "ТОО / юрлицо",
}


def _parse_clarify_subject_route(text: str) -> str | None:
    """Возвращает canonical subject_route или None."""
    t = (text or "").strip().lower()
    if t in ("1", "фл", "физ", "физлицо", "гражданин", "частник"):
        return "individual"
    if t in ("2", "ип", "кәсіпкер", "предприниматель"):
        return "sole_prop"
    if t in ("3", "тоо", "юл", "юрлицо", "компания", "llp"):
        return "company"
    return None


def _html_debt_map(route: str) -> str:
    core = (
        "<b>Карта долгов</b>\n"
        "По каждому обязательству: <b>кому</b>, <b>сумма</b> (или вилка), <b>основание</b> "
        "(договор, расписка, налог, ЖКХ, зарплата, банк, МФО), <b>спорите ли</b>, "
        "исполнительный лист / решение суда — по возможности.\n\n"
    )
    if route == "sole_prop":
        return (
            core + "<b>Для ИП:</b> отдельно обозначьте, что к <b>деятельности ИП</b>, а что к <b>личным</b> обязательствам."
        )
    if route == "company":
        return (
            core + "<b>Для ТОО:</b> долги <b>организации</b> и отдельно личные (поручительство, расписка учредителя и т.п.) — по возможности раздельными блоками."
        )
    return core + (
        "<b>Для физлица:</b> если есть долги «как у учредителя/поручителя» по компании — отметьте отдельной строкой."
    )


def _html_ip_business_status() -> str:
    return (
        "<b>Статус и деятельность ИП</b> (идентификация предпринимателя)\n"
        "• <b>ИИН</b>, город регистрации ИП, основной вид деятельности (кратко);\n"
        "• есть ли <b>наёмные</b> (порядок численности);\n"
        "• режим налогообложения / спецрежим — если знаете;\n"
        "• ведёте ли раздельно личные и предпринимательские долги и расчёты на практике;\n"
        "• отрасль или ключевые контрагенты — если важно.\n"
        "Незнакомые пункты — «н/д»."
    )


def _html_company_identification() -> str:
    return (
        "<b>Идентификация компании и ваш статус</b>\n"
        "• <b>наименование</b> и <b>БИН</b> ТОО (если можете);\n"
        "• ваша <b>роль</b> (учредитель, директор, единоличный исполнительный орган и т.д.) и <b>доля</b>;\n"
        "• кратко — когда и в каком регионе зарегистрирована организация, если важно.\n"
        "Только факты."
    )


def _html_company_finance() -> str:
    return (
        "<b>Финансовое состояние организации</b>\n"
        "• <b>выручка / оборот</b>, прибыль или убыток (вилка, период) — по вашим данным;\n"
        "• достаточно ли денежного потока на текущие обязательства;\n"
        "• основные <b>кредиторы</b> по делу (кроме уже перечисленных в карте долгов) и просрочки;\n"
        "• дебиторская задолженность / «замороженные» активы — если есть.\n"
        "Если не ведёте учёт — напишите честно «ориентировочно»."
    )


def _html_company_employees_budget() -> str:
    return (
        "<b>Персонал и платежи в бюджет</b>\n"
        "• численность, задолженность по <b>заработной плате</b> и удержаниям;\n"
        "• задолженность перед <b>бюджетом</b> (налоги, соц. платежи) — по известному;\n"
        "• проверки/акты контролирующих органов — если релевантно (фактами).\n"
        "Если нет — «нет»."
    )


def _html_company_controllers() -> str:
    return (
        "<b>Контроль и связанные лица</b>\n"
        "• кто фактически <b>принимает решения</b> по компании (кроме формального директора), если отличается;\n"
        "• аффилированные / «дружественные» компании, взаимные займы с группой;\n"
        "• супруг(а) или родственники как учредители/контрагенты — если есть.\n"
        "Без оценки правомерности — только обстоятельства."
    )


def _html_risk_checklist(route: str) -> str:
    base = (
        "<b>Риски и сделки</b> (общий обязательный блок — ответьте по пунктам или «нет»):\n"
        "• <b>спорные долги</b> или оспариваемые суммы;\n"
        "• долги по <b>распискам</b> / физлицам;\n"
        "• сделки с <b>родственниками</b> или аффилированными лицами, займы им/от них;\n"
        "• <b>продажа/дарение</b> имущества за последние ~1–3 года;\n"
        "• крупные или необычные <b>переводы и платежи</b>;\n"
        "• опасения по <b>сокрытию</b> имущества или дохода (только как описание ситуации);\n"
        "• что важно по <b>исполнительному производству</b>, если ещё не сказали;\n"
        "• <b>реструктуризация / отказ</b> кредиторов — если ещё не отражено.\n"
        "Если по пункту ничего — пишите «нет»."
    )
    if route == "company":
        return base + (
            "\n<b>Для ТОО:</b> отдельно кратко — крупные операции компании с учредителями и связанными лицами."
        )
    return base


def _html_ip_taxes_creditors() -> str:
    return (
        "<b>Налоги и кредиторы по деятельности ИП</b>\n"
        "• задолженность перед <b>бюджетом</b> и соц. платежи;\n"
        "• претензии ключевых <b>контрагентов</b> по договорам (поставка, услуги, аренда);\n"
        "• налоговые/трудовые проверки — если были.\n"
        "Если не применимо — «нет»."
    )


def _html_income(route: str) -> str:
    if route == "sole_prop":
        return (
            "<b>Доходы</b>\n"
            "Доходы от деятельности ИП (вилка, стабильность) и при необоходимости личный/семейный бюджет при смешанных долгах."
        )
    return (
        "<b>Доходы</b>\n"
        "Личный и семейный бюджет, источники, стабильность."
    )


def _html_family(route: str) -> str:
    if route == "sole_prop":
        return (
            "<b>Семья и иждивенцы</b>\n"
            "Состав, иждивенцы; пересечение с долгами ИП/личными. Если только вы — «нет семьи» / «н/п»."
        )
    return (
        "<b>Семья и иждивенцы</b>\n"
        "Состав, несовершеннолетние, иждивенцы; кратко брачный режим / совместное имущество, если важно для долгов. "
        "Если только вы — «нет семьи» или «н/п»."
    )


def _html_assets(route: str) -> str:
    if route == "company":
        return (
            "<b>Имущество</b>\n"
            "<b>ТОО:</b> основные активы (ОС, товар, дебиторка), залоги. "
            "<b>Личное</b> учредителей — отдельно при поручительстве или смешении. Если нет — «нет»."
        )
    if route == "sole_prop":
        return (
            "<b>Имущество</b>\n"
            "Имущество <b>ИП</b> (товар, оборудование, транспорт) и <b>личное</b>; залоги, ипотека. Если нет — «нет»."
        )
    return (
        "<b>Имущество</b>\n"
        "Недвижимость, транспорт, доли, вклады; залоги, ипотека, совместная собственность. Если нет — «нет»."
    )


def _html_enforcement(route: str) -> str:
    if route == "company":
        return (
            "<b>Исполнительное производство</b>\n"
            "В отношении <b>ТОО</b> и <b>вас лично</b> (если есть): номера ИП, аресты, ограничения. Если нет — «нет»."
        )
    return (
        "<b>Исполнительное производство</b>\n"
        "Номера ИП, аресты, запреты, travel-ban. Если нет — «нет»."
    )


def _html_additional_notes(route: str) -> str:
    base = (
        "<b>Дополнительно (по желанию)</b>\n"
        "Сроки, суды, угрозы уголовного/налогового характера. Если нечего — «нет»."
    )
    if route == "company":
        return base + "\nЕсли уже звучит тема <b>субсидиарной</b> или оспаривания сделок ТОО — одной фразой."
    return base


def _route_from_data(data: dict) -> str:
    return (data.get("subject_route") or "individual").strip() or "individual"


_MISPLACE_RETURN_STATE = {
    "income": BankruptcyStates.income,
    "family": BankruptcyStates.family,
    "assets": BankruptcyStates.assets,
    "debt_map": BankruptcyStates.debt_map,
    "company_finance": BankruptcyStates.company_finance,
}


def _normalized_intake_value(field: str, text: str) -> str:
    if field in ("assets", "enforcement", "renegotiation", "additional_notes"):
        return _preserved_no(text)
    if field == "risk_disclosures":
        return _risk_value_from_message(text)
    return (text or "").strip()


def _correction_menu_html(route: str) -> str:
    if route == "company":
        inc_line = "<b>3</b> — финансы компании (выручка, поток, задолженность по делу)\n"
    else:
        inc_line = "<b>3</b> — доходы\n"
    return (
        "<b>Что исправить?</b> Ответьте числом <b>1–9</b>.\n"
        "<b>отмена</b> — вернуться к сводке без изменений.\n\n"
        "<b>1</b> — кто вы (ФЛ / ИП / ТОО)\n"
        "<b>2</b> — долги (карта долгов)\n"
        f"{inc_line}"
        "<b>4</b> — семья\n"
        "<b>5</b> — имущество\n"
        "<b>6</b> — взыскание (исполнительное производство)\n"
        "<b>7</b> — переговоры с кредиторами\n"
        "<b>8</b> — риски и сделки\n"
        "<b>9</b> — цель\n"
    )


def _correction_choice_to_field(choice: str, route: str) -> str | None:
    c = (choice or "").strip().lower()
    mapping: dict[str, str]
    if route == "company":
        mapping = {
            "1": "subject",
            "2": "debt_map",
            "3": "company_finance",
            "4": "family",
            "5": "assets",
            "6": "enforcement",
            "7": "renegotiation",
            "8": "risk_disclosures",
            "9": "client_goal",
        }
    else:
        mapping = {
            "1": "subject",
            "2": "debt_map",
            "3": "income",
            "4": "family",
            "5": "assets",
            "6": "enforcement",
            "7": "renegotiation",
            "8": "risk_disclosures",
            "9": "client_goal",
        }
    return mapping.get(c)


def _merge_into_intake_field(data: dict, field: str, text: str) -> str:
    new_val = _normalized_intake_value(field, text)
    if field == "debt_map":
        prev = (data.get(field) or "").strip()
        if prev:
            return (prev + "\n\n" + new_val).strip()
    return new_val


async def _try_misplaced_redirect(
    message: Message,
    state: FSMContext,
    *,
    text: str,
    current_field: str,
) -> bool:
    await sync_bankruptcy_migrations(state)
    data = await state.get_data()
    merged = merge_legacy_bankruptcy_fields(data)
    r = resolved_subject_kind_for_qualification(data, merged)
    sug = suggest_misplaced_intake_block(text, current_field, r)
    if not sug:
        return False
    await state.update_data(
        _misplace_suggest=sug,
        _misplace_pending_text=text,
        _misplace_from_field=current_field,
    )
    await state.set_state(BankruptcyStates.intake_misplaced_confirm)
    label = _misplaced_field_label_ru(sug)
    await message.answer(
        "Похоже, вы описали раздел <b>"
        f"{html.escape(label)}</b>, а сейчас другой шаг опроса.\n\n"
        "Перенести текст туда?\n"
        "<b>да</b> — перенести и снова задать текущий вопрос\n"
        "<b>нет</b> — не сохранять это сообщение, ответьте на вопрос заново",
        parse_mode=ParseMode.HTML,
    )
    return True


_RESUME_STATE_MAP = {
    "debt_map": BankruptcyStates.debt_map,
    "ip_business_status": BankruptcyStates.ip_business_status,
    "company_identification": BankruptcyStates.company_identification,
    "company_finance": BankruptcyStates.company_finance,
    "income": BankruptcyStates.income,
    "family": BankruptcyStates.family,
    "assets": BankruptcyStates.assets,
    "ip_taxes_creditors": BankruptcyStates.ip_taxes_creditors,
    "company_employees_budget": BankruptcyStates.company_employees_budget,
    "company_controllers": BankruptcyStates.company_controllers,
    "risk_disclosures": BankruptcyStates.risk_disclosures,
    "enforcement": BankruptcyStates.enforcement,
    "renegotiation": BankruptcyStates.renegotiation,
    "client_goal": BankruptcyStates.client_goal,
}

_RISK_BLOCK_MIN_LEN = 24


async def sync_bankruptcy_migrations(state: FSMContext) -> None:
    """Подтянуть subject_route и legacy-поля в новый формат без потери ответов пользователя."""
    data = await state.get_data()
    migrated = apply_bankruptcy_session_migrations(data)
    updates: dict = {}
    for k, v in migrated.items():
        if str(k).startswith("_"):
            continue
        if data.get(k) != v:
            updates[k] = v
    if updates:
        await state.update_data(**updates)


def _resume_prompt_for_field(field: str, route: str) -> str:
    if field == "subject":
        return (
            "<b>Кто вы по статусу и регистрации?</b>\n"
            "Физлицо / ИП / ТОО — связным текстом (ИИН/БИН, город — по возможности)."
        )
    if field == "debt_map":
        return _html_debt_map(route)
    if field == "ip_business_status":
        return _html_ip_business_status()
    if field == "company_identification":
        return _html_company_identification()
    if field == "company_finance":
        return _html_company_finance()
    if field == "income":
        return _html_income(route)
    if field == "family":
        return _html_family(route)
    if field == "assets":
        return _html_assets(route)
    if field == "ip_taxes_creditors":
        return _html_ip_taxes_creditors()
    if field == "company_employees_budget":
        return _html_company_employees_budget()
    if field == "company_controllers":
        return _html_company_controllers()
    if field == "risk_disclosures":
        return _html_risk_checklist(route)
    if field == "enforcement":
        return _html_enforcement(route)
    if field == "renegotiation":
        return (
            "<b>Переговоры и реструктуризация</b>\n"
            "Что уже пробовали: банк, МФО, налоговая, мораторий, мировое, отсрочки. "
            "Отказ кредиторов — кратко. Если ничего — «нет»."
        )
    if field == "client_goal":
        return (
            "<b>Цель</b>\n"
            "Что хотите получить: процедура банкротства, реструктуризация, списание по закону, "
            "остановка взыскания, защита имущества, другое — своими словами."
        )
    return ""


async def _resume_intake_from_state(message: Message, state: FSMContext) -> None:
    """После миграции — первый незаполненный шаг или меню следующих действий."""
    await sync_bankruptcy_migrations(state)
    data = await state.get_data()
    merged = merge_legacy_bankruptcy_fields(data)
    miss = first_incomplete_intake_field(merged)
    route = _route_from_data(data)
    resolved = resolved_subject_kind_for_qualification(data, merged)

    if miss is None:
        await state.set_state(BankruptcyStates.next_action)
        await message.answer(
            "<b>Сохранённые ответы достаточны, чтобы перейти к выгрузкам.</b>\n\n"
            + next_step_menu_text_html()
            + _CAUTIONS_FOOTER,
            parse_mode=ParseMode.HTML,
        )
        return
    if miss == "subject_kind_clarify":
        await state.set_state(BankruptcyStates.subject_kind_clarify)
        await message.answer(
            "<b>Нужно уточнить тип субъекта</b> (после обновления опроса).\n"
            "Ответьте: <b>1</b> — физлицо, <b>2</b> — ИП, <b>3</b> — ТОО / юрлицо.",
            parse_mode=ParseMode.HTML,
        )
        return
    if miss == "subject":
        await state.set_state(BankruptcyStates.subject)
        await message.answer(
            "<b>Продолжаем опрос.</b> Сначала коротко: кто вы по статусу и регистрации?\n"
            "Физлицо / ИП / ТОО — связным текстом.",
            parse_mode=ParseMode.HTML,
        )
        return

    if miss == "enforcement" and resolved == "company":
        risk_ok = len((merged.get("risk_disclosures") or "").strip()) >= _RISK_BLOCK_MIN_LEN
        if risk_ok:
            await state.update_data(__post_risk_enforcement=True)

    st_cls = _RESUME_STATE_MAP.get(miss)
    if st_cls is None:
        await state.set_state(BankruptcyStates.next_action)
        await message.answer(
            "Не удалось автоматически выбрать шаг опроса. Используйте /bankruptcy или кнопку сценария.\n\n"
            + next_step_menu_text_html(),
            parse_mode=ParseMode.HTML,
        )
        return

    r_for_prompt = route if route in ("individual", "sole_prop", "company") else "individual"
    await state.set_state(st_cls)
    body = _resume_prompt_for_field(miss, r_for_prompt)
    await message.answer(
        "<b>Мы сохранили ваши ответы.</b> Дальше — шаг, где не хватает данных.\n\n" + body,
        parse_mode=ParseMode.HTML,
    )


def _risk_value_from_message(text: str | None) -> str:
    raw = (text or "").strip()
    low = raw.lower()
    if low in {
        "нет",
        "нету",
        "no",
        "-",
        "не требуется",
        "отсутствует",
        "не знаю",
        "н/д",
        "ничего",
    }:
        return "нет"
    return raw


async def _begin_intake_for_route(message: Message, state: FSMContext, route: str) -> None:
    await state.update_data(
        subject_route=route,
        **{FSM_SCENARIO_ID_KEY: scenario_id_for_bankruptcy_route(route)},
    )
    if route == "individual":
        await state.set_state(BankruptcyStates.debt_map)
        await message.answer(
            _html_debt_map(route) + "\n\n" + UX_AFTER_BRANCH_HTML,
            parse_mode=ParseMode.HTML,
        )
    elif route == "sole_prop":
        await state.set_state(BankruptcyStates.ip_business_status)
        await message.answer(
            _html_ip_business_status() + "\n\n" + UX_AFTER_BRANCH_HTML,
            parse_mode=ParseMode.HTML,
        )
    else:
        await state.set_state(BankruptcyStates.company_identification)
        await message.answer(
            _html_company_identification() + "\n\n" + UX_AFTER_BRANCH_HTML,
            parse_mode=ParseMode.HTML,
        )


async def _send_bankruptcy_response(message: Message, result: dict) -> None:
    """Telegram ~4096 на сообщение: превью + DOCX или нарезка на чанки."""
    text = (result.get("text") or "").strip()
    docx = result.get("docx")

    if not text:
        await message.answer("⚠️ Пустой результат.", parse_mode=ParseMode.HTML)
        return

    if docx and Path(docx).is_file():
        preview = text[:_TELEGRAM_PREVIEW_CHARS].rstrip()
        if len(text) > _TELEGRAM_PREVIEW_CHARS:
            preview += "\n\n… полный текст во вложении (DOCX)."
        body = (
            "<b>Банкротство — материал</b>\n\n"
            f"{html.escape(preview, quote=False)}"
        )
        await message.answer(body, parse_mode=ParseMode.HTML)
        await message.answer_document(
            FSInputFile(docx),
            caption="Полный текст (DOCX)",
        )
        return

    try:
        for chunk in split_text_to_html_chunks_for_telegram(text):
            await message.answer(chunk, parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.answer(
            "❌ <b>Не удалось отправить ответ</b>\n\n"
            f"<code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML,
        )


def _intake_summary_rows(route: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("subject", "Идентификация (вы)"),
        ("subject_route", "Маршрут"),
    ]
    if route == "sole_prop":
        rows.append(("ip_business_status", "Статус ИП / деятельность"))
        rows.append(("debt_map", "Карта долгов (личное / бизнес)"))
        rows.extend(
            [
                ("income", "Доходы"),
                ("family", "Семья / иждивенцы"),
                ("assets", "Имущество (личное и бизнес)"),
                ("ip_taxes_creditors", "Налоги и кредиторы по делу"),
                ("enforcement", "Исполнительное производство"),
                ("renegotiation", "Переговоры / реструктуризация"),
                ("risk_disclosures", "Риски и сделки"),
            ]
        )
    elif route == "company":
        rows.append(("company_identification", "Компания и ваша роль"))
        rows.append(("debt_map", "Структура долгов"))
        rows.extend(
            [
                ("company_finance", "Финансовое состояние"),
                ("assets", "Активы"),
                ("company_employees_budget", "Персонал / бюджет"),
                ("company_controllers", "Контроль / связанные лица"),
                ("risk_disclosures", "Сделки и риски"),
                ("enforcement", "Исполнительное производство / споры"),
            ]
        )
    else:
        rows.append(("debt_map", "Карта долгов"))
        rows.extend(
            [
                ("income", "Доходы"),
                ("family", "Семья / иждивенцы"),
                ("assets", "Имущество"),
                ("enforcement", "Исполнительное производство"),
                ("renegotiation", "Переговоры / реструктуризация"),
                ("risk_disclosures", "Риски и сделки"),
            ]
        )
    rows.extend([("client_goal", "Цель"), ("additional_notes", "Дополнительно")])
    return rows


def _intake_summary_html(data: dict) -> str:
    route = (data.get("subject_route") or "").strip() or "individual"
    lines = ["<b>Сводка ответов</b>", ""]
    for key, title in _intake_summary_rows(route):
        v_raw = (data.get(key) or "").strip() or "—"
        if key == "subject_route":
            v_disp = _ROUTE_SUMMARY_RU.get(v_raw, v_raw)
        else:
            v_disp = v_raw
        lines.append(f"<b>{html.escape(title)}</b>")
        lines.append(html.escape(v_disp))
        lines.append("")
    lines.append("Если всё верно — <b>подтвердить</b>. Если что-то не так — <b>нет</b> (откроется список разделов).")
    return "\n".join(lines)


# =====================================================
# START
# =====================================================


@router.message(Command("bankruptcy"))
@router.message(F.text.func(lambda text: main_menu_button_matches(text, BTN_BANKRUPTCY, "bankruptcy")))
async def start_bankruptcy(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(BankruptcyStates.subject)
    await state.update_data(
        **{
            FSM_ACTIVE_FEATURE: FEATURE_BANKRUPTCY,
            FSM_ACTIVE_SCENARIO: SCENARIO_BANKRUPTCY,
            FSM_SCENARIO_ID_KEY: "",
        }
    )

    uid = _uid(message)
    await message.answer(
        "⚖️ <b>Банкротство / несостоятельность</b>\n\n"
        "Этот сценарий — <b>глубокий опрос</b>: дальнейшие вопросы зависят от типа субъекта (ФЛ / ИП / ТОО).\n\n"
        "<b>Шаг 1.</b> Кто вы по статусу и регистрации?\n"
        "• физическое лицо (ИИН, город)\n"
        "• ИП (ИИН, вид деятельности, есть ли наёмные)\n"
        "• ТОО (БИН, вы — учредитель/директор, доля)\n\n"
        "Можно связным текстом.\n\n"
        + UX_FREE_NARRATIVE_INVITE_HTML
        + "\n\n"
        + UX_RIBBON_HTML
        + free_tier_footer_html(uid),
        parse_mode=ParseMode.HTML,
    )


# =====================================================
# INTAKE CHAIN
# =====================================================


@router.message(BankruptcyStates.subject)
async def intake_subject(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    prev = await state.get_data()
    mid_resume = bool((prev.get("subject_route") or "").strip()) and bool((prev.get("debt_map") or "").strip())
    if mid_resume:
        await state.update_data(subject=text)
        await sync_bankruptcy_migrations(state)
        await _resume_intake_from_state(message, state)
        return

    await state.update_data(
        subject=text,
        subject_route="",
        **{FSM_SCENARIO_ID_KEY: ""},
        ip_context="",
        company_context="",
        ip_business_status="",
        ip_taxes_creditors="",
        company_identification="",
        company_finance="",
        company_employees_budget="",
        company_controllers="",
        risk_disclosures="",
        recent_transactions="",
        __post_risk_enforcement=None,
    )
    sk = infer_subject_kind(text.lower())
    if sk == "unclear":
        await state.set_state(BankruptcyStates.subject_kind_clarify)
        await message.answer(
            "По первому сообщению тип субъекта неоднозначен.\n\n"
            "Уточните (одним числом или словом):\n"
            "<b>1</b> — физическое лицо (не ИП)\n"
            "<b>2</b> — индивидуальный предприниматель (ИП)\n"
            "<b>3</b> — ТОО / иное юрлицо",
            parse_mode=ParseMode.HTML,
        )
        return
    await _begin_intake_for_route(message, state, sk)


@router.message(BankruptcyStates.subject_kind_clarify)
async def intake_subject_kind_clarify(message: Message, state: FSMContext):
    route = _parse_clarify_subject_route(message.text or "")
    if not route:
        await message.answer(
            "Нужно указать <b>1</b>, <b>2</b> или <b>3</b> (или коротко: фл / ип / тоо).",
            parse_mode=ParseMode.HTML,
        )
        return
    await state.update_data(
        subject_route=route,
        **{FSM_SCENARIO_ID_KEY: scenario_id_for_bankruptcy_route(route)},
    )
    await sync_bankruptcy_migrations(state)
    await _resume_intake_from_state(message, state)


@router.message(BankruptcyStates.ip_business_status)
async def intake_ip_business_status(message: Message, state: FSMContext):
    await state.update_data(ip_business_status=(message.text or "").strip())
    await state.set_state(BankruptcyStates.debt_map)
    await message.answer(_html_debt_map("sole_prop"), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.company_identification)
async def intake_company_identification(message: Message, state: FSMContext):
    await state.update_data(company_identification=(message.text or "").strip())
    await state.set_state(BankruptcyStates.debt_map)
    await message.answer(_html_debt_map("company"), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.debt_map)
async def intake_debt_map(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if await _try_misplaced_redirect(message, state, text=text, current_field="debt_map"):
        return
    await state.update_data(debt_map=text)
    data = await state.get_data()
    route = _route_from_data(data)
    if route == "company":
        await state.set_state(BankruptcyStates.company_finance)
        await message.answer(_html_company_finance(), parse_mode=ParseMode.HTML)
        return
    await state.set_state(BankruptcyStates.income)
    await message.answer(_html_income(route), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.company_finance)
async def intake_company_finance(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if await _try_misplaced_redirect(message, state, text=text, current_field="company_finance"):
        return
    await state.update_data(company_finance=text)
    data = await state.get_data()
    route = _route_from_data(data)
    await state.set_state(BankruptcyStates.assets)
    await message.answer(_html_assets(route), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.income)
async def intake_income(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if await _try_misplaced_redirect(message, state, text=text, current_field="income"):
        return
    await state.update_data(income=text)
    data = await state.get_data()
    route = _route_from_data(data)
    await state.set_state(BankruptcyStates.family)
    await message.answer(_html_family(route), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.family)
async def intake_family(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if await _try_misplaced_redirect(message, state, text=text, current_field="family"):
        return
    await state.update_data(family=text)
    data = await state.get_data()
    route = _route_from_data(data)
    await state.set_state(BankruptcyStates.assets)
    await message.answer(_html_assets(route), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.assets)
async def intake_assets(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if await _try_misplaced_redirect(message, state, text=text, current_field="assets"):
        return
    await state.update_data(assets=_preserved_no(message.text))
    data = await state.get_data()
    route = _route_from_data(data)
    if route == "company":
        await state.set_state(BankruptcyStates.company_employees_budget)
        await message.answer(_html_company_employees_budget(), parse_mode=ParseMode.HTML)
        return
    if route == "sole_prop":
        await state.set_state(BankruptcyStates.ip_taxes_creditors)
        await message.answer(_html_ip_taxes_creditors(), parse_mode=ParseMode.HTML)
        return
    await state.set_state(BankruptcyStates.enforcement)
    await message.answer(_html_enforcement(route), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.ip_taxes_creditors)
async def intake_ip_taxes_creditors(message: Message, state: FSMContext):
    await state.update_data(ip_taxes_creditors=(message.text or "").strip())
    data = await state.get_data()
    route = _route_from_data(data)
    await state.set_state(BankruptcyStates.enforcement)
    await message.answer(_html_enforcement(route), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.company_employees_budget)
async def intake_company_employees_budget(message: Message, state: FSMContext):
    await state.update_data(company_employees_budget=_preserved_no(message.text))
    await state.set_state(BankruptcyStates.company_controllers)
    await message.answer(_html_company_controllers(), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.company_controllers)
async def intake_company_controllers(message: Message, state: FSMContext):
    await state.update_data(company_controllers=(message.text or "").strip())
    data = await state.get_data()
    route = _route_from_data(data)
    await state.set_state(BankruptcyStates.risk_disclosures)
    await message.answer(_html_risk_checklist(route), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.risk_disclosures)
async def intake_risk_disclosures(message: Message, state: FSMContext):
    rv = _risk_value_from_message(message.text)
    await state.update_data(risk_disclosures=rv, recent_transactions=rv)
    data = await state.get_data()
    route = _route_from_data(data)
    if route == "company":
        await state.update_data(__post_risk_enforcement=True)
        await state.set_state(BankruptcyStates.enforcement)
        await message.answer(_html_enforcement(route), parse_mode=ParseMode.HTML)
        return
    await state.set_state(BankruptcyStates.client_goal)
    await message.answer(
        "<b>Цель</b>\n"
        "Что хотите получить: процедура банкротства, реструктуризация, списание по закону, "
        "остановка взыскания, защита имущества, другое — своими словами.",
        parse_mode=ParseMode.HTML,
    )


@router.message(BankruptcyStates.enforcement)
async def intake_enforcement(message: Message, state: FSMContext):
    await state.update_data(enforcement=_preserved_no(message.text))
    data = await state.get_data()
    route = _route_from_data(data)
    post_risk = data.get("__post_risk_enforcement")
    await state.update_data(__post_risk_enforcement=None)
    if post_risk:
        await state.set_state(BankruptcyStates.client_goal)
        await message.answer(
            "<b>Цель</b>\n"
            "Что хотите получить по организации и лично: реструктуризация, банкротство ЮЛ, защита активов, иное — своими словами.",
            parse_mode=ParseMode.HTML,
        )
        return
    await state.set_state(BankruptcyStates.renegotiation)
    await message.answer(
        "<b>Переговоры и реструктуризация</b>\n"
        "Что уже пробовали: банк, МФО, налоговая, мораторий, мировое, отсрочки. "
        "Отказ кредиторов — кратко. Если ничего — «нет».",
        parse_mode=ParseMode.HTML,
    )


@router.message(BankruptcyStates.renegotiation)
async def intake_renegotiation(message: Message, state: FSMContext):
    await state.update_data(renegotiation=_preserved_no(message.text))
    data = await state.get_data()
    route = _route_from_data(data)
    await state.set_state(BankruptcyStates.risk_disclosures)
    await message.answer(_html_risk_checklist(route), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.client_goal)
async def intake_client_goal(message: Message, state: FSMContext):
    await state.update_data(client_goal=message.text.strip())
    data = await state.get_data()
    route = _route_from_data(data)
    await state.set_state(BankruptcyStates.additional_notes)
    await message.answer(_html_additional_notes(route), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.additional_notes)
async def intake_additional(message: Message, state: FSMContext):
    await state.update_data(additional_notes=_preserved_no(message.text))
    data = await state.get_data()
    await state.set_state(BankruptcyStates.confirm_intake)
    await message.answer(_intake_summary_html(data), parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.intake_misplaced_confirm)
async def intake_misplaced_confirm(message: Message, state: FSMContext):
    await sync_bankruptcy_migrations(state)
    data = await state.get_data()
    sug = data.get("_misplace_suggest")
    pending = data.get("_misplace_pending_text")
    from_f = data.get("_misplace_from_field")
    if not sug or not isinstance(pending, str) or not from_f:
        await state.update_data(
            _misplace_suggest=None,
            _misplace_pending_text=None,
            _misplace_from_field=None,
        )
        await _resume_intake_from_state(message, state)
        return

    t = (message.text or "").strip().lower()
    if t in MISPLACED_YES:
        merged_prev = dict(data)
        val = _merge_into_intake_field(merged_prev, str(sug), pending)
        await state.update_data(
            **{str(sug): val},
            _misplace_suggest=None,
            _misplace_pending_text=None,
            _misplace_from_field=None,
        )
        ret_st = _MISPLACE_RETURN_STATE.get(str(from_f))
        if not ret_st:
            await _resume_intake_from_state(message, state)
            return
        await state.set_state(ret_st)
        route = _route_from_data(await state.get_data())
        rfp = route if route in ("individual", "sole_prop", "company") else "individual"
        body = _resume_prompt_for_field(str(from_f), rfp)
        nice = _misplaced_field_label_ru(str(sug))
        await message.answer(
            f"Сохранено в раздел «{html.escape(nice)}». Текущий вопрос:\n\n" + body,
            parse_mode=ParseMode.HTML,
        )
        return
    if t in MISPLACED_NO:
        await state.update_data(
            _misplace_suggest=None,
            _misplace_pending_text=None,
            _misplace_from_field=None,
        )
        ret_st = _MISPLACE_RETURN_STATE.get(str(from_f))
        if not ret_st:
            await _resume_intake_from_state(message, state)
            return
        await state.set_state(ret_st)
        route = _route_from_data(await state.get_data())
        rfp = route if route in ("individual", "sole_prop", "company") else "individual"
        body = _resume_prompt_for_field(str(from_f), rfp)
        await message.answer(
            "Хорошо, прошлый ответ не сохранялся. Ответьте на вопрос ещё раз:\n\n" + body,
            parse_mode=ParseMode.HTML,
        )
        return

    await message.answer("Ответьте <b>да</b> или <b>нет</b>.", parse_mode=ParseMode.HTML)


@router.message(BankruptcyStates.intake_correction_menu)
async def intake_correction_menu(message: Message, state: FSMContext):
    await sync_bankruptcy_migrations(state)
    t = (message.text or "").strip().lower()
    if t in {"отмена", "назад", "cancel"}:
        data = await state.get_data()
        await state.set_state(BankruptcyStates.confirm_intake)
        await message.answer(_intake_summary_html(data), parse_mode=ParseMode.HTML)
        return

    route = _route_from_data(await state.get_data())
    field = _correction_choice_to_field(t, route)
    if not field:
        await message.answer(
            "Выберите число <b>1–9</b> или напишите <b>отмена</b> (вернуться к сводке).",
            parse_mode=ParseMode.HTML,
        )
        return

    await state.update_data(_correction_target_field=field)
    await state.set_state(BankruptcyStates.intake_correction_capture)
    rfp = route if route in ("individual", "sole_prop", "company") else "individual"
    body = _resume_prompt_for_field(field, rfp)
    await message.answer(
        "<b>Исправляем выбранный раздел.</b> Пришлите новый ответ одним сообщением.\n\n" + body,
        parse_mode=ParseMode.HTML,
    )


@router.message(BankruptcyStates.intake_correction_capture)
async def intake_correction_capture(message: Message, state: FSMContext):
    await sync_bankruptcy_migrations(state)
    data = await state.get_data()
    field = data.get("_correction_target_field")
    if not field:
        await state.set_state(BankruptcyStates.confirm_intake)
        await message.answer(_intake_summary_html(data), parse_mode=ParseMode.HTML)
        return

    t = (message.text or "").strip().lower()
    if t in {"отмена", "назад", "cancel"}:
        await state.update_data(_correction_target_field=None)
        await state.set_state(BankruptcyStates.intake_correction_menu)
        route = _route_from_data(data)
        await message.answer(_correction_menu_html(route), parse_mode=ParseMode.HTML)
        return

    text = (message.text or "").strip()
    await state.update_data(**{str(field): _normalized_intake_value(str(field), text)}, _correction_target_field=None)
    await state.set_state(BankruptcyStates.confirm_intake)
    fresh = await state.get_data()
    await message.answer(
        "Раздел обновлён. Проверьте сводку:\n\n" + _intake_summary_html(fresh),
        parse_mode=ParseMode.HTML,
    )


# =====================================================
# CONFIRM → КВАЛИФИКАЦИЯ → ВЫБОР ШАГА
# =====================================================


@router.message(BankruptcyStates.confirm_intake)
async def confirm_intake(message: Message, state: FSMContext):
    await sync_bankruptcy_migrations(state)
    t = (message.text or "").strip().lower()
    if t in SUMMARY_REJECT_WORDS:
        route = _route_from_data(await state.get_data())
        await state.set_state(BankruptcyStates.intake_correction_menu)
        await message.answer(_correction_menu_html(route), parse_mode=ParseMode.HTML)
        return
    if t not in CONFIRM_WORDS:
        await message.answer(
            "Если сводка верна — напишите <b>подтвердить</b>.\n"
            "Если нужно поправить данные — напишите <b>нет</b>: откроется меню разделов.\n"
            "Новый опрос: /bankruptcy",
            parse_mode=ParseMode.HTML,
        )
        return

    raw = await state.get_data()
    assessment = assess_bankruptcy_case(raw)

    if assessment.decision != "bankruptcy_allowed":
        await state.clear()
        await message.answer(
            "⚠️ <b>Автоматическая генерация недоступна</b>\n\n"
            f"Уровень риска: {html.escape(assessment.risk_level)}\n"
            "Причины:\n"
            + "\n".join(f"• {html.escape(r)}" for r in assessment.reasons),
            parse_mode=ParseMode.HTML,
        )
        return

    prelim = build_preliminary_qualification(raw)
    qual = format_qualification_telegram_html(prelim)
    menu = next_step_menu_text_html()
    await message.answer(
        qual + "\n\n" + menu + _CAUTIONS_FOOTER,
        parse_mode=ParseMode.HTML,
    )
    await state.set_state(BankruptcyStates.next_action)


# =====================================================
# NEXT ACTION → PIPELINE
# =====================================================


def _facts_for_pipeline(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


async def _execute_bankruptcy_output(
    message: Message,
    state: FSMContext,
    raw: dict,
    focus: str,
) -> None:
    await sync_bankruptcy_migrations(state)
    snap = await state.get_data()
    if snap.get("_generation_in_progress"):
        await message.answer(_GENERATION_BUSY_HTML, parse_mode=ParseMode.HTML)
        return

    raw = dict(snap)
    if scenario_mismatch_for_bankruptcy(snap):
        await message.answer(
            "⚠️ Активен другой сценарий. Банкротство — через меню или /bankruptcy.",
            parse_mode=ParseMode.HTML,
        )
        return
    facts = _facts_for_pipeline(dict(raw))

    merged = merge_legacy_bankruptcy_fields(facts)
    prelim = build_preliminary_qualification(facts)

    if focus == "application_draft":
        gate, msg = evaluate_application_draft_gate(prelim, merged)
        if gate == "blocked":
            await message.answer(msg, parse_mode=ParseMode.HTML)
            await state.update_data(_pending_output_focus=None)
            await state.set_state(BankruptcyStates.next_action)
            await message.answer(
                next_step_menu_text_html() + _CAUTIONS_FOOTER,
                parse_mode=ParseMode.HTML,
            )
            return
        if gate == "need_data":
            await state.update_data(
                **{k: v for k, v in facts.items()},
                _pending_output_focus="application_draft",
            )
            await state.set_state(BankruptcyStates.supplement_application)
            await message.answer(
                "<b>Нужно чуть больше фактов для проекта заявления.</b>\n"
                "Допишите по пунктам ниже одним или несколькими сообщениями, затем — <b>готово</b>.\n\n"
                f"<pre>{html.escape(msg)}</pre>",
                parse_mode=ParseMode.HTML,
            )
            return

    uid = _uid(message)
    ok, wall = assert_can_deliver_result(uid)
    if not ok:
        await message.answer(wall, parse_mode=ParseMode.HTML)
        return

    await state.update_data(_generation_in_progress=True)
    try:
        await message.answer(
            f"{UX_BEFORE_GENERATION_HTML}\n\n⚖️ Готовлю материал…" + free_tier_footer_html(uid),
            parse_mode=ParseMode.HTML,
        )
        try:
            if focus == "application_draft":
                result = await generate_bankruptcy_result(
                    facts, generation_mode="statement", analysis_focus="full"
                )
            else:
                result = await generate_bankruptcy_result(
                    facts, generation_mode="analysis", analysis_focus=focus
                )
        except Exception as e:
            await message.answer(
                "❌ <b>Ошибка</b>\n\n"
                f"<code>{html.escape(str(e))}</code>",
                parse_mode=ParseMode.HTML,
            )
            await state.set_state(BankruptcyStates.next_action)
            return

        if not result.get("ok", True):
            await message.answer(
                html.escape(result.get("text") or "Ошибка", quote=False),
                parse_mode=ParseMode.HTML,
            )
            await state.set_state(BankruptcyStates.next_action)
            return

        await _send_bankruptcy_response(message, result)
        if (result.get("text") or "").strip():
            record_completed_result(uid)

        await state.update_data(
            **_session_payload_from_raw(facts),
            application_supplement="",
            _pending_output_focus=None,
            session_clarifications=facts.get("session_clarifications") or "",
        )
        await state.set_state(BankruptcyStates.followup)
        await message.answer(
            followup_menu_text_html(),
            parse_mode=ParseMode.HTML,
        )
    finally:
        await state.update_data(_generation_in_progress=False)


@router.message(BankruptcyStates.next_action)
async def run_bankruptcy_pipeline(message: Message, state: FSMContext):
    raw = await state.get_data()
    focus = parse_output_focus(message.text or "")
    await _execute_bankruptcy_output(message, state, dict(raw), focus)


@router.message(BankruptcyStates.supplement_application)
async def bankruptcy_supplement_application(message: Message, state: FSMContext):
    await sync_bankruptcy_migrations(state)
    data = await state.get_data()
    if data.get("_generation_in_progress"):
        await message.answer(_GENERATION_BUSY_HTML, parse_mode=ParseMode.HTML)
        return
    if not data.get("_pending_output_focus"):
        await state.set_state(BankruptcyStates.next_action)
        await message.answer(
            "<b>Режим дополнения к заявлению не активен.</b> Это бывает после перезапуска бота или если сессия устарела.\n"
            "Выберите снова пункт меню — например, <b>3</b> (проект заявления), если квалификация позволяет.\n"
            "Или начните новый опрос: /bankruptcy.",
            parse_mode=ParseMode.HTML,
        )
        await message.answer(next_step_menu_text_html() + _CAUTIONS_FOOTER, parse_mode=ParseMode.HTML)
        return

    t = (message.text or "").strip()
    low = t.lower()
    if low in {"готово", "done", "ок", "ok"}:
        data = await state.get_data()
        facts = {k: v for k, v in data.items() if k != "_pending_output_focus"}
        focus = str(data.get("_pending_output_focus") or "application_draft")
        await _execute_bankruptcy_output(message, state, facts, focus)
        return

    data = await state.get_data()
    prev = (data.get("application_supplement") or "").strip()
    new_block = (prev + "\n\n" + t).strip() if prev else t
    await state.update_data(application_supplement=new_block)
    await message.answer(
        "Дополнение сохранено. Можно ещё сообщение или <b>готово</b>.",
        parse_mode=ParseMode.HTML,
    )


@router.message(BankruptcyStates.followup, F.text)
async def bankruptcy_followup(message: Message, state: FSMContext):
    await sync_bankruptcy_migrations(state)
    t = (message.text or "").strip().lower()

    if t in ("ещё", "еще", "меню", "menu"):
        await state.set_state(BankruptcyStates.next_action)
        await message.answer(
            next_step_menu_text_html() + _CAUTIONS_FOOTER,
            parse_mode=ParseMode.HTML,
        )
        return
    if t in ("уточнить", "уточнение", "дополнить"):
        await state.set_state(BankruptcyStates.refine_session)
        await message.answer(
            "Одним сообщением напишите уточнения к фактам. Они будут учтены при следующей выгрузке.",
            parse_mode=ParseMode.HTML,
        )
        return
    if t in ("заново", "сначала"):
        await state.clear()
        await state.set_state(BankruptcyStates.subject)
        await message.answer(
            "⚖️ <b>Банкротство / несостоятельность</b> — новый опрос с нуля.\n\n"
            "<b>Шаг 1.</b> Кто вы по статусу и регистрации?\n"
            "• физическое лицо (ИИН, город)\n"
            "• ИП (ИИН, вид деятельности, есть ли наёмные)\n"
            "• ТОО (БИН, вы — учредитель/директор, доля)\n\n"
            "Можно связным текстом.",
            parse_mode=ParseMode.HTML,
        )
        return

    tx = (message.text or "").strip()
    if tx in ("1", "2", "3", "4", "5", "6"):
        data = await state.get_data()
        focus = parse_output_focus(tx)
        await _execute_bankruptcy_output(message, state, dict(data), focus)
        return

    await message.answer(
        followup_menu_text_html()
        + "\n\nМожно сразу прислать цифру <b>1–6</b> как в меню.",
        parse_mode=ParseMode.HTML,
    )


@router.message(BankruptcyStates.refine_session)
async def bankruptcy_refine_session(message: Message, state: FSMContext):
    await sync_bankruptcy_migrations(state)
    clar = (message.text or "").strip()
    if not clar:
        await message.answer("Напишите текст уточнения.")
        return
    data = await state.get_data()
    prev = (data.get("session_clarifications") or "").strip()
    new = (prev + "\n\n" + clar).strip() if prev else clar
    await state.update_data(session_clarifications=new)
    await state.set_state(BankruptcyStates.followup)
    await message.answer(
        "Сохранено.\n\n" + followup_menu_text_html(),
        parse_mode=ParseMode.HTML,
    )


# =====================================================
# LEGACY FSM (до branching v2) — мягкая миграция без «молчания» бота
# =====================================================


@router.message(BankruptcyStates.ip_context)
async def legacy_intake_ip_context(message: Message, state: FSMContext):
    await state.update_data(ip_context=(message.text or "").strip())
    await message.answer(
        "<b>Обновление сценария.</b> Этот вопрос относился к старой версии бота; ответ сохранён.",
        parse_mode=ParseMode.HTML,
    )
    await _resume_intake_from_state(message, state)


@router.message(BankruptcyStates.company_context)
async def legacy_intake_company_context(message: Message, state: FSMContext):
    await state.update_data(company_context=(message.text or "").strip())
    await message.answer(
        "<b>Обновление сценария.</b> Этот вопрос относился к старой версии бота; ответ сохранён.",
        parse_mode=ParseMode.HTML,
    )
    await _resume_intake_from_state(message, state)


@router.message(BankruptcyStates.recent_transactions)
async def legacy_intake_recent_transactions(message: Message, state: FSMContext):
    rv = _risk_value_from_message(message.text)
    await state.update_data(recent_transactions=rv, risk_disclosures=rv)
    await message.answer(
        "<b>Обновление сценария.</b> Блок «сделки» перенесён в единый чек-лист рисков.",
        parse_mode=ParseMode.HTML,
    )
    await _resume_intake_from_state(message, state)
