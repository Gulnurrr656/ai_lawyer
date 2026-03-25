# app/shared/safety.py
from typing import Dict, List

from app.shared.legal_reality_system import LEGAL_REALITY_SYSTEM


def check_legal_boundary(*, facts: Dict) -> Dict:
    """
    ЕДИНЫЙ SAFETY-GATE СИСТЕМЫ.

    ❌ НЕ генерирует текст
    ❌ НЕ работает с RAG
    ❌ НЕ знает про кнопки / сценарии

    ✅ Анализирует факты
    ✅ Определяет юридическую конфигурацию
    ✅ Возвращает рекомендации для pipeline
    """

    warnings: List[str] = []
    forbidden: List[str] = []
    notes: List[str] = []

    text_blob = " ".join(
        str(v).lower()
        for v in facts.values()
        if isinstance(v, str)
    )

    # ==================================================
    # 1. УГОЛОВНЫЕ МАРКЕРЫ (граница УК)
    # ==================================================
    criminal_markers = [
        "мошен",
        "хищ",
        "поддел",
        "присво",
        "вымог",
        "угроза",
        "обман",
    ]

    criminal_risk = any(m in text_blob for m in criminal_markers)

    if criminal_risk:
        warnings.append(
            "Обнаружены формулировки, которые могут быть истолкованы "
            "как признаки уголовно-правовой оценки. "
            "Рекомендуется избегать квалифицирующей лексики."
        )
        forbidden.extend(
            [
                "мошенничество",
                "хищение",
                "уголовная ответственность",
                "преступление",
            ]
        )

    # ==================================================
    # 2. КЛАССИФИКАЦИЯ ОБЪЕКТА (двойственность)
    # ==================================================
    object_type = "civil"

    admin_markers = [
        "предписание",
        "уведомление",
        "постановление",
        "штраф",
        "доначис",
        "камераль",
        "проверка",
    ]

    procedural_markers = [
        "рассмотрение",
        "проверка",
        "стадия",
        "запрос",
    ]

    state_function_markers = [
        "контроль",
        "надзор",
        "мониторинг",
        "госфункц",
    ]

    if any(m in text_blob for m in state_function_markers):
        object_type = "state_function"
    elif any(m in text_blob for m in procedural_markers):
        object_type = "procedural"
    elif any(m in text_blob for m in admin_markers):
        object_type = "admin"

    # ==================================================
    # 3. ФИЛЬТР СУДЕБНОГО РЕЗУЛЬТАТА
    # ==================================================
    can_have_judicial_result = object_type in ("civil", "admin")

    if not can_have_judicial_result:
        notes.append(
            "В данной конфигурации право на обращение "
            "не образует судебной защиты, "
            "поскольку отсутствует объект судебного контроля, "
            "который может быть изменён или установлен решением суда."
        )

    # ==================================================
    # 4. РЕЖИМ ГЕНЕРАЦИИ
    # ==================================================
    if criminal_risk:
        mode = "civil_safe"
    elif object_type == "admin":
        mode = "admin"
    elif not can_have_judicial_result:
        mode = "consult_only"
    else:
        mode = "civil"

    # ==================================================
    # 5. РЕЗУЛЬТАТ
    # ==================================================
    return {
        "ok": True,  # мы не блочим, решение за pipeline
        "mode": mode,  # civil | civil_safe | admin | consult_only
        "object_type": object_type,
        "warnings": warnings,
        "forbidden_terms": forbidden,
        "notes_for_prompt": "\n".join(notes) if notes else "",
        "system_principle": LEGAL_REALITY_SYSTEM.strip(),
    }