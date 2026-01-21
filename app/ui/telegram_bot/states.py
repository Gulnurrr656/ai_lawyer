from aiogram.fsm.state import StatesGroup, State


# =========================
# CONTRACT FSM
# =========================

class ContractStates(StatesGroup):
    # Тип договора
    contract_type = State()

    # Стороны
    customer = State()     # Заказчик
    executor = State()     # Исполнитель

    # Налоги
    tax_mode = State()     # НДС / упрощёнка / без НДС

    # Условия
    price = State()        # Итоговая цена
    subject = State()      # Предмет договора
    term = State()         # Срок
    jurisdiction = State() # Подсудность / применимое право
    attachments = State()  # Приложения

    # Подтверждение
    confirm = State()


# =========================
# CLAIMS FSM
# (на будущее, чтобы не ломать импорты)
# =========================

class ClaimsStates(StatesGroup):
    claim_type = State()
    parties = State()
    facts = State()
    demands = State()
    attachments = State()
    confirm = State()


# =========================
# CONSULT FSM
# =========================

class ConsultStates(StatesGroup):
    question = State()


# =========================
# ANALYZE FSM
# =========================

class AnalyzeStates(StatesGroup):
    upload = State()
    confirm = State()
