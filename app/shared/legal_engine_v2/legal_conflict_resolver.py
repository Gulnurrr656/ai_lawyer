"""Legal conflict resolver for Document Factory v2 / Legal Engine v2.

The AI-юрист must work with **legal duality**:

- A single question is regulated by several codes/laws.
- Norms may *appear* contradictory.
- We must determine the iерархию, специальную норму, общую норму, исключение
  и стратегию защиты — *without inventing statutes*.

This module is pure-Python. No I/O, no LLM, no network. Inputs are
:class:`RerankedDoc` objects coming from the v2 retrieval pipeline.

Public API:

- :class:`LegalConflict`
- :class:`LegalDefenseArgument`
- :func:`detect_legal_conflicts`
- :func:`resolve_conflict_by_hierarchy`
- :func:`build_defense_arguments`
- :func:`render_conflict_block`
- :func:`render_defense_block`

Conflict types (``LegalConflict.conflict_type``):

- ``hierarchy_conflict``      — нормы разного уровня иерархии
- ``same_level_conflict``     — два кодекса одного уровня без явной спец-нормы
- ``general_vs_special``      — общая vs специальная норма одного уровня
- ``procedure_vs_material``   — материальный кодекс + процессуальный кодекс
                                  (формальное «соседство», не настоящий конфликт)
- ``tax_special_control``     — особый случай НК vs ПК для налогового контроля
                                  (НК специальный по предмету; ПК общий слой)
- ``no_real_conflict``        — единственный класс источников; конфликта нет
- ``unresolved``              — конфликт есть, разрешение неочевидно
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from app.shared.legal_engine_v2.legal_hierarchy import (
    CLASS_CODE,
    CLASS_CONSTITUTION,
    CLASS_CONSTITUTIONAL_LAW,
    CLASS_JUDICIAL_GUIDANCE,
    CLASS_LAW,
    CLASS_SUBORDINATE,
    classify_legal_source,
    get_source_authority_level,
)
from app.shared.legal_engine_v2.schemas import (
    LegalQueryUnderstanding,
    RerankedDoc,
)

# ---------------------------------------------------------------------------
# Conflict types
# ---------------------------------------------------------------------------

CONFLICT_HIERARCHY = "hierarchy_conflict"
CONFLICT_SAME_LEVEL = "same_level_conflict"
CONFLICT_GENERAL_VS_SPECIAL = "general_vs_special"
CONFLICT_PROCEDURE_VS_MATERIAL = "procedure_vs_material"
CONFLICT_TAX_SPECIAL_CONTROL = "tax_special_control"
CONFLICT_NO_REAL = "no_real_conflict"
CONFLICT_UNRESOLVED = "unresolved"

CONFLICT_TYPES: Tuple[str, ...] = (
    CONFLICT_HIERARCHY,
    CONFLICT_SAME_LEVEL,
    CONFLICT_GENERAL_VS_SPECIAL,
    CONFLICT_PROCEDURE_VS_MATERIAL,
    CONFLICT_TAX_SPECIAL_CONTROL,
    CONFLICT_NO_REAL,
    CONFLICT_UNRESOLVED,
)

# Conflict types that count as "resolved" for verifier purposes.
RESOLVED_CONFLICT_TYPES: Tuple[str, ...] = (
    CONFLICT_HIERARCHY,
    CONFLICT_GENERAL_VS_SPECIAL,
    CONFLICT_PROCEDURE_VS_MATERIAL,
    CONFLICT_TAX_SPECIAL_CONTROL,
    CONFLICT_NO_REAL,
)


# ---------------------------------------------------------------------------
# Source-id stems we care about
# ---------------------------------------------------------------------------

_NK = "kz_nk_code"
_PK = "kz_pk_code"
_GK = "kz_gk_code"
_GK_DUP = "kz_gk__code"
_GPK = "kz_gpk_code"
_APPC = "kz_appc_code"
_KOAP = "kz_koap_code"
_UK = "kz_uk_code"
# NOTE: уголовно-процессуальный кодекс = ``kz_upk_code`` (если есть в RAG).
# ``kz_pk_code`` — это **Предпринимательский кодекс**, не УПК.
_TK = "kz_tk_code"
_FAMILY = "kz_family_code"

_PROCEDURAL_STEMS: Tuple[str, ...] = (
    _GPK, _APPC, "kz_law_enforcement_code", "kz_law_arbitration_code",
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LegalConflict:
    """A pair-wise / multi-source legal conflict (or a non-conflict notice)."""

    issue: str = ""
    conflict_type: str = CONFLICT_NO_REAL

    higher_level_docs: List[RerankedDoc] = field(default_factory=list)
    same_level_docs: List[RerankedDoc] = field(default_factory=list)
    special_docs: List[RerankedDoc] = field(default_factory=list)
    general_docs: List[RerankedDoc] = field(default_factory=list)
    judicial_guidance_docs: List[RerankedDoc] = field(default_factory=list)

    resolution_rule: str = ""
    recommended_argument: str = ""
    warnings: List[str] = field(default_factory=list)

    def is_resolved(self) -> bool:
        return self.conflict_type in RESOLVED_CONFLICT_TYPES

    def to_dict(self) -> dict:
        return {
            "issue": self.issue,
            "conflict_type": self.conflict_type,
            "higher_level_doc_ids": [d.doc_id for d in self.higher_level_docs if d.doc_id],
            "same_level_doc_ids": [d.doc_id for d in self.same_level_docs if d.doc_id],
            "special_doc_ids": [d.doc_id for d in self.special_docs if d.doc_id],
            "general_doc_ids": [d.doc_id for d in self.general_docs if d.doc_id],
            "judicial_guidance_doc_ids": [
                d.doc_id for d in self.judicial_guidance_docs if d.doc_id
            ],
            "resolution_rule": self.resolution_rule,
            "recommended_argument": self.recommended_argument,
            "warnings": list(self.warnings),
            "resolved": self.is_resolved(),
        }


@dataclass
class LegalDefenseArgument:
    """A defensive argument structured around RAG-anchored norms."""

    issue: str = ""
    taxpayer_or_client_position: str = ""
    authority_position: str = ""

    applicable_hierarchy: List[str] = field(default_factory=list)
    special_norm: str = ""

    procedural_guarantees: List[str] = field(default_factory=list)
    attack_points: List[str] = field(default_factory=list)
    evidence_needed: List[str] = field(default_factory=list)

    recommended_action: str = ""

    # Doc IDs that anchor this defense argument.
    anchored_doc_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        hier = list(self.applicable_hierarchy)
        return {
            "issue": self.issue,
            # Spec alias (same value as taxpayer_or_client_position).
            "client_position": self.taxpayer_or_client_position,
            "taxpayer_or_client_position": self.taxpayer_or_client_position,
            "authority_position": self.authority_position,
            "applicable_hierarchy": hier,
            "applicable_hierarchy_text": " → ".join(hier) if hier else "",
            "special_norm": self.special_norm,
            "procedural_guarantees": list(self.procedural_guarantees),
            "attack_points": list(self.attack_points),
            "evidence_needed": list(self.evidence_needed),
            "recommended_action": self.recommended_action,
            "anchored_doc_ids": list(self.anchored_doc_ids),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sid(d: RerankedDoc) -> str:
    return (getattr(d, "source_id", "") or "").strip().lower()


def _has(docs: Sequence[RerankedDoc], stem: str) -> bool:
    return any(stem in _sid(d) for d in docs)


def _filter(docs: Sequence[RerankedDoc], stems: Sequence[str]) -> List[RerankedDoc]:
    return [d for d in docs if any(stem in _sid(d) for stem in stems)]


def _filter_by_class(
    docs: Sequence[RerankedDoc], cls_set: Sequence[str]
) -> List[RerankedDoc]:
    return [d for d in docs if classify_legal_source(d) in cls_set]


def _is_tax_control_query(
    query: str, understanding: LegalQueryUnderstanding | None
) -> bool:
    q = (query or "").lower()
    direct = any(
        marker in q
        for marker in (
            "налоговая проверк",
            "налоговый контрол",
            "налоговая пришла",
            "проверка предприним",
            "проверка бизнес",
        )
    )
    if direct:
        return True
    if understanding is None:
        return False
    domains = set((understanding.legal_domains or []))
    return ("tax" in domains and ("control" in domains or "business" in domains))


def _is_business_protection_query(
    query: str, understanding: LegalQueryUnderstanding | None
) -> bool:
    q = (query or "").lower()
    if any(marker in q for marker in ("предпринимат", "бизнес")):
        return True
    if understanding and "business" in (understanding.legal_domains or ()):
        return True
    return False


# ---------------------------------------------------------------------------
# detect_legal_conflicts
# ---------------------------------------------------------------------------

def detect_legal_conflicts(
    docs: Sequence[RerankedDoc],
    understanding: LegalQueryUnderstanding | None = None,
) -> List[LegalConflict]:
    """Inspect ``docs`` and emit the relevant :class:`LegalConflict` records.

    The function never invents statutes; it only describes the *relationship*
    between the documents that the retrieval/rerank stage already pulled.

    Order of detection (each independent — multiple may fire):

    1. Tax + Business special control (НК vs ПК for tax inspections).
    2. Procedure vs material (e.g. ГК + ГПК appearing together).
    3. Hierarchy conflict (different authority classes co-exist).
    4. Same-level conflict (≥2 codes that are not in the procedure-vs-material
       case and have no obvious general-vs-special split).
    5. NP VS without code/law (unresolved — guidance without a primary norm).
    """
    docs = list(docs or [])
    if not docs:
        return []

    raw_query = ""
    if understanding is not None:
        raw_query = understanding.raw_query or ""

    out: List[LegalConflict] = []

    # ---- 1. Tax_special_control --------------------------------------------
    has_nk = _has(docs, _NK)
    has_pk = _has(docs, _PK)
    if (has_nk or has_pk) and _is_tax_control_query(raw_query, understanding):
        nk_docs = _filter(docs, [_NK])
        pk_docs = _filter(docs, [_PK])
        out.append(
            LegalConflict(
                issue=(
                    "Соотношение Налогового кодекса и Предпринимательского "
                    "кодекса в части налогового контроля предпринимателя"
                ),
                conflict_type=CONFLICT_TAX_SPECIAL_CONTROL,
                same_level_docs=nk_docs + pk_docs,
                special_docs=nk_docs,
                general_docs=pk_docs,
                resolution_rule=(
                    "Налоговый кодекс — специальный источник по налоговому "
                    "контролю, налоговым проверкам и налоговым обязательствам. "
                    "Предпринимательский кодекс — общий слой защиты "
                    "предпринимателя; применяется ДОПОЛНИТЕЛЬНО только в той "
                    "части, которая не урегулирована Налоговым кодексом. "
                    "Нельзя автоматически применять общие гарантии ПК против "
                    "специальной процедуры НК, если НК прямо регулирует "
                    "вопрос."
                ),
                recommended_argument=(
                    "Сначала проверить, что говорит Налоговый кодекс по "
                    "конкретной форме контроля (проверка / хронометраж / "
                    "обследование / камеральный контроль / запрос документов). "
                    "Если НК прямо урегулировал процедуру — применяется НК. "
                    "Если НК молчит по конкретной гарантии — обращаться к ПК "
                    "как к дополнительному защитному слою. "
                    "Не делать вывод «НК выше ПК» — оба являются кодексами "
                    "одного уровня."
                ),
                warnings=(
                    []
                    if (has_nk and has_pk)
                    else [
                        (
                            "Налоговый кодекс не найден в used_docs"
                            if not has_nk
                            else "Предпринимательский кодекс не найден в used_docs"
                        )
                    ]
                ),
            )
        )

    # ---- 2. Procedure vs material ------------------------------------------
    procedure_docs = _filter(docs, _PROCEDURAL_STEMS)
    material_codes = [
        d for d in docs
        if classify_legal_source(d) == CLASS_CODE
        and not any(stem in _sid(d) for stem in _PROCEDURAL_STEMS)
        and not any(stem in _sid(d) for stem in (_KOAP, _UK))
    ]
    if procedure_docs and material_codes:
        out.append(
            LegalConflict(
                issue=(
                    "Сосуществование материального и процессуального кодексов"
                ),
                conflict_type=CONFLICT_PROCEDURE_VS_MATERIAL,
                higher_level_docs=[],
                same_level_docs=procedure_docs + material_codes,
                special_docs=procedure_docs,
                general_docs=material_codes,
                resolution_rule=(
                    "Материальный кодекс (ГК / НК / ТК / СК и др.) и "
                    "процессуальный кодекс (ГПК / АППК / УПК) НЕ являются "
                    "конфликтующими. Материальный кодекс задаёт права и "
                    "обязанности; процессуальный — порядок их защиты. "
                    "Оба применяются совместно: материальное обоснование + "
                    "процессуальный порядок."
                ),
                recommended_argument=(
                    "В документе сначала привести материальную норму "
                    "(основание права/обязанности), затем процессуальную "
                    "норму (как именно реализуется защита в суде/у органа)."
                ),
            )
        )

    # ---- 3. Hierarchy conflict ---------------------------------------------
    classes_present: Dict[str, RerankedDoc] = {}
    for d in docs:
        cls = classify_legal_source(d)
        if cls in (
            CLASS_CONSTITUTION,
            CLASS_CONSTITUTIONAL_LAW,
            CLASS_CODE,
            CLASS_LAW,
            CLASS_SUBORDINATE,
        ):
            classes_present.setdefault(cls, d)
    if len(classes_present) >= 2:
        ordered = sorted(
            classes_present.items(),
            key=lambda kv: -get_source_authority_level(kv[1].source_id, kv[1].doc_type),
        )
        higher_cls, higher_doc = ordered[0]
        lower_cls, lower_doc = ordered[-1]
        if higher_cls != lower_cls:
            out.append(
                LegalConflict(
                    issue="Сосуществование источников разного уровня иерархии",
                    conflict_type=CONFLICT_HIERARCHY,
                    higher_level_docs=[higher_doc],
                    same_level_docs=[],
                    general_docs=[lower_doc],
                    resolution_rule=(
                        "При прямом противоречии норм разного уровня "
                        "применяется акт более высокого уровня "
                        f"({higher_cls})."
                    ),
                    recommended_argument=(
                        "Сначала проверить высший источник; если он не даёт "
                        "ответа — обращаться к нижестоящему. Если нижестоящий "
                        "противоречит высшему — он не применяется в этой "
                        "части."
                    ),
                )
            )

    # ---- 4. Same-level conflict (≥2 codes that are not procedure-vs-mat) --
    code_docs = _filter_by_class(docs, [CLASS_CODE])
    distinct_code_sids = {
        _sid(d).split("__", 1)[0] if "__" in _sid(d) else _sid(d)
        for d in code_docs
    }
    if (
        len(distinct_code_sids) >= 2
        and not any(c.conflict_type == CONFLICT_TAX_SPECIAL_CONTROL for c in out)
        and not any(c.conflict_type == CONFLICT_PROCEDURE_VS_MATERIAL for c in out)
    ):
        out.append(
            LegalConflict(
                issue=(
                    "Несколько кодексов одного уровня регулируют один вопрос"
                ),
                conflict_type=CONFLICT_SAME_LEVEL,
                same_level_docs=list(code_docs),
                resolution_rule=(
                    "Кодексы одного уровня не подчиняются друг другу. "
                    "Сначала искать специальную норму по предмету; затем "
                    "прямую отсылку одного кодекса к другому; затем "
                    "исключение. Если конфликт неразрешим — отметить как "
                    "требующий судебной/официальной проверки."
                ),
                recommended_argument=(
                    "Не утверждать, что один кодекс «выше» другого. "
                    "Найти специальный кодекс по предмету и применить его в "
                    "специальной части; общий кодекс — в неурегулированной."
                ),
                warnings=[],
            )
        )

    # ---- 5. NP VS без основной нормы кодекса/закона ------------------------
    has_judicial = any(
        classify_legal_source(d) == CLASS_JUDICIAL_GUIDANCE for d in docs
    )
    has_material = any(
        classify_legal_source(d) in (CLASS_CONSTITUTION, CLASS_CODE, CLASS_LAW)
        for d in docs
    )
    if has_judicial and not has_material:
        judicial_docs = _filter_by_class(docs, [CLASS_JUDICIAL_GUIDANCE])
        out.append(
            LegalConflict(
                issue=(
                    "НП ВС / КС присутствует, но нет основной нормы "
                    "кодекса или закона"
                ),
                conflict_type=CONFLICT_UNRESOLVED,
                judicial_guidance_docs=judicial_docs,
                resolution_rule=(
                    "Нормативные постановления ВС и КС объясняют применение "
                    "кодексов и законов, но не заменяют их. Без материальной "
                    "нормы кодекса/закона вывод не может считаться полным."
                ),
                recommended_argument=(
                    "Добавить в анализ основную норму материального права "
                    "(кодекс или закон) до составления документа. Если "
                    "норма не найдена в RAG — отметить пробел и не "
                    "формулировать вывод."
                ),
                warnings=[
                    "В RAG-базе не найдена основная норма кодекса/закона; "
                    "требуется дополнительная проверка."
                ],
            )
        )

    return out


# ---------------------------------------------------------------------------
# resolve_conflict_by_hierarchy
# ---------------------------------------------------------------------------

def resolve_conflict_by_hierarchy(conflict: LegalConflict) -> LegalConflict:
    """Fill ``conflict.resolution_rule`` / ``conflict.recommended_argument``
    if the detector left them empty.

    Returns the same object (mutated). Idempotent.
    """
    if conflict.resolution_rule and conflict.recommended_argument:
        return conflict

    if conflict.conflict_type == CONFLICT_HIERARCHY:
        if not conflict.resolution_rule:
            conflict.resolution_rule = (
                "При противоречии между нормами разного уровня применяется "
                "акт более высокого уровня."
            )
        if not conflict.recommended_argument:
            conflict.recommended_argument = (
                "Опираться на высший источник; если он не даёт ответа — "
                "обращаться к нижестоящему. Несоответствие нижестоящего "
                "высшему делает соответствующее положение неприменимым."
            )

    elif conflict.conflict_type == CONFLICT_SAME_LEVEL:
        if not conflict.resolution_rule:
            conflict.resolution_rule = (
                "Кодексы одного уровня применяются по правилу: специальная "
                "норма имеет приоритет над общей; при отсутствии прямой "
                "отсылки и исключения — обе действуют параллельно."
            )
        if not conflict.recommended_argument:
            conflict.recommended_argument = (
                "Не делать вывод «один кодекс выше другого». Найти "
                "специальный кодекс по предмету; общий кодекс применять в "
                "неурегулированной части."
            )

    elif conflict.conflict_type == CONFLICT_GENERAL_VS_SPECIAL:
        if not conflict.resolution_rule:
            conflict.resolution_rule = (
                "Lex specialis derogat legi generali — специальная норма "
                "имеет приоритет над общей в её предмете."
            )
        if not conflict.recommended_argument:
            conflict.recommended_argument = (
                "Сначала применять специальную норму по предмету; общая "
                "норма — для неурегулированных вопросов."
            )

    elif conflict.conflict_type == CONFLICT_PROCEDURE_VS_MATERIAL:
        if not conflict.resolution_rule:
            conflict.resolution_rule = (
                "Материальный и процессуальный кодексы не конфликтуют: "
                "материал даёт права/обязанности, процесс — порядок защиты."
            )
        if not conflict.recommended_argument:
            conflict.recommended_argument = (
                "Привести материальное основание + процессуальный порядок "
                "защиты вместе."
            )

    elif conflict.conflict_type == CONFLICT_TAX_SPECIAL_CONTROL:
        # Already populated by detect_legal_conflicts with full text.
        pass

    elif conflict.conflict_type == CONFLICT_UNRESOLVED:
        if not conflict.resolution_rule:
            conflict.resolution_rule = (
                "Конфликт неразрешим автоматически — требуется обращение к "
                "судебной/официальной практике или дополнительный поиск "
                "нормы."
            )
        if not conflict.recommended_argument:
            conflict.recommended_argument = (
                "Отметить пробел; не формулировать вывод без материальной "
                "нормы."
            )

    return conflict


# ---------------------------------------------------------------------------
# build_defense_arguments
# ---------------------------------------------------------------------------

def build_defense_arguments(
    query: str,
    docs: Sequence[RerankedDoc],
    conflicts: Sequence[LegalConflict],
    understanding: LegalQueryUnderstanding | None = None,
) -> List[LegalDefenseArgument]:
    """Build a list of :class:`LegalDefenseArgument` from RAG docs + conflicts.

    Currently produces a defense argument for:
    1. Tax control / business protection scenarios (НК vs ПК).
    2. Generic civil-debt scenarios (ГК + ГПК).

    No statute is invented. ``anchored_doc_ids`` lists the doc_ids that
    actually back the argument.
    """
    out: List[LegalDefenseArgument] = []
    docs = list(docs or [])

    # Find any tax_special_control conflict.
    tax_conflict = next(
        (c for c in conflicts if c.conflict_type == CONFLICT_TAX_SPECIAL_CONTROL),
        None,
    )

    if tax_conflict or (
        _is_tax_control_query(query, understanding)
        or _is_business_protection_query(query, understanding)
    ):
        nk_docs = _filter(docs, [_NK])
        pk_docs = _filter(docs, [_PK])
        anchored = [d.doc_id for d in nk_docs + pk_docs if d.doc_id]
        out.append(
            LegalDefenseArgument(
                issue=(
                    "Защита предпринимателя при налоговом контроле "
                    "(проверка/хронометраж/обследование/камеральный контроль/"
                    "запрос документов)"
                ),
                taxpayer_or_client_position=(
                    "Налоговый орган обязан действовать в рамках Налогового "
                    "кодекса (специальный источник по налоговому контролю). "
                    "При отсутствии правового основания (предписание/решение/"
                    "полномочия/предмет/период) действия органа подлежат "
                    "оспариванию. Общие гарантии Предпринимательского кодекса "
                    "применяются дополнительно — в части, не урегулированной "
                    "Налоговым кодексом."
                ),
                authority_position=(
                    "Налоговый орган может ссылаться на Налоговый кодекс как "
                    "на специальное основание контроля. В отдельных формах "
                    "контроля (камеральный, запрос документов) классическое "
                    "предварительное уведомление может не требоваться, но "
                    "правовое основание (предписание/решение/полномочия) "
                    "обязательно."
                ),
                applicable_hierarchy=[
                    "Конституция РК",
                    "Налоговый кодекс РК (специальный по налоговому контролю)",
                    "Предпринимательский кодекс РК (общий слой защиты "
                    "предпринимателя — в неурегулированной НК части)",
                    "ГПК / АППК (процессуальный порядок оспаривания)",
                    "НП ВС / КС (объясняют применение)",
                ],
                special_norm=(
                    "Налоговый кодекс — специальный источник по налоговому "
                    "контролю. Применяется в первую очередь."
                ),
                procedural_guarantees=[
                    "право требовать предъявления предписания / решения о проверке",
                    "право проверить полномочия должностных лиц налогового органа",
                    "право знать предмет проверки и проверяемый период",
                    "право знать сроки проверки",
                    "право фиксировать ход проверки и получать копии актов",
                    "право обжаловать действия / акты в порядке АППК или "
                    "вышестоящему налоговому органу",
                ],
                attack_points=[
                    "не предъявлено предписание / решение о проверке",
                    "проверяющие лица не указаны или их полномочия не подтверждены",
                    "вышли за пределы предмета проверки",
                    "вышли за пределы проверяемого периода",
                    "нарушены сроки проверки",
                    "не вручены документы налогоплательщику",
                    "запрос документов сделан вне формы налогового контроля",
                ],
                evidence_needed=[
                    "копия предписания/решения о проверке",
                    "удостоверения проверяющих лиц",
                    "перечень изъятых/запрошенных документов",
                    "акты, протоколы, уведомления",
                    "переписка с налоговым органом",
                    "фиксация даты, времени, состава комиссии",
                ],
                recommended_action=(
                    "Не отвечать «да/нет» на вопрос «может ли налоговая прийти "
                    "без уведомления». Сначала определить вид налогового "
                    "контроля; затем проверить НК (специальный источник); "
                    "затем ПК как дополнительный слой по неурегулированной "
                    "части; затем готовить процессуальное оспаривание (АППК) "
                    "по выявленным нарушениям. В отдельных формах контроля "
                    "налоговая может действовать без классического "
                    "предварительного уведомления, НО не без правового "
                    "основания. Если основания нет — есть аргументы для "
                    "оспаривания."
                ),
                anchored_doc_ids=anchored,
            )
        )

    # Civil-debt defense (ГК + ГПК).
    has_gk = _has(docs, _GK) or _has(docs, _GK_DUP)
    has_gpk = _has(docs, _GPK)
    if (has_gk or has_gpk) and any(
        marker in (query or "").lower()
        for marker in ("долг", "взыскан", "договор", "задолженност", "иск")
    ):
        gk_docs = _filter(docs, [_GK, _GK_DUP])
        gpk_docs = _filter(docs, [_GPK])
        anchored = [d.doc_id for d in gk_docs + gpk_docs if d.doc_id]
        out.append(
            LegalDefenseArgument(
                issue=(
                    "Гражданско-правовая позиция по взысканию задолженности "
                    "по договору"
                ),
                taxpayer_or_client_position=(
                    "Сторона, исполнившая обязательство, имеет право требовать "
                    "встречного исполнения и/или возмещения убытков (ГК РК). "
                    "Защита реализуется в суде в порядке ГПК РК."
                ),
                authority_position=(
                    "Должник может ссылаться на исполнение, прекращение, "
                    "истечение срока исковой давности или иные основания, "
                    "предусмотренные ГК РК."
                ),
                applicable_hierarchy=[
                    "Конституция РК",
                    "Гражданский кодекс РК (материальное основание)",
                    "Гражданский процессуальный кодекс РК (порядок защиты)",
                    "НП ВС по гражданским делам (применение)",
                ],
                special_norm=(
                    "Специальная норма — конкретная статья ГК РК о виде "
                    "обязательства/ответственности; для процедуры — "
                    "соответствующая глава ГПК РК."
                ),
                procedural_guarantees=[
                    "право подать иск в порядке ГПК РК",
                    "право требовать обеспечительных мер",
                    "право представлять доказательства",
                    "право на судебную защиту в разумный срок",
                ],
                attack_points=[
                    "несоблюдение досудебного порядка (если требуется)",
                    "неверное определение подсудности",
                    "истёкший срок исковой давности",
                    "недоказанность факта/размера задолженности",
                ],
                evidence_needed=[
                    "оригинал/копия договора и приложений",
                    "акты выполненных работ / накладные / счета",
                    "переписка сторон",
                    "расчёт задолженности с разбивкой по периодам",
                    "доказательства направления претензии",
                ],
                recommended_action=(
                    "Сначала направить досудебную претензию (ГК РК), затем "
                    "иск в порядке ГПК РК. Привести материальную норму "
                    "ГК + процессуальную норму ГПК + при наличии — НП ВС."
                ),
                anchored_doc_ids=anchored,
            )
        )

    return out


# ---------------------------------------------------------------------------
# Rendering helpers (used by writer / answer engine)
# ---------------------------------------------------------------------------

def render_conflict_block(conflicts: Sequence[LegalConflict]) -> str:
    """Render conflicts as a bracket-headed text block."""
    if not conflicts:
        return ""
    parts: List[str] = []
    for c in conflicts:
        parts.append(f"— Тип: {c.conflict_type}")
        if c.issue:
            parts.append(f"  Вопрос: {c.issue}")
        if c.resolution_rule:
            parts.append(f"  Правило разрешения: {c.resolution_rule}")
        if c.recommended_argument:
            parts.append(f"  Рекомендуемый аргумент: {c.recommended_argument}")
        if c.warnings:
            for w in c.warnings:
                parts.append(f"  Предупреждение: {w}")
        parts.append("")
    return "\n".join(parts).rstrip()


def render_defense_block(defenses: Sequence[LegalDefenseArgument]) -> str:
    """Render defense arguments as a bracket-headed text block."""
    if not defenses:
        return ""
    parts: List[str] = []
    for a in defenses:
        if a.issue:
            parts.append(f"— Вопрос: {a.issue}")
        if a.taxpayer_or_client_position:
            parts.append(f"  Позиция клиента: {a.taxpayer_or_client_position}")
        if a.authority_position:
            parts.append(f"  Позиция органа/контрагента: {a.authority_position}")
        if a.applicable_hierarchy:
            parts.append(
                "  Иерархия применимых норм: "
                + " → ".join(a.applicable_hierarchy)
            )
        if a.special_norm:
            parts.append(f"  Специальная норма: {a.special_norm}")
        if a.procedural_guarantees:
            parts.append("  Процессуальные гарантии:")
            for g in a.procedural_guarantees:
                parts.append(f"    • {g}")
        if a.attack_points:
            parts.append("  Точки для оспаривания:")
            for p in a.attack_points:
                parts.append(f"    • {p}")
        if a.evidence_needed:
            parts.append("  Необходимые доказательства:")
            for e in a.evidence_needed:
                parts.append(f"    • {e}")
        if a.recommended_action:
            parts.append(f"  Рекомендуемое действие: {a.recommended_action}")
        parts.append("")
    return "\n".join(parts).rstrip()


__all__ = [
    "CONFLICT_GENERAL_VS_SPECIAL",
    "CONFLICT_HIERARCHY",
    "CONFLICT_NO_REAL",
    "CONFLICT_PROCEDURE_VS_MATERIAL",
    "CONFLICT_SAME_LEVEL",
    "CONFLICT_TAX_SPECIAL_CONTROL",
    "CONFLICT_TYPES",
    "CONFLICT_UNRESOLVED",
    "LegalConflict",
    "LegalDefenseArgument",
    "RESOLVED_CONFLICT_TYPES",
    "build_defense_arguments",
    "detect_legal_conflicts",
    "render_conflict_block",
    "render_defense_block",
    "resolve_conflict_by_hierarchy",
]
