import re
from typing import Dict


def extract_facts_from_text(text: str) -> Dict[str, str]:
    """
    Простейший извлекатель юридических фактов из речи.
    Потом можно усложнять (NER, LLM, rules).
    """

    facts = {}

    # Тип договора
    if "возмезд" in text.lower():
        facts["Тип договора"] = "Договор возмездного оказания услуг"

    # Цена
    price_match = re.search(r"(\d+)\s*тысяч", text.lower())
    if price_match:
        facts["Цена"] = f"{price_match.group(1)} 000 тенге"

    if "ндс" in text.lower():
        facts["НДС"] = "включая НДС"

    # Срок
    if "две недели" in text.lower():
        facts["Срок"] = "2 недели"

    # Аванс
    if "аванс" in text.lower() or "50%" in text:
        facts["Аванс"] = "50% предоплата"

    # Предмет
    if "сайт" in text.lower():
        facts["Предмет"] = "Разработка и доработка сайта"

    if "презентац" in text.lower():
        facts["Предмет"] = facts.get("Предмет", "") + ", разработка презентации"

    return facts
