# app/features/contracts/questions.py

from __future__ import annotations

from .states import _q, parse_multiline_required, parse_yes_no, parse_optional


Q_CONTRACT_TITLE = _q(
    key="contract_title",
    title="Название договора",
    prompt="Введите название договора (как в шапке документа).",
    parser=parse_multiline_required,
)

Q_PARTIES = _q(
    key="parties",
    title="Стороны договора",
    prompt=(
        "Укажите стороны:\n"
        "— Полное наименование / ФИО\n"
        "— БИН/ИИН (если есть)\n"
        "— Адрес\n"
        "— Представитель и основание полномочий\n"
        "Можно списком."
    ),
    parser=parse_multiline_required,
)

Q_CONFIDENTIAL = _q(
    key="confidential",
    title="Конфиденциальность",
    prompt="Нужна конфиденциальность? (да/нет)",
    parser=parse_yes_no,
)

Q_PD = _q(
    key="personal_data",
    title="Персональные данные",
    prompt="Есть ли обработка персональных данных? (да/нет)",
    parser=parse_yes_no,
)

Q_DISPUTE = _q(
    key="dispute",
    title="Разрешение споров",
    prompt=(
        "Как решаются споры?\n"
        "Примеры: «суд РК по месту ответчика», «МФЦА», «арбитраж (указать регламент)»."
    ),
    parser=parse_multiline_required,  # ✅ фикс: parse_dispute не существует
)

Q_NOTICE = _q(
    key="notice",
    title="Порядок уведомлений",
    prompt=(
        "Как стороны направляют уведомления?\n"
        "Примеры: e-mail, курьер, почта; сроки получения."
    ),
    parser=parse_multiline_required,
)

Q_FORCE_MAJEURE = _q(
    key="force_majeure",
    title="Форс-мажор",
    prompt=(
        "Нужны ли особые условия форс-мажора?\n"
        "Если стандартно — напишите «стандартно»."
    ),
    required=False,
    parser=parse_optional,
)

Q_CONFIRM = _q(
    key="confirm",
    title="Подтверждение",
    prompt="Напишите «подтвердить», чтобы перейти к генерации договора.",
    parser=parse_multiline_required,
)