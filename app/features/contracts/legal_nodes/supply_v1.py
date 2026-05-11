# app/features/contracts/legal_nodes/supply_v1.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LegalNodeV1:
    node_id: str
    title: str
    contract_section: str
    facts_keys: tuple[str, ...]
    query_templates: tuple[str, ...]
    default_closure_style: str
    risk_keys: tuple[str, ...]
    expected_sources: tuple[str, ...]
    traceability_role: str


SUPPLY_LEGAL_NODES_V1: tuple[LegalNodeV1, ...] = (
    LegalNodeV1(
        node_id="supply_parties_title",
        title="Стороны, преамбула, название",
        contract_section="1",
        facts_keys=("contract_title", "parties"),
        query_templates=(
            "договор поставки Республика Казахстан поставщик покупатель реквизиты полномочия представителя",
            "существенные условия договор поставки стороны заключение договора ГК РК",
            "{contract_title} стороны преамбула договора поставки",
        ),
        default_closure_style="neutral_frame: наименование типового договора без выдуманных реквизитов; «определение сторон по реквизитам ниже»",
        risk_keys=("misidentification_party", "missing_bin"),
        expected_sources=("kz_gk_code", "kz_law_llp_code"),
        traceability_role="Фиксирует опору на общие положения об обязательствах и идентификации сторон; якорь для последующих узлов.",
    ),
    LegalNodeV1(
        node_id="supply_subject_goods",
        title="Предмет: товар, соответствие описанию",
        contract_section="1",
        facts_keys=("goods", "product", "subject_of_contract", "supply_kind"),
        query_templates=(
            "поставка товар предмет договора переход собственности ГК РК",
            "качество товар соответствие договору поставка",
            "{goods} поставка качество",
        ),
        default_closure_style="defer_to_spec: «ассортимент, количество и цены по приложению — спецификации»; не выдумывать SKU",
        risk_keys=("vague_subject", "spec_missing"),
        expected_sources=("kz_gk_code", "kz_vs_np_invalidity_of_transactions_code"),
        traceability_role="Показывает, как RAG уточнил существенные условия и соответствие предмета.",
    ),
    LegalNodeV1(
        node_id="supply_assortment_qty_quality",
        title="Ассортимент, количество, качество, комплектность",
        contract_section="1, 3",
        facts_keys=("goods", "product", "technical_task", "specification", "tz"),
        query_templates=(
            "количество товар поставка комплектность ассортимент спецификация ГК РК",
            "качество товара соответствие условиям договора поставки отклонение комплектности",
            "документы качества товара при поставке соответствие спецификации Казахстан",
        ),
        default_closure_style="spec_attachment: закрытие через обязательную спецификацию/приложения; «при отсутствии иного письменного согласования — по типовым нормам качества для данной категории без марки»",
        risk_keys=("non_conformity", "completeness_dispute"),
        expected_sources=("kz_gk_code", "kz_vs_np_civil_judgment_code"),
        traceability_role="Трасса для споров о несоответствии и доказательственной базы.",
    ),
    LegalNodeV1(
        node_id="supply_spec_tz_docs",
        title="Спецификация, ТЗ, документы на товар",
        contract_section="3",
        facts_keys=("technical_task", "specification", "tz", "goods"),
        query_templates=(
            "техническое задание договор поставка приложение",
            "документы товар происхождении соответствие ГК РК",
            "санитарные технические регламенты товар Казахстан",
        ),
        default_closure_style="appendix_driven: «состав и форма документов — по спецификации; стороны признают приложения неотъемлемой частью»",
        risk_keys=("regulatory_docs_gap", "import_export_unknown"),
        expected_sources=("kz_gk_code",),
        traceability_role="Связывает приложения с обязательствами поставщика по документам.",
    ),
    LegalNodeV1(
        node_id="supply_delivery_terms",
        title="Сроки, партии, место, порядок поставки",
        contract_section="4",
        facts_keys=("supply_term", "service_term", "performance_terms"),
        query_templates=(
            "срок поставка партии договор ГК РК",
            "опоздание поставка ответственность",
            "график поставки договор",
        ),
        default_closure_style="timeline_agreement: «конкретные даты/партии — в графике (приложении) или ДС»",
        risk_keys=("delay_cascade", "partial_performance"),
        expected_sources=("kz_gk_code", "kz_vs_np_civil_judgment_code"),
        traceability_role="Документирует нормы о надлежащем исполнении сроков.",
    ),
    LegalNodeV1(
        node_id="supply_transfer_title_risk",
        title="Переход права и рисков",
        contract_section="4",
        facts_keys=("supply_term", "goods", "parties"),
        query_templates=(
            "переход права собственности поставка ГК РК",
            "риск случайной гибели товар поставка",
            "момент передачи товар поставка",
        ),
        default_closure_style="default_statutory: если факты молчат — типовая привязка к передаче/отгрузке в формулировках из RAG, без выдуманного INCOTERM",
        risk_keys=("FOT_mismatch", "carrier_dispute"),
        expected_sources=("kz_gk_code", "kz_vs_np_civil_judgment_code"),
        traceability_role="Критичный узел: какие статьи зафиксировали момент рисков.",
    ),
    LegalNodeV1(
        node_id="supply_price_change",
        title="Цена, валюта, изменение цены",
        contract_section="6",
        facts_keys=("supply_price", "service_price", "price", "price_and_payment"),
        query_templates=(
            "цена договор поставка изменение цены ГК РК",
            "индексация цена товар поставка",
            "НДС цена договор Казахстан",
        ),
        default_closure_style="written_amendment: изменение цены только письменным допсоглашением; без чисел если нет в facts",
        risk_keys=("price_surge", "vat_error"),
        expected_sources=("kz_gk_code", "kz_nk_code"),
        traceability_role="Трасса налоговых и ценовых конструкций.",
    ),
    LegalNodeV1(
        node_id="supply_payment",
        title="Порядок расчётов, предоплата, аккредитив и т.д.",
        contract_section="7",
        facts_keys=("payment_terms", "payment_due", "price_and_payment"),
        query_templates=(
            "оплата товар поставка предоплата ГК РК",
            "рассрочка оплата поставка",
            "неустойка за просрочку оплаты",
        ),
        default_closure_style="staged_payment_general: этапы оплаты — в приложении или типовые без сумм если нет данных",
        risk_keys=("prepayment_exposure", "currency_control"),
        expected_sources=("kz_gk_code", "kz_law_currency_control_code"),
        traceability_role="Показывает опору на режим обязательств оплаты.",
    ),
    LegalNodeV1(
        node_id="supply_acceptance_qty_quality",
        title="Приёмка, претензии, сроки уведомления о недостатках",
        contract_section="9",
        facts_keys=("supply_acceptance", "service_acceptance", "goods"),
        query_templates=(
            "приёмка товар количество качество претензия ГК РК",
            "срок уведомления недостатки товар поставка",
            "акт приемки товар спор",
        ),
        default_closure_style="claim_window_statutory: сроки и порядок претензии — из RAG; если не извлечено — нейтральная отсылка к закону и разумному сроку без фейковых дней",
        risk_keys=("silent_acceptance", "hidden_defects"),
        expected_sources=("kz_gk_code", "kz_vs_np_civil_judgment_code"),
        traceability_role="Высокий практический вес — обязательная трасса.",
    ),
    LegalNodeV1(
        node_id="supply_warranties",
        title="Гарантии, недостатки, последствия",
        contract_section="10",
        facts_keys=("warranty", "quality_guarantees", "quality_requirements", "goods"),
        query_templates=(
            "гарантия качество товар поставка ГК РК",
            "устранение недостатков поставщик срок",
            "гарантийный срок товар",
        ),
        default_closure_style="scope_in_appendix: сроки/объём гарантии в приложении или «стандарт производителя если применимо»",
        risk_keys=("warranty_exclusion_overbroad",),
        expected_sources=("kz_gk_code",),
        traceability_role="Связь гарантийных обязательств с нормами о последствиях.",
    ),
    LegalNodeV1(
        node_id="supply_liability_penalty",
        title="Ответственность, неустойка, ограничения",
        contract_section="11",
        facts_keys=("supply_liability", "liability_mode"),
        query_templates=(
            "неустойка поставка ГК РК",
            "подлежащее взысканию убытки ограничение ответственности",
            "пеня просрочка поставка",
        ),
        default_closure_style="capped_reasonable: неустойка соразмерная без конкретного % если нет в facts; оговорка о доказывании убытков",
        risk_keys=("penalty_excessive", "liability_cap_unfair"),
        expected_sources=("kz_gk_code", "kz_vs_np_civil_judgment_code"),
        traceability_role="Трасса договорных санкций и судебного контроля.",
    ),
    LegalNodeV1(
        node_id="supply_force_majeure",
        title="Форс-мажор",
        contract_section="13",
        facts_keys=("force_majeure",),
        query_templates=(
            "форс мажор обязательство ГК РК",
            "освобождение ответственности форс мажор доказательство",
        ),
        default_closure_style="standard_clause: уведомление, разумные сроки, последствия — по типовым нормам из RAG",
        risk_keys=("fm_overuse",),
        expected_sources=("kz_gk_code",),
        traceability_role="Доказуемость освобождения.",
    ),
    LegalNodeV1(
        node_id="supply_claims_dispute",
        title="Претензии, подсудность, арбитраж",
        contract_section="16, 17",
        facts_keys=("dispute", "notice"),
        query_templates=(
            "претензионный порядок ГК РК",
            "подсудность договор Казахстан",
            "арбитраж оговорка договор",
        ),
        default_closure_style="court_default: если спор не согласован — компетентный суд по общим правилам ГПК/заключительные нормы без выдуманного номера суда",
        risk_keys=("jurisdiction_conflict", "consumer_edge_case"),
        expected_sources=(
            "kz_gk_code",
            "kz_law_arbitration_code",
            "kz_vs_np_civil_procedure_norms_code",
        ),
        traceability_role="Куда «сели» нормы процедуры.",
    ),
    LegalNodeV1(
        node_id="supply_confidential_pd",
        title="Конфиденциальность, ПД (если применимо)",
        contract_section="14, 15",
        facts_keys=("confidential", "pd"),
        query_templates=(
            "конфиденциальность коммерческая тайна договор Казахстан",
            "персональные данные обработка договор ЗРК",
        ),
        default_closure_style="if_applicable: если facts «нет» — краткий раздел «не применяется» с пояснением в трассе как user_fact/default_closure",
        risk_keys=("pd_overcollection",),
        expected_sources=("kz_law_personal_data_code", "kz_gk_code"),
        traceability_role="Ограничение объёма обработки под факты.",
    ),
    LegalNodeV1(
        node_id="supply_termination",
        title="Расторжение, односторонний отказ (в рамках типовых оснований)",
        contract_section="18",
        facts_keys=("termination",),
        query_templates=(
            "расторжение договор поставка существенное нарушение ГК РК",
            "односторонний отказ поставка",
        ),
        default_closure_style="material_breach_frame: без выдуманных оснований; отсылка к существенному нарушению из ГК",
        risk_keys=("wrongful_termination",),
        expected_sources=("kz_gk_code", "kz_vs_np_invalidity_of_transactions_code"),
        traceability_role="Трасса материальности нарушений.",
    ),
    LegalNodeV1(
        node_id="supply_final_misc",
        title="Заключительные положения, уведомления, толкование",
        contract_section="16, 19",
        facts_keys=("notice", "intake_extras"),
        query_templates=(
            "уведомления юридическая сила договор ГК РК",
            "изменение договор письменная форма",
        ),
        default_closure_style="written_form_emphasis: изменения только в письме; адреса в реквизитах",
        risk_keys=("oral_amendment_risk",),
        expected_sources=("kz_gk_code",),
        traceability_role="Связывает форму сделки с последующими спорами.",
    ),
    LegalNodeV1(
        node_id="supply_appendices",
        title="Приложения, ссылки на формы",
        contract_section="3, 19-20",
        facts_keys=("goods", "supply_term", "technical_task"),
        query_templates=(
            "приложение спецификация договор поставка обязательность неотъемлемая часть",
            "товарная накладная акт приёмки передачи товара поставка",
            "график поставки товара приложение к договору поставки сроки партий",
        ),
        default_closure_style="enumerate_from_profile: перечень приложений согласно профилю/фактам; без нумерации если профиль задаёт канон",
        risk_keys=("orphan_appendix_ref",),
        expected_sources=("kz_gk_code",),
        traceability_role="Подтверждает, что состав приложений легитимирован нормами об интегральности договора.",
    ),
    LegalNodeV1(
        node_id="supply_requisites_signatures",
        title="Реквизиты и подписи",
        contract_section="20",
        facts_keys=("parties",),
        query_templates=(
            "реквизиты юридическое лицо договор Казахстан",
            "подпись уполномоченное лицо договор",
        ),
        default_closure_style="placeholder_safe: блок для заполнения реквизитов без вымышленных БИН; «стороны подписали ниже»",
        risk_keys=("authority_signatory",),
        expected_sources=("kz_gk_code", "kz_law_llp_code"),
        traceability_role="Завершение трассы; влияние на форму и полномочия.",
    ),
)
