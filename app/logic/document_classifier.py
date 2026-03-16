from typing import Literal

DocumentKind = Literal[
    "contract",
    "claim",
    "complaint",
    "lawsuit",
    "statement",
    "consult",
]

# =========================
# KEYWORD MAP
# =========================

KEYWORDS = {
    "lawsuit": [
        "иск",
        "исковое заявление",
        "в суд",
        "подать в суд",
        "судебный",
        "взыскать через суд",
        "прошу суд",
        "подсудность",
        "госпошлина",
    ],
    "complaint": [
        "жалоба",
        "пожаловаться",
        "прокуратура",
        "акимат",
        "госорган",
        "надзор",
        "нарушение закона",
        "проверку",
        "привлечь к ответственности",
    ],
    "claim": [
        "претензия",
        "досудебная",
        "требую",
        "прошу устранить",
        "возместить",
        "компенсировать",
        "добровольно",
        "в срок",
    ],
    "contract": [
        "договор",
        "оказания услуг",
        "поставки",
        "подряда",
        "аренды",
        "обязуется",
        "стороны договорились",
        "цена договора",
        "ндс",
    ],
    "statement": [
        "заявление",
        "прошу рассмотреть",
        "прошу выдать",
        "прошу предоставить",
        "прошу принять",
    ],
}

# =========================
# CLASSIFIER
# =========================

def classify_document(text: str) -> DocumentKind:
    """
    Определяет тип юридического документа по смыслу текста.
    Работает для текста и STT.
    """

    if not text:
        return "consult"

    t = text.lower()

    # 1️⃣ СУД — САМЫЙ ПРИОРИТЕТНЫЙ
    for kw in KEYWORDS["lawsuit"]:
        if kw in t:
            return "lawsuit"

    # 2️⃣ ЖАЛОБА (ГОСОРГАНЫ)
    for kw in KEYWORDS["complaint"]:
        if kw in t:
            return "complaint"

    # 3️⃣ ПРЕТЕНЗИЯ (ДОСУДЕБНАЯ)
    for kw in KEYWORDS["claim"]:
        if kw in t:
            return "claim"

    # 4️⃣ ДОГОВОР
    for kw in KEYWORDS["contract"]:
        if kw in t:
            return "contract"

    # 5️⃣ ЗАЯВЛЕНИЕ
    for kw in KEYWORDS["statement"]:
        if kw in t:
            return "statement"

    # 6️⃣ ПО УМОЛЧАНИЮ — КОНСУЛЬТАЦИЯ
    return "consult"
