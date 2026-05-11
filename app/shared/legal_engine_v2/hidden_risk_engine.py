"""Heuristic hidden-risk detection anchored on facts + domain (no invented norms)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Sequence

from app.shared.legal_engine_v2.legal_logic_engine import HiddenRisk


def _blob(case_facts: Sequence[str]) -> str:
    return " ".join(case_facts or ()).lower()


def _doc_labels(used_docs: Sequence[Any]) -> List[str]:
    out: List[str] = []
    for d in used_docs or []:
        sid = str(getattr(d, "source_id", "") or "")
        n = str(getattr(d, "number", "") or "")
        out.append(f"{sid}#{n}" if n else sid)
    return out


def detect_hidden_risks(
    case_facts: Sequence[str],
    used_docs: Sequence[Any],
    legal_basis_map: Mapping[str, Any],
    domain: str,
) -> List[HiddenRisk]:
    """Emit structured risks; ``legal_basis_map`` reserved for slot-aware checks."""

    low = _blob(case_facts)
    labels = _doc_labels(used_docs)
    basis_hint = labels[:6]
    risks: List[HiddenRisk] = []
    _ = legal_basis_map

    def add(title: str, expl: str, lvl: str, trig: List[str], opp: str, mit: str, ev: List[str]) -> None:
        rid = hashlib.sha256((title + expl[:40]).encode()).hexdigest()[:12]
        risks.append(
            HiddenRisk(
                risk_id=f"risk_{rid}",
                title=title,
                explanation=expl,
                risk_level=lvl,
                triggered_by_facts=trig,
                legal_basis=basis_hint,
                how_opponent_can_use_it=opp,
                how_to_reduce_risk=mit,
                evidence_needed=ev,
            )
        )

    if domain in ("civil", "mixed") or any(x in low for x in ("договор", "долг", "взыскан")):
        if any(x in low for x in ("давност", "срок иск", "пропустил срок")):
            add(
                "Срок исковой давности / процессуальные сроки",
                "Даже при сильной правовой позиции пропуск срока может закрыть доступ к защите.",
                "high",
                ["упоминание срока/давности"],
                "Заявит о пропуске срока или злоупотреблении правом.",
                "Проверить начало течения срока и основания восстановления.",
                ["документы о получении знания о нарушении", "дата последнего исполнения"],
            )
        if not any(x in low for x in ("договор", "акт", "чек", "переписк")):
            add(
                "Слабая доказательственная база по обязательству",
                "Право может существовать, но без первичных доказательств трудно доказать факт.",
                "medium",
                ["нет ссылки на письменные доказательства"],
                "Оспорит факт возникновения обязательства или его размер.",
                "Собрать первичку: договор/акт/платежи/переписку.",
                ["договор или переписка", "платежные документы"],
            )

    if domain in ("tax", "mixed") or any(x in low for x in ("налог", "камерал", "проверк")):
        add(
            "Налоговый контроль и доначисления",
            "Риск переквалификации и доначислений при недостатке подтверждающих документов.",
            "high",
            ["налог/проверка/уведомление"],
            "Доначислит налог и применит санкции при слабой первичке.",
            "Упорядочить первичку; проверить специальные нормы НК vs общие гарантии ПК.",
            ["учетные регистры", "акты сверки", "пояснения к вычетам"],
        )

    if domain in ("admin", "administrative", "mixed") or any(
        x in low for x in ("штраф", "протокол", "коап", "госорган")
    ):
        add(
            "Административный срок обжалования / компетенция органа",
            "Ошибка органа или пропуск срока делает защиту процессуально уязвимой.",
            "medium",
            ["штраф", "акт органа", "отказ"],
            "Заявит о надлежащей процедуре и своевременности обращения.",
            "Проверить АППК/КоАП и обязательный досудебный порядок.",
            ["копия акта", "подтверждение обращений"],

        )

    if domain in ("criminal", "mixed") or any(
        x in low for x in ("уголовн", "мошенничество", "ук ", "преступлен")
    ):
        add(
            "Уголовно-правовой риск без подтверждённого состава",
            "Факты могут трактоваться по-разному; квалификация требует проверки доказательств.",
            "high",
            ["ключевые слова уголовного риска"],
            "Будет доказывать умысел/обман и причинность.",
            "Не формулировать выводы о виновности; работать с версией и доказательствами законно.",
            ["документы передачи денег", "переписка до сделки", "версия событий"],

        )

    if domain in ("bankruptcy", "mixed") or "банкрот" in low:
        add(
            "Банкротство: оспаривание сделок и субсидиарка",
            "Риск оспаривания сделок и привлечения контролирующих лиц.",
            "high",
            ["банкрот", "сделк"],
            "Оспорит сделки как наносящие ущерб кредиторам.",
            "Инвентаризация сделок; юридический аудит корпоративных решений.",
            ["учредительные документы", "бухгалтерская отчетность"],

        )

    if not risks:
        add(
            "Отсутствие формализованных рисков по ключевым маркерам",
            "Явных процессуальных ловушек по текущим маркерам не выявлено — это не исключает рисков после уточнения фактов.",
            "low",
            ["общий профилактический учёт"],
            "Может использовать любые пробелы после уточнения дела.",
            "Уточнить факты и доказательства перед процессуальной эскалацией.",
            [],

        )

    return risks[:30]


__all__ = ["detect_hidden_risks"]
