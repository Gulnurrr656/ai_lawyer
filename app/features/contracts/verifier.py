# app/features/contracts/verifier.py

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .contract_fact_model import CONTRACT_FACT_ENTITY_KEYS, build_contract_fact_snapshot

"""
DETERMINISTIC CONTRACT VERIFIER (KZ)

Hard — блокируют выдачу (пусто, нет профиля, forbidden_mix, нет реквизитов).
Soft — предупреждения в лог; не ломают UX (порядок outline, заголовки, приложения, дубли).
"""

_REQUISITES_PHRASE = "реквизиты и подписи сторон"

_PRICE_FACT_KEYS = (
    "supply_price",
    "supply_price_unit",
    "service_price",
    "service_price_unit",
    "work_price",
    "work_price_unit",
    "manufacture_price",
    "manufacture_price_unit",
    "rent_price",
    "price_and_payment",
)


def _joined_price_blob_lower(facts: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for k in _PRICE_FACT_KEYS:
        v = facts.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " ".join(parts).lower()


def _soft_commercial_warnings(facts: Optional[Mapping[str, Any]]) -> List[str]:
    if not facts:
        return []
    out: List[str] = []
    triplets = (
        ("supply_price", "supply_price_unit", "goods"),
        ("service_price", "service_price_unit", "service_object"),
        ("work_price", "work_price_unit", "work_object"),
        ("manufacture_price", "manufacture_price_unit", "product"),
    )
    for total_k, unit_k, subj_k in triplets:
        if (
            _normalize(facts.get(total_k))
            and _normalize(facts.get(unit_k))
            and _normalize(facts.get(subj_k))
        ):
            out.append(
                f"Мягкая проверка: заполнены `{total_k}`, `{unit_k}` и `{subj_k}` — убедитесь, что в §6 договора "
                "количество × цена за единицу согласованы с общей суммой; явная общая сумма в интейке не должна "
                "подменяться расчётом без основания во фактах."
            )
            break
    pt = _normalize(facts.get("payment_terms"))
    pd = _normalize(facts.get("payment_due"))
    if pt and pd and pt == pd and len(pt) > 40:
        out.append(
            "Мягкая проверка: порядок оплаты и сроки оплаты в интейке совпадают дословно — "
            "проверьте, что в §6–7 договора они не смешаны без необходимости."
        )
    vm = _lower(facts.get("vat_mode"))
    blob = _joined_price_blob_lower(facts)
    if not blob:
        return out
    if vm == "с ндс" and "без ндс" in blob:
        out.append(
            "Мягкая проверка: `vat_mode` = «с НДС», но в ценовых полях интейка есть «без НДС» — "
            "возможна двусмысленность суммы и налогов."
        )
    if vm == "без ндс" and (
        "с ндс" in blob
        or "в т.ч. ндс" in blob
        or "в том числе ндс" in blob
        or "включая ндс" in blob
    ):
        out.append(
            "Мягкая проверка: `vat_mode` = «без НДС», но в ценовых полях интейка указано включение НДС — "
            "проверьте согласованность."
        )
    return out


def _normalize(text: Any) -> str:
    return ("" if text is None else str(text)).strip()


def _lower(text: Any) -> str:
    return _normalize(text).lower()


def _entity_snapshot_fragment_ok(key: str, lowered: str, raw: str) -> bool:
    raw_l = _lower(raw)
    if len(raw_l) < 14:
        return True
    frag = raw_l[:72]
    if frag in lowered:
        return True
    fallbacks: Dict[str, Tuple[str, ...]] = {
        "parties": ("сторон", "исполнител", "заказчик", "аренд"),
        "subject": ("предмет", "товар", "услуг", "работ"),
        "price": ("цен", "стоимост", "вознагражден", "арендн", "платеж"),
        "payment_terms": ("оплат", "расчёт", "расчет", "платеж", "предоплат"),
        "deadlines": ("срок", "календар", "поставк", "исполнен"),
        "acceptance": ("приёмк", "приемк", "акт сдач", "сдачи-прием", "приёма-передач"),
        "liability": ("ответственн", "неустойк", "штраф", "пеня", "санкци"),
        "termination": ("расторжен", "прекращен"),
        "disputes": ("спор", "подсудн", "арбитр"),
        "requisites": ("реквизит",),
        "appendices": ("приложен", "приложения"),
    }
    if key in fallbacks and any(h in lowered for h in fallbacks[key]):
        return True
    if key == "price" and any(ch.isdigit() for ch in raw_l) and any(ch.isdigit() for ch in lowered):
        return True
    return False


def _verify_mandatory_contract_entities(
    lowered: str, snapshot: Mapping[str, str]
) -> Optional[str]:
    flag = (os.getenv("CONTRACT_FACT_ENTITIES_HARD") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return None

    for key in CONTRACT_FACT_ENTITY_KEYS:
        raw = _normalize(snapshot.get(key))
        if len(raw) < 14:
            continue
        if key == "requisites":
            if _REQUISITES_PHRASE in lowered:
                continue
        if _entity_snapshot_fragment_ok(key, lowered, raw):
            continue
        return (
            "Черновик не содержит обязательную сущность из интейка "
            f"(fact entity «{key}»); проверьте разделы договора по фактам."
        )
    return None


def _kz_contract_core_rubrics_failed(lowered: str) -> Optional[str]:
    """
    Жёсткие рубрики коммерческого договора РК (стороны, предмет, цена, сроки,
    ответственность/расчёты, акты, форс-мажор, споры, расторжение, приложения).
    Реквизиты проверяются отдельно (_REQUISITES_PHRASE).
    """
    flag = (os.getenv("CONTRACT_HARD_RUBRICS") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return None

    groups: Tuple[Tuple[str, ...], ...] = (
        ("преамбул", "сторон", "исполнител", "поставщик", "заказчик", "подрядчик", "аренд"),
        ("предмет",),
        ("цен", "стоимост", "вознагражден", "арендн", "арендная плата"),
        ("срок", "сроки"),
        ("ответственн", "неустойк", "штраф", "пеня", "санкци"),
        ("оплат", "платеж", "расчёт", "расчет"),
        ("приёмк", "приемк", "акта сдач", "сдачи-прием", "приема-передач"),
        ("форс-мажор", "непреодолимой сил", "форсмажор"),
        ("спор", "арбитр", "подсудн"),
        ("расторжен", "прекращени"),
        ("приложен", "приложения"),
    )
    for variants in groups:
        if not any(v in lowered for v in variants):
            hint = ", ".join(variants[:4])
            return (
                "Черновик договора не содержит обязательной рубрики по контрольному шаблону РК "
                f"(ключи: {hint})."
            )
    return None


def _extract_aliases(section: Union[str, Dict[str, Any]]) -> List[str]:
    aliases: List[str] = []

    if isinstance(section, str):
        s = section.strip()
        if s:
            aliases.append(s)

    elif isinstance(section, dict):
        title = section.get("title")
        if isinstance(title, str) and title.strip():
            aliases.append(title.strip())

        for a in section.get("aliases", []) or []:
            if isinstance(a, str) and a.strip():
                aliases.append(a.strip())

    out: List[str] = []
    seen = set()
    for a in aliases:
        la = a.lower()
        if la not in seen:
            out.append(a)
            seen.add(la)

    return out


def _normalize_key(alias: str) -> str:
    return alias.split(".", 1)[-1].strip().lower()


def verify_contract_text(
    contract_text: str,
    profile: Dict[str, Any],
    facts: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, List[str]]:
    """
    Возвращает (hard_ok, hard_reason, soft_warnings).

    hard_ok=False → pipeline должен бросить RuntimeError(hard_reason).
    soft_warnings → только логирование.
    facts — опционально: мягкие эвристики по коммерческим полям интейка.
    """
    warnings: List[str] = []

    text = _normalize(contract_text)
    if not text:
        return False, "Пустой текст договора", warnings

    if not profile:
        return False, "PROFILE не передан в verifier", warnings

    lowered_text = _lower(text)

    outline = profile.get("outline") or []
    if not outline:
        return False, "В PROFILE отсутствует outline (структура договора)", warnings

    for term in profile.get("forbidden_mix", []) or []:
        if isinstance(term, str) and term.lower() in lowered_text:
            return (
                False,
                f"Обнаружен запрещённый термин/конструкция: {term}",
                warnings,
            )

    if _REQUISITES_PHRASE not in lowered_text:
        return (
            False,
            "Не найден завершающий блок «Реквизиты и подписи сторон»",
            warnings,
        )

    rub_fail = _kz_contract_core_rubrics_failed(lowered_text)
    if rub_fail:
        return False, rub_fail, warnings

    ent_fail = _verify_mandatory_contract_entities(lowered_text, build_contract_fact_snapshot(facts))
    if ent_fail:
        return False, ent_fail, warnings

    try:
        hard_outline_n = int(os.getenv("CONTRACT_OUTLINE_SECTIONS_HARD", "5"))
    except ValueError:
        hard_outline_n = 5
    hard_outline_n = max(1, min(hard_outline_n, len(outline)))

    for section in outline[:hard_outline_n]:
        aliases = _extract_aliases(section)
        found_header = False
        for alias in aliases:
            key = _normalize_key(alias)
            if key and key in lowered_text:
                found_header = True
                break
        if not found_header:
            title = aliases[0] if aliases else str(section)
            return (
                False,
                f"Отсутствует обязательный раздел договора (жёсткая проверка): {title}",
                warnings,
            )

    if facts:
        parties = _normalize(facts.get("parties"))
        if len(parties) >= 20:
            frag = parties[:72].lower()
            if frag and frag not in lowered_text:
                return (
                    False,
                    "Черновик не содержит ожидаемой идентификации сторон по полю `parties`.",
                    warnings,
                )
        subj_parts = [
            _normalize(facts.get(k))
            for k in (
                "goods",
                "service_object",
                "work_object",
                "rent_object",
                "product",
                "subject_of_contract",
            )
        ]
        subj_blob = " ".join(p for p in subj_parts if p).strip()
        if len(subj_blob) >= 18:
            frag = subj_blob[:64].lower()
            if frag and frag not in lowered_text:
                return (
                    False,
                    "Черновик не согласован с предметом из интейка (фрагмент предмета не найден в тексте).",
                    warnings,
                )
        price_blob = _joined_price_blob_lower(facts)
        if price_blob and any(ch.isdigit() for ch in price_blob):
            has_digit = any(ch.isdigit() for ch in text)
            if not has_digit and "цен" not in lowered_text:
                return (
                    False,
                    "В интейке есть цифры по цене/оплате; в тексте договора нет согласованных сумм или явного ценового блока.",
                    warnings,
                )

    req_count = lowered_text.count(_REQUISITES_PHRASE)
    if req_count != 1:
        warnings.append(
            f"Мягкая проверка: фраза «Реквизиты и подписи сторон» встречается {req_count} раз "
            f"(ожидается одна основная секция)."
        )

    positions: List[int] = []
    for section in outline:
        aliases = _extract_aliases(section)
        found_pos: int | None = None

        for alias in aliases:
            key = _normalize_key(alias)
            pos = lowered_text.find(key)
            if pos != -1:
                found_pos = pos
                break

        if found_pos is None:
            title = aliases[0] if aliases else str(section)
            warnings.append(f"Мягкая проверка: не найден раздел outline (подзаголовок): {title}")
            continue

        positions.append(found_pos)

    if len(positions) >= 2 and positions != sorted(positions):
        warnings.append("Мягкая проверка: возможное нарушение порядка разделов договора (outline).")

    last_section = outline[-1]
    last_aliases = _extract_aliases(last_section)

    last_pos = -1
    for alias in last_aliases:
        key = _normalize_key(alias)
        pos = lowered_text.rfind(key)
        if pos != -1:
            last_pos = pos
            break

    if last_pos == -1:
        warnings.append(
            "Мягкая проверка: не удалось позиционировать последний раздел outline для проверки хвоста."
        )
    else:
        tail = lowered_text[last_pos:]
        for section in outline[:-1]:
            for alias in _extract_aliases(section):
                key = _normalize_key(alias)
                if key and key in tail:
                    warnings.append(
                        "Мягкая проверка: после финального раздела обнаружен текст, похожий на другой раздел: "
                        f"{alias}"
                    )
                    break

    for attachment in profile.get("required_attachments", []) or []:
        if isinstance(attachment, str) and attachment.lower() not in lowered_text:
            warnings.append(
                "Мягкая проверка: нет дословного упоминания обязательного приложения: "
                f"{attachment}"
            )

    if "________________" in text or "_______________" in text:
        warnings.append(
            "Мягкая проверка: в тексте есть длинные строки-заполнители «____» — для уровня senior-черновика лучше заполнить из фактов или убрать макет."
        )
    if "указать реквизиты" in lowered_text or "заполняется сторонами" in lowered_text:
        warnings.append(
            "Мягкая проверка: формулировки вида «указать реквизиты» / «заполняется сторонами» при наличии данных в интейке снижают качество; проверьте перенос из parties."
        )

    warnings.extend(_soft_commercial_warnings(facts))

    return True, "", warnings
