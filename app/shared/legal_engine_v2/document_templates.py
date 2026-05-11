"""Document Factory v2 — templates.

Each template is a list of :class:`SectionTemplate` describing the section's
key, title, purpose, and the slot keys it expects from a
:class:`DocumentRequest`. The writer reads these templates and renders one
:class:`DocumentSection` per item.

Templates are pure metadata — no I/O, no LLM. The writer fills in actual
draft text either deterministically or via per-section LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class SectionTemplate:
    key: str
    title: str
    purpose: str
    required_slots: tuple[str, ...] = ()
    bucket_priority: tuple[str, ...] = ("codes", "laws", "vs_np", "procedure", "risk", "other")


@dataclass(frozen=True)
class DocumentTemplate:
    doc_type: str
    title: str
    sections: tuple[SectionTemplate, ...]
    # Optional: source_id substrings preferred for legal_basis selection.
    preferred_source_id_tokens: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Concrete templates
# ---------------------------------------------------------------------------

# 1. ПРЕТЕНЗИЯ о взыскании долга по договору (досудебная)
CLAIM_DEBT_PRETRIAL = DocumentTemplate(
    doc_type="claim_debt_pretrial",
    title="ПРЕТЕНЗИЯ о взыскании задолженности по договору",
    sections=(
        SectionTemplate(
            key="header",
            title="Шапка",
            purpose=(
                "Адресат претензии (должник, наименование/ФИО, адрес) и "
                "отправитель (взыскатель)."
            ),
            required_slots=("parties.defendant", "parties.plaintiff"),
        ),
        SectionTemplate(
            key="parties",
            title="Данные сторон",
            purpose="Полные реквизиты сторон: наименование/ФИО, ИИН/БИН, адрес, контакты.",
            required_slots=("parties.plaintiff", "parties.defendant"),
        ),
        SectionTemplate(
            key="circumstances",
            title="Обстоятельства",
            purpose="Связное изложение фактов и хронологии возникновения долга.",
            required_slots=("facts",),
        ),
        SectionTemplate(
            key="debt_basis",
            title="Основание долга",
            purpose="Договор: вид, номер, дата, существенные условия (предмет, цена, сроки).",
            required_slots=("contract_info",),
        ),
        SectionTemplate(
            key="breach",
            title="Нарушение обязательства",
            purpose="Что именно нарушено: неоплата, просрочка, ненадлежащее исполнение.",
            required_slots=("facts", "amounts.principal_debt"),
        ),
        SectionTemplate(
            key="calculation",
            title="Расчёт задолженности",
            purpose="Сумма долга, неустойка/пени, проценты по ст. 353 ГК. Период.",
            required_slots=("amounts.principal_debt",),
        ),
        SectionTemplate(
            key="legal_basis",
            title="Правовое обоснование",
            purpose="Ссылки на нормы из RAG: ГК (обязательства, ответственность), профильные законы.",
            bucket_priority=("codes", "laws", "vs_np"),
        ),
        SectionTemplate(
            key="demand",
            title="Требование",
            purpose="Чёткая формулировка требования: оплатить сумму, погасить долг, исполнить обязательство.",
            required_slots=("claims",),
        ),
        SectionTemplate(
            key="deadline",
            title="Срок исполнения",
            purpose="Срок добровольного исполнения требования и форма ответа.",
        ),
        SectionTemplate(
            key="court_warning",
            title="Предупреждение о суде",
            purpose=(
                "В случае неисполнения — обращение в суд с иском, отнесение всех "
                "судебных и иных расходов на должника (ст. ГК / ГПК)."
            ),
            bucket_priority=("codes", "procedure"),
        ),
        SectionTemplate(
            key="attachments",
            title="Приложения",
            purpose="Список приложенных документов (копии договора, расчёт, переписка).",
            required_slots=("evidence",),
        ),
        SectionTemplate(
            key="signature",
            title="Дата и подпись",
            purpose="Дата составления, ФИО подписанта, подпись/печать.",
        ),
    ),
    preferred_source_id_tokens=("kz_civil_code", "kz_gpk_code", "kz_law_obligations"),
)


# 2. ИСКОВОЕ ЗАЯВЛЕНИЕ о взыскании долга по договору
CIVIL_LAWSUIT_DEBT = DocumentTemplate(
    doc_type="civil_lawsuit_debt",
    title="ИСКОВОЕ ЗАЯВЛЕНИЕ о взыскании задолженности по договору",
    sections=(
        SectionTemplate(
            key="court_header",
            title="Шапка суда",
            purpose="Наименование суда, в который подаётся исковое заявление.",
            required_slots=("court_info.court",),
        ),
        SectionTemplate(
            key="plaintiff",
            title="Истец",
            purpose="Реквизиты истца: ФИО/наименование, ИИН/БИН, адрес, телефон.",
            required_slots=("parties.plaintiff",),
        ),
        SectionTemplate(
            key="defendant",
            title="Ответчик",
            purpose="Реквизиты ответчика.",
            required_slots=("parties.defendant",),
        ),
        SectionTemplate(
            key="case_value",
            title="Цена иска",
            purpose="Сумма требований и расчёт государственной пошлины.",
            required_slots=("amounts.principal_debt",),
        ),
        SectionTemplate(
            key="title",
            title="Название документа",
            purpose="«ИСКОВОЕ ЗАЯВЛЕНИЕ о взыскании задолженности по договору».",
        ),
        SectionTemplate(
            key="circumstances",
            title="Обстоятельства дела",
            purpose="Связное изложение фактов: возникновение обязательства, ход исполнения.",
            required_slots=("facts",),
        ),
        SectionTemplate(
            key="contract_relations",
            title="Договорные отношения",
            purpose="Договор: вид, номер, дата, существенные условия (предмет, цена, сроки).",
            required_slots=("contract_info",),
        ),
        SectionTemplate(
            key="breach",
            title="Нарушение обязательства",
            purpose="Конкретные нарушения и последствия.",
            required_slots=("facts",),
        ),
        SectionTemplate(
            key="pretrial",
            title="Досудебный порядок",
            purpose="Сведения о направленной претензии и ответе (если требуется по закону / договору).",
        ),
        SectionTemplate(
            key="legal_basis",
            title="Правовое обоснование",
            purpose=(
                "Нормы ГК (обязательства, ответственность за нарушение, "
                "ст. 353 проценты), специальные законы. Подсудность по ГПК."
            ),
            bucket_priority=("codes", "laws", "vs_np", "procedure"),
        ),
        SectionTemplate(
            key="calculation",
            title="Расчёт требований",
            purpose="Сумма основного долга, неустойка/пеня, проценты. Период.",
            required_slots=("amounts.principal_debt",),
        ),
        SectionTemplate(
            key="petitum",
            title="Просительная часть",
            purpose="«ПРОШУ» — конкретные требования к суду.",
            required_slots=("claims",),
        ),
        SectionTemplate(
            key="attachments",
            title="Приложения",
            purpose="Перечень документов: договор, расчёт, претензия, госпошлина, доверенность.",
            required_slots=("evidence",),
        ),
        SectionTemplate(
            key="signature",
            title="Дата и подпись",
            purpose="Дата подачи, подпись истца / представителя.",
        ),
    ),
    preferred_source_id_tokens=(
        "kz_civil_code",
        "kz_gpk_code",
        "kz_law_obligations",
        "kz_vs_np",
    ),
)


# 3. ПРАВОВОЕ ЗАКЛЮЧЕНИЕ
LEGAL_OPINION = DocumentTemplate(
    doc_type="legal_opinion",
    title="ПРАВОВОЕ ЗАКЛЮЧЕНИЕ",
    sections=(
        SectionTemplate(
            key="summary",
            title="Вводный вывод",
            purpose="Короткий вывод по делу (3–6 предложений).",
            required_slots=("facts",),
        ),
        SectionTemplate(
            key="facts",
            title="Факты",
            purpose="Изложение значимых фактов и хронологии.",
            required_slots=("facts",),
        ),
        SectionTemplate(
            key="questions",
            title="Вопросы",
            purpose="Юридические вопросы, на которые отвечает заключение.",
        ),
        SectionTemplate(
            key="norms",
            title="Применимые нормы",
            purpose="Релевантные нормы из RAG.",
            bucket_priority=("codes", "laws"),
        ),
        SectionTemplate(
            key="practice",
            title="Судебная практика",
            purpose="Релевантные позиции НП ВС из RAG (если есть).",
            bucket_priority=("vs_np",),
        ),
        SectionTemplate(
            key="analysis",
            title="Анализ",
            purpose="Применение норм к фактам, квалификация ситуации.",
            required_slots=("facts",),
        ),
        SectionTemplate(
            key="risks",
            title="Риски",
            purpose="Гражданские, административные, уголовные, процессуальные риски.",
            bucket_priority=("risk", "codes", "laws"),
        ),
        SectionTemplate(
            key="recommendations",
            title="Рекомендации",
            purpose="План действий, требуемые документы, сроки.",
        ),
    ),
)


# 4. ДОГОВОР ОКАЗАНИЯ УСЛУГ
CONTRACT_SERVICES = DocumentTemplate(
    doc_type="contract_services",
    title="ДОГОВОР ОКАЗАНИЯ УСЛУГ",
    sections=(
        SectionTemplate(
            key="parties",
            title="Стороны",
            purpose="Заказчик и Исполнитель: наименование/ФИО, ИИН/БИН, адрес, представители.",
            required_slots=("parties",),
        ),
        SectionTemplate(
            key="subject",
            title="Предмет договора",
            purpose="Перечень услуг, объём, требования к качеству.",
        ),
        SectionTemplate(
            key="rights_obligations",
            title="Права и обязанности",
            purpose="Обязанности Исполнителя и Заказчика, права сторон.",
        ),
        SectionTemplate(
            key="terms",
            title="Сроки",
            purpose="Срок действия договора, сроки оказания услуг и сдачи-приёмки.",
        ),
        SectionTemplate(
            key="price_and_payment",
            title="Цена и порядок оплаты",
            purpose="Стоимость, валюта, порядок и сроки расчётов, НДС.",
            required_slots=("amounts",),
        ),
        SectionTemplate(
            key="liability",
            title="Ответственность",
            purpose="Ответственность за нарушение обязательств: пеня/штраф/убытки.",
            bucket_priority=("codes", "laws"),
        ),
        SectionTemplate(
            key="termination",
            title="Расторжение",
            purpose="Основания и порядок одностороннего и судебного расторжения.",
        ),
        SectionTemplate(
            key="confidentiality",
            title="Конфиденциальность",
            purpose="Режим коммерческой тайны и персональных данных.",
        ),
        SectionTemplate(
            key="disputes",
            title="Разрешение споров",
            purpose="Претензионный порядок и подсудность.",
            bucket_priority=("procedure", "codes"),
        ),
        SectionTemplate(
            key="requisites",
            title="Реквизиты и подписи сторон",
            purpose="Банковские реквизиты, БИН/ИИН, подписи и печати.",
            required_slots=("parties",),
        ),
    ),
    preferred_source_id_tokens=("kz_civil_code",),
)


# 5. ЗАЯВЛЕНИЕ О БАНКРОТСТВЕ ТОО
BANKRUPTCY_STATEMENT_TOO = DocumentTemplate(
    doc_type="bankruptcy_statement_too",
    title="ЗАЯВЛЕНИЕ о применении процедуры банкротства / реабилитации (ТОО)",
    sections=(
        SectionTemplate(
            key="court_header",
            title="Суд",
            purpose="Наименование суда, в который подаётся заявление (по подсудности).",
            required_slots=("court_info.court",),
        ),
        SectionTemplate(
            key="applicant",
            title="Заявитель",
            purpose="Реквизиты заявителя (должник или кредитор).",
            required_slots=("parties.applicant",),
        ),
        SectionTemplate(
            key="debtor",
            title="Должник",
            purpose="ТОО: полное наименование, БИН, юр. адрес, учредители.",
            required_slots=("parties.debtor",),
        ),
        SectionTemplate(
            key="creditors",
            title="Кредиторы",
            purpose="Перечень кредиторов и сумм требований.",
        ),
        SectionTemplate(
            key="insolvency",
            title="Обстоятельства неплатежеспособности",
            purpose="Причины и период наступления неплатежеспособности.",
            required_slots=("facts",),
        ),
        SectionTemplate(
            key="debt_summary",
            title="Задолженность",
            purpose="Размер совокупной задолженности, структура (банки, контрагенты, налоги).",
        ),
        SectionTemplate(
            key="assets",
            title="Активы",
            purpose="Имущество должника, оценочная стоимость, обременения.",
        ),
        SectionTemplate(
            key="bank_obligations",
            title="Банковские обязательства",
            purpose="Кредиты, ипотеки, гарантии — перечень и сальдо.",
        ),
        SectionTemplate(
            key="tax_debt",
            title="Налоговая задолженность",
            purpose="Сведения о налоговой задолженности и налоговых спорах.",
        ),
        SectionTemplate(
            key="legal_basis",
            title="Правовое обоснование",
            purpose="Нормы Закона О реабилитации и банкротстве (из RAG).",
            bucket_priority=("laws", "codes", "vs_np"),
        ),
        SectionTemplate(
            key="petitum",
            title="Просительная часть",
            purpose="«ПРОШУ» — какую процедуру применить и в каком объёме.",
            required_slots=("claims",),
        ),
        SectionTemplate(
            key="attachments",
            title="Приложения",
            purpose="Учредительные документы, баланс, реестр кредиторов, налоговая справка.",
        ),
    ),
    preferred_source_id_tokens=("kz_law_bankruptcy", "kz_law_rehabilitation"),
)


# ---------------------------------------------------------------------------
# Procedural court documents — skeletons follow strict ГПК / АППК / УПК
# structure.  Each template maps to a doc_type used by intake and writer.
# ---------------------------------------------------------------------------

def _proc(key: str, title: str, purpose: str, *, slots: tuple[str, ...] = ()) -> SectionTemplate:
    return SectionTemplate(key=key, title=title, purpose=purpose, required_slots=slots)


APPEAL_COMPLAINT = DocumentTemplate(
    doc_type="appeal_complaint",
    title="АПЕЛЛЯЦИОННАЯ ЖАЛОБА",
    sections=(
        _proc("court_header", "Суд апелляционной инстанции",
              "Наименование суда апелляционной инстанции (через суд первой инстанции).",
              slots=("court_info.court",)),
        _proc("applicant", "Заявитель", "Реквизиты заявителя жалобы.",
              slots=("parties.applicant",)),
        _proc("other_parties", "Другие участники дела",
              "Истец / ответчик / третьи лица / прокурор по делу."),
        _proc("act_data", "Данные обжалуемого судебного акта",
              "Наименование суда, № дела, дата вынесения, существо акта.",
              slots=("court_info.case_number",)),
        _proc("circumstances", "Краткие обстоятельства дела",
              "Существенные факты, без переписывания материалов дела.",
              slots=("facts",)),
        _proc("unlawful", "В чём незаконность / необоснованность решения",
              "Обоснование, какие именно выводы суда не соответствуют закону / делу."),
        _proc("material_violations", "Нарушения материального права",
              "Какие именно нормы материального права нарушены / неправильно применены.",),
        _proc("procedural_violations", "Нарушения процессуального права",
              "Какие нормы ГПК / АППК нарушены и как это повлияло на исход дела."),
        _proc("evidence", "Доказательства",
              "Доказательства, имеющиеся в материалах дела и подтверждающие доводы."),
        _proc("petitum", "Просительная часть",
              "Что именно просит сделать суд апелляционной инстанции.",
              slots=("claims",)),
        _proc("attachments", "Приложения",
              "Копия обжалуемого акта, доверенность, документ об оплате госпошлины.",
              slots=("evidence",)),
        _proc("signature", "Дата и подпись",
              "Дата подачи, ФИО подписанта, подпись."),
    ),
    preferred_source_id_tokens=("kz_gpk_code", "kz_appc_code", "kz_vs_np"),
)


CASSATION_COMPLAINT = DocumentTemplate(
    doc_type="cassation_complaint",
    title="КАССАЦИОННАЯ ЖАЛОБА",
    sections=(
        _proc("court_header", "Суд кассационной инстанции",
              "Верховный Суд РК.", slots=()),
        _proc("applicant", "Заявитель", "Реквизиты заявителя жалобы.",
              slots=("parties.applicant",)),
        _proc("parties", "Участники дела",
              "Истец / ответчик / третьи лица."),
        _proc("acts_first_appeal", "Судебные акты первой и апелляционной инстанций",
              "Реквизиты актов, даты, исход.",
              slots=("court_info.case_number",)),
        _proc("dispute_summary", "Краткое содержание спора",
              "Чёткое изложение существа спора без избыточных деталей.",
              slots=("facts",)),
        _proc("material_violations", "Существенные нарушения норм материального права",
              "Конкретные статьи кодексов / законов и как они нарушены."),
        _proc("procedural_violations", "Существенные нарушения норм процессуального права",
              "Конкретные нарушения ГПК / АППК."),
        _proc("impact", "Почему нарушение повлияло на исход дела",
              "Связь нарушения с принятым решением."),
        _proc("admission", "Обоснование допуска / пересмотра",
              "Почему дело подлежит кассационному пересмотру."),
        _proc("petitum", "Просительная часть",
              "Что просит заявитель: отменить, изменить, направить на новое рассмотрение.",
              slots=("claims",)),
        _proc("attachments", "Приложения",
              "Копии судебных актов, доверенность, документ об оплате госпошлины.",
              slots=("evidence",)),
        _proc("signature", "Дата и подпись", "Дата подачи и подпись."),
    ),
    preferred_source_id_tokens=("kz_gpk_code", "kz_appc_code", "kz_vs_np"),
)


PRIVATE_COMPLAINT = DocumentTemplate(
    doc_type="private_complaint",
    title="ЧАСТНАЯ ЖАЛОБА",
    sections=(
        _proc("court_header", "Суд", "Наименование суда апелляционной инстанции."),
        _proc("applicant", "Заявитель", "Реквизиты заявителя.",
              slots=("parties.applicant",)),
        _proc("ruling_data", "Обжалуемое определение",
              "Дата, номер дела, существо определения.",
              slots=("court_info.case_number",)),
        _proc("circumstances", "Краткие обстоятельства",
              "Контекст вынесения определения.", slots=("facts",)),
        _proc("unlawful", "Почему определение незаконно",
              "Конкретные основания: нарушения норм или фактов."),
        _proc("legal_basis", "Правовое обоснование",
              "Нормы ГПК / АППК."),
        _proc("petitum", "Просительная часть",
              "Что просит заявитель.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Копия определения, доверенность.", slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_gpk_code", "kz_appc_code"),
)


MOTION_GENERAL = DocumentTemplate(
    doc_type="motion_general",
    title="ХОДАТАЙСТВО",
    sections=(
        _proc("court_header", "Суд / орган", "Наименование суда или органа."),
        _proc("applicant", "Заявитель", "Реквизиты заявителя.",
              slots=("parties.applicant",)),
        _proc("case_number", "Номер дела", "Номер дела (если есть).",
              slots=("court_info.case_number",)),
        _proc("subject", "Суть ходатайства",
              "Чёткая формулировка того, о чём ходатайствует сторона."),
        _proc("circumstances", "Обстоятельства",
              "Факты, на которых основано ходатайство.", slots=("facts",)),
        _proc("legal_basis", "Правовое обоснование",
              "Нормы ГПК / АППК / иные."),
        _proc("petitum", "Просительная часть",
              "Что просит заявитель.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Документы, обосновывающие ходатайство.", slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_gpk_code", "kz_appc_code"),
)


INTERIM_MEASURES_APPLICATION = DocumentTemplate(
    doc_type="interim_measures_application",
    title="ЗАЯВЛЕНИЕ О ПРИНЯТИИ ОБЕСПЕЧИТЕЛЬНЫХ МЕР",
    sections=(
        _proc("court_header", "Суд", "Суд, рассматривающий дело."),
        _proc("applicant", "Заявитель", "Реквизиты заявителя (истец).",
              slots=("parties.plaintiff",)),
        _proc("defendant", "Ответчик", "Реквизиты ответчика.",
              slots=("parties.defendant",)),
        _proc("claim_summary", "Суть иска",
              "Краткое изложение исковых требований.", slots=("facts",)),
        _proc("requested_measures", "Какие обеспечительные меры просим принять",
              "Конкретный перечень мер: арест, запрет, приостановление и т.п."),
        _proc("risk", "Почему без мер исполнение решения будет затруднено",
              "Обоснование риска неисполнения судебного акта."),
        _proc("evidence", "Доказательства риска",
              "Документы, подтверждающие риск."),
        _proc("legal_basis", "Правовое обоснование",
              "Нормы ГПК / АППК об обеспечительных мерах."),
        _proc("petitum", "Просительная часть",
              "ПРОШУ — конкретные меры.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Копия искового заявления, доверенность.", slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_gpk_code", "kz_appc_code", "kz_vs_np"),
)


RESTORE_DEADLINE_APPLICATION = DocumentTemplate(
    doc_type="restore_deadline_application",
    title="ЗАЯВЛЕНИЕ О ВОССТАНОВЛЕНИИ ПРОПУЩЕННОГО ПРОЦЕССУАЛЬНОГО СРОКА",
    sections=(
        _proc("court_header", "Суд / орган",
              "Суд или орган, перед которым пропущен срок."),
        _proc("applicant", "Заявитель", "Реквизиты заявителя.",
              slots=("parties.applicant",)),
        _proc("missed_deadline", "Какой срок пропущен",
              "Конкретный процессуальный срок и нормативная база."),
        _proc("reasons", "Причины пропуска",
              "Уважительные причины пропуска срока."),
        _proc("evidence", "Доказательства уважительности причин",
              "Больничные, командировки, иные документы."),
        _proc("legal_basis", "Правовое обоснование",
              "Нормы ГПК / АППК о восстановлении сроков."),
        _proc("petitum", "Просительная часть",
              "ПРОШУ — восстановить срок.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Сам процессуальный документ + доказательства.", slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_gpk_code", "kz_appc_code"),
)


ENFORCEMENT_WRIT_APPLICATION = DocumentTemplate(
    doc_type="enforcement_writ_application",
    title="ЗАЯВЛЕНИЕ О ВЫДАЧЕ ИСПОЛНИТЕЛЬНОГО ЛИСТА",
    sections=(
        _proc("court_header", "Суд",
              "Суд первой инстанции, вынесший решение."),
        _proc("applicant", "Заявитель",
              "Реквизиты взыскателя.", slots=("parties.plaintiff",)),
        _proc("act_data", "Судебный акт",
              "Реквизиты судебного акта по делу.",
              slots=("court_info.case_number",)),
        _proc("date_in_force", "Дата вступления в силу",
              "Дата вступления судебного акта в законную силу."),
        _proc("petitum", "Просительная часть",
              "ПРОШУ — выдать исполнительный лист.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Копия судебного акта, доверенность.", slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_gpk_code", "kz_law_enforcement_code"),
)


ADMIN_CLAIM = DocumentTemplate(
    doc_type="admin_claim",
    title="АДМИНИСТРАТИВНОЕ ИСКОВОЕ ЗАЯВЛЕНИЕ",
    sections=(
        _proc("court_header", "Административный суд",
              "Специализированный межрайонный административный суд по подсудности.",
              slots=("court_info.court",)),
        _proc("plaintiff", "Истец", "Реквизиты истца.",
              slots=("parties.plaintiff",)),
        _proc("defendant_body", "Ответчик-госорган",
              "Наименование госоргана, чьи решения / действия / бездействие оспариваются.",
              slots=("parties.defendant",)),
        _proc("contested_act", "Оспариваемое решение / действие / бездействие",
              "Реквизиты решения, дата, исходящий номер."),
        _proc("violated_rights", "Какие права нарушены",
              "Конкретные права истца, нарушенные актом / действием.",
              slots=("facts",)),
        _proc("pretrial", "Досудебный порядок",
              "Соблюдён ли досудебный порядок (по АППК)."),
        _proc("legal_basis", "Правовое обоснование по АППК",
              "Конкретные статьи АППК.",
              ),
        _proc("petitum", "Просительная часть",
              "Что просит истец.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Оспариваемый акт, переписка, доверенность, госпошлина.",
              slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_appc_code", "kz_vs_np"),
)


BAILIFF_COMPLAINT = DocumentTemplate(
    doc_type="bailiff_complaint",
    title="ЖАЛОБА на действия / бездействие судебного исполнителя",
    sections=(
        _proc("court_header", "Орган / суд",
              "Орган исполнительного производства / суд по подсудности."),
        _proc("applicant", "Заявитель", "Реквизиты заявителя.",
              slots=("parties.applicant",)),
        _proc("bailiff", "Судебный исполнитель",
              "ФИО судебного исполнителя, ЧСИ / ГСИ, регион."),
        _proc("case_number", "Исполнительное производство",
              "№ исполнительного производства, дата возбуждения.",
              slots=("court_info.case_number",)),
        _proc("contested_action", "Обжалуемое действие / бездействие",
              "Конкретные действия / бездействие, дата, акт."),
        _proc("violated_rights", "Нарушенные права",
              "Какие права заявителя нарушены.", slots=("facts",)),
        _proc("legal_basis", "Правовое обоснование",
              "Нормы Закона об исполнительном производстве, ГПК."),
        _proc("petitum", "Просительная часть",
              "Что просит заявитель.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Материалы исполнительного производства, доверенность.",
              slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_law_enforcement_code", "kz_gpk_code"),
)


OBJECTION_TO_CLAIM = DocumentTemplate(
    doc_type="objection_to_claim",
    title="ВОЗРАЖЕНИЕ НА ИСКОВОЕ ЗАЯВЛЕНИЕ",
    sections=(
        _proc("court_header", "Суд", "Суд, рассматривающий дело."),
        _proc("defendant", "Ответчик", "Реквизиты ответчика.",
              slots=("parties.defendant",)),
        _proc("plaintiff", "Истец", "Реквизиты истца.",
              slots=("parties.plaintiff",)),
        _proc("case_number", "Номер дела", "Номер дела.",
              slots=("court_info.case_number",)),
        _proc("claim_summary", "Суть иска",
              "Краткое изложение требований истца."),
        _proc("fact_objections", "Возражения по фактам",
              "Какие факты ответчик оспаривает.", slots=("facts",)),
        _proc("legal_objections", "Возражения по праву",
              "Несогласие с правовой квалификацией истца."),
        _proc("evidence", "Доказательства ответчика",
              "Доказательства, опровергающие иск."),
        _proc("petitum", "Просительная часть",
              "В удовлетворении иска отказать (полностью / частично).",
              slots=("claims",)),
        _proc("attachments", "Приложения",
              "Документы ответчика, доверенность.", slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_gk_code", "kz_gpk_code"),
)


RESPONSE_TO_CLAIM = DocumentTemplate(
    doc_type="response_to_claim",
    title="ОТЗЫВ НА ИСКОВОЕ ЗАЯВЛЕНИЕ",
    sections=(
        _proc("court_header", "Суд", "Суд, рассматривающий дело."),
        _proc("defendant", "Ответчик", "Реквизиты ответчика.",
              slots=("parties.defendant",)),
        _proc("plaintiff", "Истец", "Реквизиты истца.",
              slots=("parties.plaintiff",)),
        _proc("case_number", "Номер дела", "Номер дела.",
              slots=("court_info.case_number",)),
        _proc("position", "Позиция по иску",
              "Признание / частичное признание / непризнание."),
        _proc("circumstances", "Обстоятельства",
              "Изложение позиции ответчика.", slots=("facts",)),
        _proc("legal_basis", "Правовое обоснование",
              "Нормы права, обосновывающие позицию ответчика."),
        _proc("evidence", "Доказательства",
              "Доказательства, подтверждающие позицию."),
        _proc("petitum", "Просительная часть",
              "Что просит ответчик.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Документы ответчика, доверенность.", slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_gk_code", "kz_gpk_code"),
)


# Bankruptcy of an individual is intentionally a simplified eGov route — its
# template is small because the substantive content is filled by the eGov form.
INDIVIDUAL_BANKRUPTCY = DocumentTemplate(
    doc_type="individual_bankruptcy",
    title="ЗАЯВЛЕНИЕ о применении процедуры банкротства физического лица",
    sections=(
        _proc("applicant", "Заявитель", "Физическое лицо: ФИО, ИИН, адрес.",
              slots=("parties.applicant",)),
        _proc("circumstances", "Обстоятельства неплатёжеспособности",
              "Период, причины, состав долгов.", slots=("facts",)),
        _proc("creditors", "Кредиторы",
              "Перечень кредиторов и сумм требований."),
        _proc("assets", "Имущество",
              "Сведения об имуществе и доходах."),
        _proc("legal_basis", "Правовое обоснование",
              "Нормы Закона о банкротстве физических лиц / иные."),
        _proc("petitum", "Просительная часть",
              "ПРОШУ — применить соответствующую процедуру.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Документы по доходам, имуществу, задолженности.",
              slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_law_bankruptcy",),
)


# Generic complaint to a state body — used when the user query maps to
# "complaint" but not "admin_claim".
COMPLAINT_TO_STATE_BODY = DocumentTemplate(
    doc_type="complaint_to_state_body",
    title="ЖАЛОБА в государственный орган",
    sections=(
        _proc("addressee", "Адресат", "Государственный орган-адресат жалобы."),
        _proc("applicant", "Заявитель", "Реквизиты заявителя.",
              slots=("parties.applicant",)),
        _proc("contested_act", "Оспариваемое решение / действие / бездействие",
              "Реквизиты, дата, исходящий номер."),
        _proc("violated_rights", "Какие права нарушены",
              "Конкретные права, нарушенные актом / действием.",
              slots=("facts",)),
        _proc("legal_basis", "Правовое обоснование",
              "Нормы АППК / профильных законов."),
        _proc("petitum", "Просительная часть",
              "Что просит заявитель.", slots=("claims",)),
        _proc("attachments", "Приложения",
              "Оспариваемый акт, переписка, доверенность.",
              slots=("evidence",)),
    ),
    preferred_source_id_tokens=("kz_appc_code",),
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DOCUMENT_TEMPLATES: Dict[str, DocumentTemplate] = {
    CLAIM_DEBT_PRETRIAL.doc_type: CLAIM_DEBT_PRETRIAL,
    CIVIL_LAWSUIT_DEBT.doc_type: CIVIL_LAWSUIT_DEBT,
    LEGAL_OPINION.doc_type: LEGAL_OPINION,
    CONTRACT_SERVICES.doc_type: CONTRACT_SERVICES,
    BANKRUPTCY_STATEMENT_TOO.doc_type: BANKRUPTCY_STATEMENT_TOO,
    INDIVIDUAL_BANKRUPTCY.doc_type: INDIVIDUAL_BANKRUPTCY,
    APPEAL_COMPLAINT.doc_type: APPEAL_COMPLAINT,
    CASSATION_COMPLAINT.doc_type: CASSATION_COMPLAINT,
    PRIVATE_COMPLAINT.doc_type: PRIVATE_COMPLAINT,
    MOTION_GENERAL.doc_type: MOTION_GENERAL,
    INTERIM_MEASURES_APPLICATION.doc_type: INTERIM_MEASURES_APPLICATION,
    RESTORE_DEADLINE_APPLICATION.doc_type: RESTORE_DEADLINE_APPLICATION,
    ENFORCEMENT_WRIT_APPLICATION.doc_type: ENFORCEMENT_WRIT_APPLICATION,
    ADMIN_CLAIM.doc_type: ADMIN_CLAIM,
    BAILIFF_COMPLAINT.doc_type: BAILIFF_COMPLAINT,
    OBJECTION_TO_CLAIM.doc_type: OBJECTION_TO_CLAIM,
    RESPONSE_TO_CLAIM.doc_type: RESPONSE_TO_CLAIM,
    COMPLAINT_TO_STATE_BODY.doc_type: COMPLAINT_TO_STATE_BODY,
    # Aliases that the intake / CLI may use.
    "claim": CLAIM_DEBT_PRETRIAL,
    "civil_lawsuit": CIVIL_LAWSUIT_DEBT,
    "complaint": COMPLAINT_TO_STATE_BODY,
    "contract": CONTRACT_SERVICES,
    "bankruptcy_statement": BANKRUPTCY_STATEMENT_TOO,
    "appeal": APPEAL_COMPLAINT,
    "cassation": CASSATION_COMPLAINT,
    "motion": MOTION_GENERAL,
    "interim_measures": INTERIM_MEASURES_APPLICATION,
    "restore_deadline": RESTORE_DEADLINE_APPLICATION,
    "enforcement_writ": ENFORCEMENT_WRIT_APPLICATION,
    "objection": OBJECTION_TO_CLAIM,
    "response": RESPONSE_TO_CLAIM,
    "admin_petition": ADMIN_CLAIM,
}


def get_template(doc_type: str) -> DocumentTemplate:
    """Resolve a doc_type alias to a concrete :class:`DocumentTemplate`.

    Falls back to LEGAL_OPINION when the type is unknown.
    """
    key = (doc_type or "").strip().lower()
    return DOCUMENT_TEMPLATES.get(key, LEGAL_OPINION)


def supported_doc_types() -> List[str]:
    """List of canonical (non-alias) document types."""
    return [
        CLAIM_DEBT_PRETRIAL.doc_type,
        CIVIL_LAWSUIT_DEBT.doc_type,
        LEGAL_OPINION.doc_type,
        CONTRACT_SERVICES.doc_type,
        BANKRUPTCY_STATEMENT_TOO.doc_type,
        INDIVIDUAL_BANKRUPTCY.doc_type,
        APPEAL_COMPLAINT.doc_type,
        CASSATION_COMPLAINT.doc_type,
        PRIVATE_COMPLAINT.doc_type,
        MOTION_GENERAL.doc_type,
        INTERIM_MEASURES_APPLICATION.doc_type,
        RESTORE_DEADLINE_APPLICATION.doc_type,
        ENFORCEMENT_WRIT_APPLICATION.doc_type,
        ADMIN_CLAIM.doc_type,
        BAILIFF_COMPLAINT.doc_type,
        OBJECTION_TO_CLAIM.doc_type,
        RESPONSE_TO_CLAIM.doc_type,
        COMPLAINT_TO_STATE_BODY.doc_type,
    ]


__all__ = [
    "ADMIN_CLAIM",
    "APPEAL_COMPLAINT",
    "BAILIFF_COMPLAINT",
    "BANKRUPTCY_STATEMENT_TOO",
    "CASSATION_COMPLAINT",
    "CIVIL_LAWSUIT_DEBT",
    "CLAIM_DEBT_PRETRIAL",
    "COMPLAINT_TO_STATE_BODY",
    "CONTRACT_SERVICES",
    "DOCUMENT_TEMPLATES",
    "DocumentTemplate",
    "ENFORCEMENT_WRIT_APPLICATION",
    "INDIVIDUAL_BANKRUPTCY",
    "INTERIM_MEASURES_APPLICATION",
    "LEGAL_OPINION",
    "MOTION_GENERAL",
    "OBJECTION_TO_CLAIM",
    "PRIVATE_COMPLAINT",
    "RESPONSE_TO_CLAIM",
    "RESTORE_DEADLINE_APPLICATION",
    "SectionTemplate",
    "get_template",
    "supported_doc_types",
]
