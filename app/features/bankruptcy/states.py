from aiogram.fsm.state import StatesGroup, State


# =========================
# BANKRUPTCY FSM — маршрутный intake (ФЛ / ИП / ТОО)
# =========================


class BankruptcyStates(StatesGroup):
    """Сбор фактов → сводка → квалификация → выбор следующего шага."""

    subject = State()
    subject_kind_clarify = State()
    # Ветки после выбора маршрута
    ip_business_status = State()
    company_identification = State()
    debt_map = State()
    company_finance = State()
    income = State()
    family = State()
    assets = State()
    ip_taxes_creditors = State()
    company_employees_budget = State()
    company_controllers = State()
    risk_disclosures = State()
    enforcement = State()
    renegotiation = State()
    client_goal = State()
    additional_notes = State()
    confirm_intake = State()
    intake_correction_menu = State()
    intake_correction_capture = State()
    intake_misplaced_confirm = State()
    next_action = State()
    supplement_application = State()
    followup = State()
    refine_session = State()
    # Устаревшие имена состояний (до branching v2): мягкая миграция в handlers
    ip_context = State()
    company_context = State()
    recent_transactions = State()
