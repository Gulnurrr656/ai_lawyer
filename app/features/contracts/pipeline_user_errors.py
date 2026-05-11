"""
Коды исходов и тексты для пользователя при остановке generate_contract (H1 hardening).

Номера/коды — только для telemetry outcome_code и support; без PII.
"""

from __future__ import annotations

# outcome_code (санитизируется run_record до lowercase alnum_)
CONTRACT_OC_MISSING_SUBJECT = "contract_missing_subject"
CONTRACT_OC_MISSING_PROFILE = "contract_missing_profile"
CONTRACT_OC_SCENARIO_LOCK = "contract_scenario_lock"
CONTRACT_OC_NO_RETRIEVAL_SPEC = "contract_no_retrieval_spec"
CONTRACT_OC_RAG_EMPTY = "contract_rag_empty"
CONTRACT_OC_EVIDENCE_PACK = "contract_evidence_pack_insufficient"
CONTRACT_OC_LENGTH_GATE = "contract_length_gate"
CONTRACT_OC_VERIFIER_HARD = "contract_verifier_hard"


def user_contract_missing_subject() -> str:
    return (
        "[contract:ввод] Не указан предмет договора. "
        "Добавьте, что именно вы заказываете: услуги, работы, поставку, аренду или другой предмет — и повторите генерацию."
    )


def user_contract_missing_profile() -> str:
    return (
        "[contract:профиль] Не удалось определить тип договора (профиль). "
        "Выберите тип договора в боте ещё раз или укажите профиль/вид договора в данных сессии и повторите попытку."
    )


def user_contract_scenario_lock() -> str:
    return (
        "[contract:сценарий] Данные сессии не совпадают с выбранным типом договора (scenario lock). "
        "Начните сценарий договора заново из меню бота."
    )


def user_contract_no_retrieval_spec() -> str:
    return (
        "[contract:конфигурация] Для этого типа договора не настроена подборка норм (retrieval). "
        "Сообщите поддержке код профиля договора из бота."
    )


def user_contract_rag_empty() -> str:
    return (
        "[contract:RAG] Не удалось подобрать нормы права для договора (пустой ответ поиска). "
        "Проверьте, что база RAG доступна; при повторении обратитесь в поддержку с trace_id прогона."
    )


def user_contract_evidence_pack_insufficient() -> str:
    return (
        "[contract:RAG] Недостаточно нормализованных фрагментов закона для безопасной генерации договора. "
        "Попробуйте позже или обратитесь в поддержку — без полноценной правовой опоры договор не выдаётся."
    )


def user_contract_length_gate() -> str:
    return (
        "[contract:объём] Сгенерированный текст короче требуемого минимума для этого типа договора. "
        "Дополните поля карточки (стороны, предмет, сроки, цена), увеличьте лимиты вывода модели в настройках "
        "или повторите генерацию. Подробности в логах оператора: contract_length_gate."
    )


def user_contract_verifier_hard() -> str:
    return (
        "[contract:проверка] Текст договора не прошёл внутреннюю проверку качества (разделы, обязательные элементы, "
        "согласованность с данными). Дополните или уточните карточку договора и сгенерируйте снова. "
        "Детали для поддержки: contract_verifier_hard."
    )


__all__ = [
    "CONTRACT_OC_EVIDENCE_PACK",
    "CONTRACT_OC_LENGTH_GATE",
    "CONTRACT_OC_MISSING_PROFILE",
    "CONTRACT_OC_MISSING_SUBJECT",
    "CONTRACT_OC_NO_RETRIEVAL_SPEC",
    "CONTRACT_OC_RAG_EMPTY",
    "CONTRACT_OC_SCENARIO_LOCK",
    "CONTRACT_OC_VERIFIER_HARD",
    "user_contract_evidence_pack_insufficient",
    "user_contract_length_gate",
    "user_contract_missing_profile",
    "user_contract_missing_subject",
    "user_contract_no_retrieval_spec",
    "user_contract_rag_empty",
    "user_contract_scenario_lock",
    "user_contract_verifier_hard",
]
