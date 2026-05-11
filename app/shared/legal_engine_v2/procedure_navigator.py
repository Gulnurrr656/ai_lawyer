"""Procedure Navigator V2.

Practical filing routes for legal documents in Kazakhstan: where to file,
through which platform, what to attach, whether ЭЦП is required, what to do
after submission, what to watch for.

This module is **deterministic and pure-Python** — no I/O, no LLM. Routes are
encoded as static :class:`FilingRoute` records selected by ``doc_type`` (with
some query-text refinement, e.g. "ТОО" vs "физическое лицо" for bankruptcy).

It intentionally does NOT compute exact госпошлина values, exact подсудность
addresses, or production URLs — those depend on facts the user must supply
and on currently-valid corpus data. Instead it gives the canonical *route*
plus a list of fields the user / lawyer must verify before submission.

Public API:

- :class:`ProcedureStep`
- :class:`FilingRoute`
- :class:`ProcedureGuide`
- :func:`build_procedure_guide`
- :func:`detect_filing_route`
- :func:`get_required_documents_for_doc_type`
- :func:`render_procedure_section`
- :func:`render_procedure_block`  (alias used by answer engine)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Sequence

# ---------------------------------------------------------------------------
# Route type vocabulary (must match the user spec exactly — referenced in
# prompts, tests and verifier checks).
# ---------------------------------------------------------------------------

ROUTE_COURT = "court"
ROUTE_ADMIN_COURT = "administrative_court"
ROUTE_EGOV = "egov"
ROUTE_JUDICIAL_CABINET = "judicial_cabinet"
ROUTE_TAX_AUTHORITY = "tax_authority"
ROUTE_KGD = "kgd"
ROUTE_ENFORCEMENT = "enforcement"
ROUTE_NOTARY = "notary"
ROUTE_PRETRIAL = "pretrial"
ROUTE_INTERNAL_COMPANY = "internal_company"
ROUTE_INTERNAL = "internal"
ROUTE_ADMIN_BODY_OR_COURT = "administrative_body_or_court"
ROUTE_COURT_OR_ENFORCEMENT_AUTHORITY = "court_or_enforcement_authority"
ROUTE_OTHER = "other"

ROUTE_TYPES: tuple[str, ...] = (
    ROUTE_COURT,
    ROUTE_ADMIN_COURT,
    ROUTE_EGOV,
    ROUTE_JUDICIAL_CABINET,
    ROUTE_TAX_AUTHORITY,
    ROUTE_KGD,
    ROUTE_ENFORCEMENT,
    ROUTE_NOTARY,
    ROUTE_PRETRIAL,
    ROUTE_INTERNAL_COMPANY,
    ROUTE_INTERNAL,
    ROUTE_ADMIN_BODY_OR_COURT,
    ROUTE_COURT_OR_ENFORCEMENT_AUTHORITY,
    ROUTE_OTHER,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProcedureStep:
    step_number: int
    title: str
    description: str = ""
    responsible_party: str = ""
    platform: str | None = None
    authority: str | None = None
    required_documents: List[str] = field(default_factory=list)
    legal_basis_doc_ids: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "title": self.title,
            "description": self.description,
            "responsible_party": self.responsible_party,
            "platform": self.platform,
            "authority": self.authority,
            "required_documents": list(self.required_documents),
            "legal_basis_doc_ids": list(self.legal_basis_doc_ids),
            "warnings": list(self.warnings),
        }


@dataclass
class FilingRoute:
    route_type: str = ROUTE_OTHER
    authority_name: str = ""
    platform_name: str = ""
    platform_url_hint: str | None = None
    requires_eds: bool = False
    file_format: List[str] = field(default_factory=list)
    submission_method: List[str] = field(default_factory=list)
    required_documents: List[str] = field(default_factory=list)
    state_fee_or_costs: List[str] = field(default_factory=list)
    next_steps_after_submission: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    legal_basis_doc_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "route_type": self.route_type,
            "authority_name": self.authority_name,
            "platform_name": self.platform_name,
            "platform_url_hint": self.platform_url_hint,
            "requires_eds": self.requires_eds,
            "file_format": list(self.file_format),
            "submission_method": list(self.submission_method),
            "required_documents": list(self.required_documents),
            "state_fee_or_costs": list(self.state_fee_or_costs),
            "next_steps_after_submission": list(self.next_steps_after_submission),
            "risks": list(self.risks),
            "legal_basis_doc_ids": list(self.legal_basis_doc_ids),
        }


@dataclass
class ProcedureGuide:
    doc_type: str = ""
    title: str = ""
    filing_route: FilingRoute = field(default_factory=FilingRoute)
    steps: List[ProcedureStep] = field(default_factory=list)
    missing_procedure_facts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "title": self.title,
            "filing_route": self.filing_route.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "missing_procedure_facts": list(self.missing_procedure_facts),
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Static route map — canonical advice per doc_type.
# ---------------------------------------------------------------------------

_BASE_COURT_DOCS = [
    "доверенность или иной документ о полномочиях представителя",
    "документы, подтверждающие обстоятельства иска / заявления",
    "копии документов для ответчиков / третьих лиц",
    "документ об оплате государственной пошлины (если применимо)",
]

_BASE_NEXT_STEPS_COURT = [
    "получить отметку о принятии заявления судом",
    "контролировать движение дела через Судебный кабинет",
    "при оставлении без движения — устранить недостатки в установленный срок",
    "явиться в назначенное судебное заседание / направить представителя",
]

_BASE_RISKS_COURT = [
    "возврат заявления при ненадлежащей подсудности",
    "оставление без движения при недостатках в форме / содержании",
    "пропуск процессуальных сроков",
]


def _civil_lawsuit_debt_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name="Суд по подсудности (по общему правилу — по месту нахождения ответчика)",
        platform_name="Судебный кабинет / eGov court filing",
        platform_url_hint=None,  # production URL must be verified per case
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=["электронно через Судебный кабинет", "нарочно в канцелярию суда"],
        required_documents=[
            "исковое заявление",
            "документы, подтверждающие обстоятельства иска",
            "копии документов для ответчиков / третьих лиц",
            "доверенность или иной документ о полномочиях представителя",
            "документ об оплате государственной пошлины",
            "расчёт суммы иска (основной долг + неустойка/проценты)",
            "доказательства соблюдения досудебного порядка (если требуется)",
        ],
        state_fee_or_costs=[
            "государственная пошлина по иску (рассчитывается по цене иска "
            "— уточнить по действующему НК РК)",
            "почтовые расходы (при необходимости отправки копий)",
        ],
        next_steps_after_submission=list(_BASE_NEXT_STEPS_COURT),
        risks=list(_BASE_RISKS_COURT),
    )


def _claim_debt_pretrial_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_PRETRIAL,
        authority_name="Должник / контрагент",
        platform_name="Почта / e-mail / ЭДО / нарочно (с отметкой о вручении)",
        platform_url_hint=None,
        requires_eds=False,
        file_format=["pdf", "docx", "scan"],
        submission_method=[
            "почта (заказное с уведомлением) — основной канал",
            "ЭДО / e-mail с фиксацией получения",
            "нарочно с отметкой получателя",
            "WhatsApp / Telegram — только как дополнительный канал, "
            "не заменяющий официальный",
        ],
        required_documents=[
            "претензия",
            "копия договора и приложений",
            "акты / накладные / счета",
            "расчёт задолженности",
            "переписка сторон",
            "доказательство направления претензии",
        ],
        state_fee_or_costs=[
            "почтовые / курьерские расходы",
        ],
        next_steps_after_submission=[
            "зафиксировать дату направления и получения претензии",
            "выдержать срок ответа, указанный в претензии",
            "при отсутствии ответа — готовить иск в порядке ГПК РК",
        ],
        risks=[
            "несоблюдение обязательного досудебного порядка может привести к "
            "возврату иска",
            "отсутствие доказательств направления претензии ослабит позицию",
        ],
    )


def _bankruptcy_too_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name=(
            "Специализированный межрайонный экономический суд по месту "
            "нахождения должника"
        ),
        platform_name="Судебный кабинет / eGov court filing (если доступно)",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно в канцелярию суда",
        ],
        required_documents=[
            "заявление должника о признании банкротом / о применении "
            "процедуры реабилитации",
            "решение уполномоченного органа юридического лица / "
            "учредителей / участников",
            "документы по уплате государственной пошлины",
            "доказательства устойчивой неплатёжеспособности",
            "перечень кредиторов с суммами требований",
            "перечень дебиторов",
            "бухгалтерский баланс / финансовая отчётность",
            "документы, подтверждающие задолженность",
            "банковские справки о состоянии счетов",
            "сведения о налоговой задолженности",
            "сведения об активах должника",
            "копии заявления и приложений для уполномоченного органа "
            "(если требуется по закону)",
        ],
        state_fee_or_costs=[
            "государственная пошлина по заявлению о банкротстве",
            "расходы на администрирование процедуры (определяются "
            "законодательством о банкротстве и реабилитации)",
        ],
        next_steps_after_submission=[
            "получить отметку о принятии заявления судом",
            "контролировать определение о возбуждении / отказе в возбуждении",
            "вести коммуникацию с временным/банкротным управляющим",
            "соблюдать сроки направления документов кредиторам и в "
            "уполномоченный орган",
        ],
        risks=[
            "возврат заявления при неполном пакете документов",
            "оспаривание со стороны кредиторов",
            "признание заявления необоснованным",
        ],
    )


def _individual_bankruptcy_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_EGOV,
        authority_name=(
            "Уполномоченный орган / КГД / ЦОН по ситуации (банкротство "
            "физических лиц)"
        ),
        platform_name="eGov / eGov Mobile / e-Salyq Azamat / ЦОН",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "форма электронной подачи"],
        submission_method=[
            "через eGov / eGov Mobile",
            "через приложение e-Salyq Azamat (для отдельных процедур)",
            "лично в ЦОНе",
        ],
        required_documents=[
            "заявление по установленной форме",
            "удостоверение личности",
            "сведения о доходах и имуществе",
            "сведения о задолженности",
            "иные документы по требованию уполномоченного органа",
        ],
        state_fee_or_costs=[
            "государственные сборы / пошлины — уточнить по действующим НПА",
        ],
        next_steps_after_submission=[
            "контролировать ход рассмотрения через eGov / личный кабинет",
            "при отказе — готовить административное обжалование",
        ],
        risks=[
            "не путать с банкротством юридического лица — маршруты разные",
            "при попытке применить маршрут физлица к ТОО — отказ",
        ],
    )


def _legal_opinion_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_INTERNAL,
        authority_name="Клиент / руководство / юридический отдел",
        platform_name="Внутренний документооборот",
        platform_url_hint=None,
        requires_eds=False,
        file_format=["docx", "pdf"],
        submission_method=["передача клиенту / руководству"],
        required_documents=[
            "исходные документы клиента",
            "договоры",
            "переписка",
            "акты",
            "платёжные документы",
            "уведомления и решения госорганов (если есть)",
            "судебные акты (если есть)",
        ],
        state_fee_or_costs=[],
        next_steps_after_submission=[
            "согласовать заключение с клиентом",
            "при необходимости — подготовить документы по рекомендациям",
        ],
        risks=[
            "правовое заключение не заменяет официальную позицию суда / органа",
        ],
    )


def _contract_services_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_INTERNAL_COMPANY,
        authority_name="Стороны договора",
        platform_name="Внутренний / межкорпоративный документооборот",
        platform_url_hint=None,
        requires_eds=False,
        file_format=["docx", "pdf"],
        submission_method=[
            "подписание сторонами на бумаге",
            "ЭДО с применением ЭЦП",
        ],
        required_documents=[
            "реквизиты сторон (наименование, БИН/ИИН, адрес)",
            "предмет договора",
            "цена и порядок оплаты",
            "сроки",
            "техническое задание / приложения",
            "документы о полномочиях подписантов",
        ],
        state_fee_or_costs=[],
        next_steps_after_submission=[
            "обмен подписанными экземплярами",
            "регистрация в системе ЭДО (если применяется)",
        ],
        risks=[
            "ничтожность при отсутствии существенных условий",
            "проблемы доказывания при отсутствии письменной формы",
        ],
    )


def _admin_claim_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_ADMIN_COURT,
        authority_name=(
            "Специализированный межрайонный административный суд "
            "по подсудности"
        ),
        platform_name="Судебный кабинет / eGov court filing",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно в канцелярию суда",
        ],
        required_documents=[
            "административное исковое заявление",
            "оспариваемое решение / ответ / акт госоргана",
            "доказательства нарушения прав истца",
            "переписка / жалобы / ответы",
            "доверенность",
            "документ об оплате госпошлины (если применимо)",
            "приложения по перечню",
        ],
        state_fee_or_costs=[
            "государственная пошлина по административному иску — уточнить "
            "по действующему НК РК",
        ],
        next_steps_after_submission=list(_BASE_NEXT_STEPS_COURT),
        risks=list(_BASE_RISKS_COURT)
        + [
            "пропуск процессуальных сроков обжалования по АППК",
        ],
    )


def _complaint_to_state_body_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_ADMIN_BODY_OR_COURT,
        authority_name="Государственный орган / административный суд по ситуации",
        platform_name="e-Otinish / eGov / Судебный кабинет / канцелярия органа",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx", "форма электронной подачи"],
        submission_method=[
            "через e-Otinish",
            "через eGov / личный кабинет органа",
            "нарочно в канцелярию",
            "электронно через Судебный кабинет (если идёт сразу в админ. суд)",
        ],
        required_documents=[
            "жалоба / заявление",
            "оспариваемое решение / действие / бездействие",
            "доказательства нарушения прав",
            "доверенность",
            "переписка с органом",
            "доказательства соблюдения срока подачи",
        ],
        state_fee_or_costs=[],
        next_steps_after_submission=[
            "контролировать срок ответа органа (по АППК)",
            "при отказе / молчании — готовить иск в административный суд",
        ],
        risks=[
            "пропуск срока обжалования",
            "отказ в принятии жалобы по формальным основаниям",
        ],
    )


def _appeal_complaint_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name="Суд апелляционной инстанции (через суд первой инстанции)",
        platform_name="Судебный кабинет",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно в канцелярию суда первой инстанции",
        ],
        required_documents=[
            "апелляционная жалоба",
            "копия обжалуемого судебного акта",
            "доверенность",
            "документ об оплате госпошлины (если применимо)",
            "копии для участников дела",
        ],
        state_fee_or_costs=[
            "госпошлина по апелляции — уточнить по действующему НК РК",
        ],
        next_steps_after_submission=list(_BASE_NEXT_STEPS_COURT)
        + [
            "контролировать назначение апелляционного заседания",
        ],
        risks=list(_BASE_RISKS_COURT)
        + [
            "пропуск процессуального срока на апелляцию",
            "оставление жалобы без движения при недостатках",
        ],
    )


def _cassation_complaint_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name="Верховный Суд РК (кассационная инстанция)",
        platform_name="Судебный кабинет",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно через суд первой инстанции",
        ],
        required_documents=[
            "кассационная жалоба",
            "копии судебных актов первой и апелляционной инстанций",
            "доверенность",
            "документ об оплате госпошлины (если применимо)",
            "копии для участников дела",
            "обоснование существенных нарушений норм материального и "
            "процессуального права",
        ],
        state_fee_or_costs=[
            "госпошлина по кассации — уточнить по действующему НК РК",
        ],
        next_steps_after_submission=[
            "контролировать решение о допуске / отказе в допуске",
            "при допуске — готовить позицию к рассмотрению",
        ],
        risks=[
            "отказ в допуске при отсутствии существенных нарушений",
            "пропуск процессуального срока на кассацию",
        ],
    )


def _private_complaint_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name="Суд апелляционной инстанции (через суд, вынесший определение)",
        platform_name="Судебный кабинет",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно через суд, вынесший определение",
        ],
        required_documents=[
            "частная жалоба",
            "копия обжалуемого определения суда",
            "доверенность",
            "копии для участников дела",
        ],
        state_fee_or_costs=[
            "госпошлина по частной жалобе — уточнить по действующему НК РК",
        ],
        next_steps_after_submission=list(_BASE_NEXT_STEPS_COURT),
        risks=list(_BASE_RISKS_COURT)
        + [
            "пропуск процессуального срока на частную жалобу",
        ],
    )


def _motion_general_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name="Суд / орган, рассматривающий дело",
        platform_name="Судебный кабинет / нарочно",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно в канцелярию",
        ],
        required_documents=[
            "ходатайство",
            "приложения, обосновывающие ходатайство",
            "доверенность (если подаётся представителем)",
        ],
        state_fee_or_costs=[],
        next_steps_after_submission=[
            "контролировать рассмотрение ходатайства",
            "получить определение / резолюцию",
        ],
        risks=[
            "отказ при отсутствии правового обоснования",
        ],
    )


def _interim_measures_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name="Суд, рассматривающий дело",
        platform_name="Судебный кабинет",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно в канцелярию суда",
        ],
        required_documents=[
            "заявление о принятии обеспечительных мер",
            "доказательства затруднения / невозможности исполнения "
            "решения без мер",
            "копия искового заявления",
            "доверенность",
        ],
        state_fee_or_costs=[
            "встречное обеспечение (по требованию суда)",
        ],
        next_steps_after_submission=[
            "при удовлетворении — получить определение и направить на "
            "исполнение",
            "при отказе — рассмотреть частную жалобу",
        ],
        risks=[
            "отказ при недоказанности риска неисполнения",
            "ответственность за необоснованные меры",
        ],
    )


def _restore_deadline_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name="Суд / орган, перед которым пропущен срок",
        platform_name="Судебный кабинет / канцелярия",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно в канцелярию",
        ],
        required_documents=[
            "заявление о восстановлении пропущенного процессуального срока",
            "документы, подтверждающие уважительность причин пропуска "
            "(больничные листы, командировочные, доказательства "
            "независящих обстоятельств)",
            "сам процессуальный документ, который подаётся с пропуском срока",
        ],
        state_fee_or_costs=[],
        next_steps_after_submission=[
            "получить определение о восстановлении / отказе",
            "при отказе — рассмотреть частную жалобу",
        ],
        risks=[
            "отказ при недостаточности доказательств уважительности",
        ],
    )


def _enforcement_writ_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name="Суд первой инстанции (вынесший решение)",
        platform_name="Судебный кабинет / нарочно",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно в канцелярию суда",
        ],
        required_documents=[
            "заявление о выдаче исполнительного листа",
            "копия судебного акта со сведениями о вступлении в силу",
            "доверенность",
        ],
        state_fee_or_costs=[],
        next_steps_after_submission=[
            "получить исполнительный лист",
            "передать судебному исполнителю / в частный СИ",
        ],
        risks=[
            "ошибки в реквизитах должника / суммы — затруднят исполнение",
        ],
    )


def _bailiff_complaint_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT_OR_ENFORCEMENT_AUTHORITY,
        authority_name=(
            "Орган исполнительного производства / суд по подсудности "
            "(в зависимости от категории жалобы)"
        ),
        platform_name="Судебный кабинет / канцелярия органа",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно в канцелярию",
        ],
        required_documents=[
            "жалоба на действие / бездействие судебного исполнителя",
            "копии материалов исполнительного производства",
            "доказательства нарушения прав",
            "доверенность",
        ],
        state_fee_or_costs=[],
        next_steps_after_submission=[
            "получить решение по жалобе",
            "при отказе — рассмотреть обжалование в суд",
        ],
        risks=[
            "пропуск срока на обжалование",
        ],
    )


def _objection_to_claim_route() -> FilingRoute:
    return FilingRoute(
        route_type=ROUTE_COURT,
        authority_name="Суд, рассматривающий дело",
        platform_name="Судебный кабинет / канцелярия",
        platform_url_hint=None,
        requires_eds=True,
        file_format=["pdf", "docx"],
        submission_method=[
            "электронно через Судебный кабинет",
            "нарочно в канцелярию суда",
        ],
        required_documents=[
            "возражение на иск",
            "доказательства, подтверждающие позицию ответчика",
            "доверенность",
        ],
        state_fee_or_costs=[],
        next_steps_after_submission=[
            "получить отметку о приобщении возражения",
            "явиться на заседание / направить представителя",
        ],
        risks=[
            "несвоевременная подача может повлечь отказ в приобщении",
        ],
    )


def _response_to_claim_route() -> FilingRoute:
    r = _objection_to_claim_route()
    r.required_documents = [
        "отзыв на иск",
        "доказательства, подтверждающие позицию",
        "доверенность",
    ]
    return r


_DOC_TYPE_TO_ROUTE_BUILDER = {
    "civil_lawsuit_debt": _civil_lawsuit_debt_route,
    "civil_lawsuit": _civil_lawsuit_debt_route,
    "claim_debt_pretrial": _claim_debt_pretrial_route,
    "claim": _claim_debt_pretrial_route,
    "bankruptcy_statement_too": _bankruptcy_too_route,
    "bankruptcy_statement": _bankruptcy_too_route,
    "individual_bankruptcy": _individual_bankruptcy_route,
    "legal_opinion": _legal_opinion_route,
    "contract_services": _contract_services_route,
    "contract": _contract_services_route,
    "admin_claim": _admin_claim_route,
    "admin_petition": _admin_claim_route,
    "complaint_to_state_body": _complaint_to_state_body_route,
    "complaint": _complaint_to_state_body_route,
    "appeal_complaint": _appeal_complaint_route,
    "cassation_complaint": _cassation_complaint_route,
    "private_complaint": _private_complaint_route,
    "motion_general": _motion_general_route,
    "interim_measures_application": _interim_measures_route,
    "restore_deadline_application": _restore_deadline_route,
    "enforcement_writ_application": _enforcement_writ_route,
    "bailiff_complaint": _bailiff_complaint_route,
    "objection_to_claim": _objection_to_claim_route,
    "response_to_claim": _response_to_claim_route,
}


def detect_filing_route(
    doc_type: str,
    query: str = "",
    used_docs: Sequence[Any] | None = None,
) -> FilingRoute:
    """Pick the canonical :class:`FilingRoute` for a given ``doc_type``.

    ``query`` may be used to disambiguate (e.g. routing "банкротство" to
    individual_bankruptcy when the user explicitly mentions a physical
    person). ``used_docs`` is reserved for future per-norm refinements.
    """
    dt = (doc_type or "").strip().lower()
    low = (query or "").lower()

    # Disambiguation: bankruptcy default → ТОО; if explicitly individual,
    # switch.
    if dt in ("bankruptcy_statement_too", "bankruptcy_statement", "bankruptcy"):
        # Stem-pair matching survives Russian inflections like
        # "физическое лицо" / "физического лица" / "физическим лицом".
        is_individual = (
            ("физическ" in low and "лиц" in low)
            or "физлиц" in low
            or "гражданин" in low
        )
        if is_individual and "тоо" not in low:
            return _individual_bankruptcy_route()

    builder = _DOC_TYPE_TO_ROUTE_BUILDER.get(dt)
    if builder is None:
        return FilingRoute(
            route_type=ROUTE_OTHER,
            authority_name="Не определено по типу документа",
            platform_name="—",
            requires_eds=False,
            risks=[
                "тип документа не распознан — маршрут подачи требует ручной "
                "проверки",
            ],
        )
    return builder()


def get_required_documents_for_doc_type(doc_type: str, query: str = "") -> List[str]:
    """Convenience accessor — returns just the required-documents list."""
    return list(detect_filing_route(doc_type, query).required_documents)


# ---------------------------------------------------------------------------
# Steps + missing facts
# ---------------------------------------------------------------------------

_DEFAULT_STEPS_BY_ROUTE_TYPE: dict[str, List[ProcedureStep]] = {
    ROUTE_COURT: [
        ProcedureStep(
            step_number=1,
            title="Подготовка пакета документов",
            description=(
                "Собрать исковое заявление / жалобу / заявление, расчёт, "
                "приложения, копии для участников. Проверить полноту."
            ),
        ),
        ProcedureStep(
            step_number=2,
            title="Уплата государственной пошлины",
            description="Рассчитать и уплатить госпошлину. Сохранить квитанцию.",
        ),
        ProcedureStep(
            step_number=3,
            title="Подача через Судебный кабинет / канцелярию",
            description=(
                "Подписать ЭЦП и направить через Судебный кабинет либо "
                "сдать нарочно в канцелярию суда."
            ),
            platform="Судебный кабинет",
        ),
        ProcedureStep(
            step_number=4,
            title="Контроль движения дела",
            description=(
                "Отслеживать статус через Судебный кабинет, реагировать на "
                "оставление без движения."
            ),
        ),
    ],
    ROUTE_ADMIN_COURT: [
        ProcedureStep(
            step_number=1,
            title="Подготовка административного иска",
            description=(
                "Собрать административное исковое заявление, оспариваемый "
                "акт, доказательства, переписку."
            ),
        ),
        ProcedureStep(
            step_number=2,
            title="Подача через Судебный кабинет",
            description=(
                "Подписать ЭЦП и направить через Судебный кабинет в "
                "административный суд."
            ),
            platform="Судебный кабинет",
        ),
        ProcedureStep(
            step_number=3,
            title="Контроль рассмотрения",
            description=(
                "Контролировать движение дела, реагировать на запросы суда, "
                "представлять доказательства."
            ),
        ),
    ],
    ROUTE_PRETRIAL: [
        ProcedureStep(
            step_number=1,
            title="Составление и подписание претензии",
            description=(
                "Сформировать претензию с указанием обстоятельств, расчёта "
                "и срока ответа."
            ),
        ),
        ProcedureStep(
            step_number=2,
            title="Направление претензии",
            description=(
                "Направить почтой с уведомлением, ЭДО или нарочно с "
                "подтверждением получения."
            ),
        ),
        ProcedureStep(
            step_number=3,
            title="Ожидание срока ответа",
            description="Выдержать установленный срок ответа.",
        ),
        ProcedureStep(
            step_number=4,
            title="Дальнейшие действия",
            description=(
                "При отсутствии ответа / отказе — готовить иск в порядке "
                "ГПК РК."
            ),
        ),
    ],
    ROUTE_EGOV: [
        ProcedureStep(
            step_number=1,
            title="Подготовка заявления / формы",
            description="Заполнить требуемую форму и собрать сопровождающие документы.",
        ),
        ProcedureStep(
            step_number=2,
            title="Подача через eGov / eGov Mobile / e-Salyq Azamat / ЦОН",
            description="Подписать ЭЦП и направить через выбранный канал.",
            platform="eGov",
        ),
        ProcedureStep(
            step_number=3,
            title="Контроль рассмотрения",
            description="Отслеживать ход через личный кабинет.",
        ),
    ],
    ROUTE_INTERNAL: [
        ProcedureStep(
            step_number=1,
            title="Сбор материалов клиента",
            description="Получить документы и факты, систематизировать.",
        ),
        ProcedureStep(
            step_number=2,
            title="Подготовка правового заключения",
            description=(
                "Сформулировать вопросы, провести анализ норм, изложить "
                "выводы и рекомендации."
            ),
        ),
        ProcedureStep(
            step_number=3,
            title="Передача клиенту",
            description="Передать заключение клиенту, обсудить дальнейшие шаги.",
        ),
    ],
    ROUTE_INTERNAL_COMPANY: [
        ProcedureStep(
            step_number=1,
            title="Подготовка проекта договора",
            description="Согласовать предмет, цену, сроки, условия.",
        ),
        ProcedureStep(
            step_number=2,
            title="Согласование сторонами",
            description=(
                "Обмен правками, фиксация согласованной редакции, "
                "приложений."
            ),
        ),
        ProcedureStep(
            step_number=3,
            title="Подписание",
            description=(
                "Подписание сторонами на бумаге или в ЭДО с применением ЭЦП."
            ),
        ),
    ],
    ROUTE_ADMIN_BODY_OR_COURT: [
        ProcedureStep(
            step_number=1,
            title="Определение подведомственности",
            description=(
                "Решить, подавать жалобу в орган в досудебном порядке (по "
                "АППК) или сразу в административный суд."
            ),
        ),
        ProcedureStep(
            step_number=2,
            title="Подача жалобы",
            description=(
                "Подать через e-Otinish / eGov / Судебный кабинет / "
                "канцелярию органа."
            ),
            platform="e-Otinish / eGov / Судебный кабинет",
        ),
        ProcedureStep(
            step_number=3,
            title="Контроль срока ответа",
            description="Соблюдать срок и контролировать получение ответа.",
        ),
        ProcedureStep(
            step_number=4,
            title="Эскалация",
            description=(
                "При отказе / молчании — готовить административный иск."
            ),
        ),
    ],
    ROUTE_COURT_OR_ENFORCEMENT_AUTHORITY: [
        ProcedureStep(
            step_number=1,
            title="Определение порядка обжалования",
            description=(
                "Уточнить, в какой орган подать жалобу: исполнительное "
                "производство / суд."
            ),
        ),
        ProcedureStep(
            step_number=2,
            title="Подача жалобы",
            description="Подать в выбранный орган с приложениями.",
        ),
        ProcedureStep(
            step_number=3,
            title="Контроль рассмотрения",
            description="Получить решение по жалобе и при необходимости обжаловать дальше.",
        ),
    ],
}


def _missing_facts_for_route(
    doc_type: str,
    route: FilingRoute,
    document_request: Any | None = None,
) -> List[str]:
    """Generate a list of *procedure-specific* missing facts."""
    miss: List[str] = []
    dt = (doc_type or "").strip().lower()

    if route.route_type in (ROUTE_COURT, ROUTE_ADMIN_COURT):
        miss.append("полное наименование суда (по подсудности)")
        if document_request is not None and not getattr(document_request, "court_info", {}).get("court"):
            miss.append("уточнить адрес и территориальную подсудность")

    if dt in {"appeal_complaint", "cassation_complaint", "private_complaint"}:
        miss.append("номер дела")
        miss.append("дата вынесения обжалуемого судебного акта")
        miss.append("реквизиты обжалуемого судебного акта (инстанция, судья)")
        miss.append("соблюдение процессуального срока на обжалование")

    if dt == "interim_measures_application":
        miss.append("вид испрашиваемой обеспечительной меры")
        miss.append("доказательства риска неисполнения судебного акта")

    if dt == "restore_deadline_application":
        miss.append("какой именно процессуальный срок пропущен")
        miss.append("причины пропуска и доказательства уважительности")

    if dt == "enforcement_writ_application":
        miss.append("дата вступления судебного акта в законную силу")

    if dt == "admin_claim":
        miss.append("наименование госоргана-ответчика")
        miss.append("дата и реквизиты оспариваемого решения / действия / бездействия")
        miss.append("сведения о соблюдении досудебного порядка по АППК")

    if dt == "bailiff_complaint":
        miss.append("номер исполнительного производства")
        miss.append("конкретные действия / бездействие судебного исполнителя")

    if dt == "bankruptcy_statement_too":
        miss.append("БИН и юридический адрес должника")
        miss.append("полный реестр кредиторов с суммами")
        miss.append("сведения о банковской задолженности и счетах")

    if dt == "individual_bankruptcy":
        miss.append("ИИН должника-физического лица")
        miss.append("сведения о доходах и имуществе должника")

    if dt in ("claim_debt_pretrial", "civil_lawsuit_debt"):
        miss.append("реквизиты должника / контрагента")
        miss.append("период образования задолженности")

    return miss


# ---------------------------------------------------------------------------
# build_procedure_guide
# ---------------------------------------------------------------------------

def build_procedure_guide(
    doc_type: str,
    query: str,
    understanding: Any | None = None,
    used_docs: Sequence[Any] | None = None,
    document_request: Any | None = None,
) -> ProcedureGuide:
    """Construct a :class:`ProcedureGuide` for a given ``doc_type``.

    ``understanding`` and ``used_docs`` are accepted for forward compatibility
    (later we'll wire RAG-anchored doc_ids into ``legal_basis_doc_ids``).
    """
    route = detect_filing_route(doc_type, query=query, used_docs=used_docs)
    steps = list(_DEFAULT_STEPS_BY_ROUTE_TYPE.get(route.route_type, []))
    missing = _missing_facts_for_route(doc_type, route, document_request=document_request)

    title_map = {
        "civil_lawsuit_debt": "Подача иска через Судебный кабинет / eGov",
        "claim_debt_pretrial": "Досудебное направление претензии",
        "bankruptcy_statement_too": "Документы для процедуры банкротства (ТОО)",
        "individual_bankruptcy": "Документы для банкротства физического лица",
        "legal_opinion": "Внутренний оборот правового заключения",
        "contract_services": "Согласование и подписание договора",
        "admin_claim": "Подача административного иска",
        "complaint_to_state_body": "Жалоба в госорган / административный суд",
        "appeal_complaint": "Подача апелляционной жалобы",
        "cassation_complaint": "Подача кассационной жалобы",
        "private_complaint": "Подача частной жалобы",
        "motion_general": "Подача ходатайства",
        "interim_measures_application": "Заявление об обеспечительных мерах",
        "restore_deadline_application": "Восстановление пропущенного процессуального срока",
        "enforcement_writ_application": "Получение исполнительного листа",
        "bailiff_complaint": "Жалоба на действия судебного исполнителя",
        "objection_to_claim": "Подача возражений на иск",
        "response_to_claim": "Подача отзыва на иск",
    }

    title = title_map.get((doc_type or "").lower(), "Практический маршрут подачи документа")

    warnings: list[str] = []
    if route.route_type == ROUTE_OTHER:
        warnings.append(
            "Тип документа не распознан — маршрут подачи требует ручной "
            "проверки."
        )

    return ProcedureGuide(
        doc_type=doc_type or "",
        title=title,
        filing_route=route,
        steps=steps,
        missing_procedure_facts=missing,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_procedure_section(guide: ProcedureGuide) -> str:
    """Render a procedure guide as a plain text block (no markdown)."""
    if guide is None:
        return ""
    parts: List[str] = []
    title = (guide.title or "Практический маршрут").strip()
    parts.append(title)
    parts.append("-" * max(8, len(title)))

    r = guide.filing_route
    parts.append(f"Маршрут: {r.route_type}")
    if r.authority_name:
        parts.append(f"Орган / адресат: {r.authority_name}")
    if r.platform_name:
        parts.append(f"Платформа: {r.platform_name}")
    if r.platform_url_hint:
        parts.append(f"URL-подсказка: {r.platform_url_hint}")
    parts.append(f"Требуется ЭЦП: {'да' if r.requires_eds else 'нет'}")
    if r.file_format:
        parts.append(f"Формат файла: {', '.join(r.file_format)}")
    if r.submission_method:
        parts.append("Способы подачи:")
        for s in r.submission_method:
            parts.append(f"  • {s}")
    if r.required_documents:
        parts.append("Документы / приложения:")
        for d in r.required_documents:
            parts.append(f"  • {d}")
    if r.state_fee_or_costs:
        parts.append("Госпошлина / расходы:")
        for c in r.state_fee_or_costs:
            parts.append(f"  • {c}")
    if r.next_steps_after_submission:
        parts.append("После подачи:")
        for s in r.next_steps_after_submission:
            parts.append(f"  • {s}")
    if r.risks:
        parts.append("Риски:")
        for risk in r.risks:
            parts.append(f"  • {risk}")

    if guide.steps:
        parts.append("")
        parts.append("Шаги:")
        for s in guide.steps:
            head = f"  {s.step_number}. {s.title}"
            parts.append(head)
            if s.description:
                parts.append(f"     {s.description}")
            if s.platform:
                parts.append(f"     Платформа: {s.platform}")
            if s.required_documents:
                for rd in s.required_documents:
                    parts.append(f"     • {rd}")

    if guide.missing_procedure_facts:
        parts.append("")
        parts.append("Уточнить перед подачей:")
        for f in guide.missing_procedure_facts:
            parts.append(f"  • {f}")

    if guide.warnings:
        parts.append("")
        parts.append("Предупреждения:")
        for w in guide.warnings:
            parts.append(f"  • {w}")

    return "\n".join(parts).rstrip()


# Alias used by answer engine.
render_procedure_block = render_procedure_section


__all__ = [
    "FilingRoute",
    "ProcedureGuide",
    "ProcedureStep",
    "ROUTE_ADMIN_BODY_OR_COURT",
    "ROUTE_ADMIN_COURT",
    "ROUTE_COURT",
    "ROUTE_COURT_OR_ENFORCEMENT_AUTHORITY",
    "ROUTE_EGOV",
    "ROUTE_ENFORCEMENT",
    "ROUTE_INTERNAL",
    "ROUTE_INTERNAL_COMPANY",
    "ROUTE_JUDICIAL_CABINET",
    "ROUTE_KGD",
    "ROUTE_NOTARY",
    "ROUTE_OTHER",
    "ROUTE_PRETRIAL",
    "ROUTE_TAX_AUTHORITY",
    "ROUTE_TYPES",
    "build_procedure_guide",
    "detect_filing_route",
    "get_required_documents_for_doc_type",
    "render_procedure_block",
    "render_procedure_section",
]
