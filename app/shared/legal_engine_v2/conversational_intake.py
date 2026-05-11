"""Conversational intake bridge for the web UI.

The web product is conversational: the user types a free-form description,
the system detects a doc_type (or keeps the entry as a consultation), then
asks **one question at a time** about missing facts. Once enough facts are
collected, the UI shows a summary and offers payment + DOCX generation.

This module is a thin orchestrator on top of Legal Engine v2:

- :func:`detect_doc_type_from_message` — uses
  :func:`build_document_request_from_query` + entry-point hints.
- :class:`ConversationState` — JSON-serialisable conversational state.
- :func:`start_conversation` — initial greeting per entry-point.
- :func:`step_conversation` — take a user message, update state, return next
  AI message and metadata (next question or summary).
- :func:`build_summary` — short summary card before payment.

No OpenAI required: deterministic intake + slot filler. Voice flows pass
already-transcribed text through this same pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.shared.legal_engine_v2.document_intake import (
    build_document_request_from_query,
)
from app.shared.legal_engine_v2.document_schemas import DocumentRequest
from app.shared.legal_engine_v2.document_templates import (
    get_template,
    supported_doc_types,
)
from app.shared.legal_engine_v2.query_understanding import (
    PROCEDURAL_DOC_TYPE_HINTS,
    understand_query_deterministic,
)
from app.shared.legal_engine_v2.slot_filler import (
    Question,
    build_missing_fact_questions,
    merge_slot_answers,
    render_questions_text,
)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

ENTRY_CONSULT = "consult"
ENTRY_DOCUMENT = "document"
ENTRY_COURT = "court_documents"
ENTRY_BANKRUPTCY = "bankruptcy"
ENTRY_ANALYZE = "document_analysis"

ENTRY_POINTS = (
    ENTRY_CONSULT,
    ENTRY_DOCUMENT,
    ENTRY_COURT,
    ENTRY_BANKRUPTCY,
    ENTRY_ANALYZE,
)


# Default doc_type hint for each entry point — used if the user message does
# not allow a confident detection.
ENTRY_DEFAULT_DOC_TYPE: Dict[str, str | None] = {
    ENTRY_CONSULT: None,  # consult mode → no doc generation
    ENTRY_DOCUMENT: None,  # let intake decide
    ENTRY_COURT: "civil_lawsuit_debt",
    ENTRY_BANKRUPTCY: "bankruptcy_statement_too",
    ENTRY_ANALYZE: None,
}


# Conversational entry messages (KZ first, RU second). The web layer pulls
# these via product_copy; we keep them here as a fallback that does not
# depend on the templating layer.
ENTRY_OPEN_MESSAGES: Dict[str, Dict[str, str]] = {
    ENTRY_CONSULT: {
        "kk": "Жағдайыңызды өз сөзіңізбен сипаттаңыз. Мен сұрақтарыңызға жауап беруге тырысамын.",
        "ru": "Опишите ситуацию своими словами. Я постараюсь ответить на ваши вопросы.",
    },
    ENTRY_DOCUMENT: {
        "kk": "Қандай құжат дайындау керек? Жағдайыңызды өз сөзіңізбен сипаттаңыз.",
        "ru": "Какой документ нужно подготовить? Опишите ситуацию своими словами.",
    },
    ENTRY_COURT: {
        "kk": (
            "Қандай сот құжаты керек? Талап арыз, апелляция, кассация, "
            "өтінішхат немесе басқа құжат па? Істің мән-жайын сипаттаңыз."
        ),
        "ru": (
            "Какой судебный документ нужен? Иск, апелляция, кассация, "
            "ходатайство или другой документ? Опишите ситуацию."
        ),
    },
    ENTRY_BANKRUPTCY: {
        "kk": (
            "Банкроттық бойынша жағдайды сипаттаңыз: ТОО, ИП немесе жеке тұлға ма? "
            "Қарыз сомасы, кредиторлар, салық берешегі, активтер бар ма?"
        ),
        "ru": (
            "Опишите ситуацию по банкротству: ТОО, ИП или физическое лицо? "
            "Сумма долгов, кредиторы, налоговая задолженность, активы?"
        ),
    },
    ENTRY_ANALYZE: {
        "kk": "Талдау үшін құжатты жүктеңіз (DOCX/TXT).",
        "ru": "Загрузите документ для анализа (DOCX/TXT).",
    },
}


# Keyword hints — light pre-filter before invoking the full intake parser.
# These do not invent facts; they only steer doc_type detection.
_DOC_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "cassation_complaint": ("кассация", "кассациялық"),
    "appeal_complaint": ("апелляция", "апелляциялық"),
    "private_complaint": ("частная жалоба", "жеке шағым"),
    "interim_measures_application": (
        "обеспечительные", "обеспечение иска", "қамтамасыз ету",
    ),
    "restore_deadline_application": (
        "восстановить срок", "пропущен срок", "мерзімді қалпына",
    ),
    "enforcement_writ_application": ("исполнительный лист", "атқару парағы"),
    "admin_claim": (
        "административный иск", "жалоба на госорган", "әкімшілік талап",
    ),
    "bailiff_complaint": ("ЧСИ", "судебный исполнитель", "сот орындаушы"),
    "objection_to_claim": ("возражение на иск", "талапқа қарсылық"),
    "response_to_claim": ("отзыв на иск", "пікір"),
    "motion_general": ("ходатайство", "өтінішхат"),
    "bankruptcy_statement_too": ("банкротство тоо", "тоо банкрот"),
    "individual_bankruptcy": ("банкротство физ", "жеке тұлға банкрот"),
    "civil_lawsuit_debt": ("исковое", "взыскание долга", "қарыз өндіру"),
    "claim_debt_pretrial": ("претензия", "талап-хат"),
    "contract_services": ("договор", "шарт"),
    "legal_opinion": ("правовое заключение", "құқықтық қорытынды"),
}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class ConversationState:
    """JSON-serialisable conversation state.

    Stored in the DB (or session for guests). Pure data: no methods that
    perform I/O. The orchestrator updates this on every step.
    """

    entry_point: str = ENTRY_CONSULT
    language: str = "kk"
    detected_doc_type: Optional[str] = None
    user_messages: List[str] = field(default_factory=list)
    assistant_messages: List[str] = field(default_factory=list)
    collected_facts: Dict[str, Any] = field(default_factory=dict)
    answered_keys: List[str] = field(default_factory=list)
    pending_question_keys: List[str] = field(default_factory=list)
    ready_for_summary: bool = False
    ready_for_payment: bool = False
    ready_for_generation: bool = False

    def to_dict(self) -> dict:
        return {
            "entry_point": self.entry_point,
            "language": self.language,
            "detected_doc_type": self.detected_doc_type,
            "user_messages": list(self.user_messages),
            "assistant_messages": list(self.assistant_messages),
            "collected_facts": dict(self.collected_facts),
            "answered_keys": list(self.answered_keys),
            "pending_question_keys": list(self.pending_question_keys),
            "ready_for_summary": self.ready_for_summary,
            "ready_for_payment": self.ready_for_payment,
            "ready_for_generation": self.ready_for_generation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "ConversationState":
        if not isinstance(data, dict):
            return cls()
        return cls(
            entry_point=str(data.get("entry_point") or ENTRY_CONSULT),
            language=str(data.get("language") or "kk"),
            detected_doc_type=data.get("detected_doc_type") or None,
            user_messages=list(data.get("user_messages") or []),
            assistant_messages=list(data.get("assistant_messages") or []),
            collected_facts=dict(data.get("collected_facts") or {}),
            answered_keys=list(data.get("answered_keys") or []),
            pending_question_keys=list(data.get("pending_question_keys") or []),
            ready_for_summary=bool(data.get("ready_for_summary")),
            ready_for_payment=bool(data.get("ready_for_payment")),
            ready_for_generation=bool(data.get("ready_for_generation")),
        )


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_doc_type_from_message(
    message: str,
    *,
    entry_point: str = ENTRY_DOCUMENT,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """Best-effort doc_type detection without inventing data.

    1. Try keyword hints (fast, deterministic).
    2. Fall back to :func:`build_document_request_from_query` (full intake).
    3. Apply entry-point default if still unknown.
    """

    msg = (message or "").strip().lower()
    if not msg:
        return fallback or ENTRY_DEFAULT_DOC_TYPE.get(entry_point)

    # Keyword hints first.
    for doc_type, kws in _DOC_KEYWORDS.items():
        for kw in kws:
            if kw and kw.lower() in msg:
                return doc_type

    # Procedural hints (already aliased in query_understanding). The
    # source is a ``tuple[tuple[str, str], ...]``.
    for needle, doc_type in PROCEDURAL_DOC_TYPE_HINTS:
        if needle and all(part in msg for part in needle.split()):
            return doc_type

    # Full intake parser as fallback.
    try:
        u = understand_query_deterministic(message)
        request = build_document_request_from_query(message, u)
        if request and request.doc_type:
            return request.doc_type
    except Exception:  # pragma: no cover — defensive
        pass

    return fallback or ENTRY_DEFAULT_DOC_TYPE.get(entry_point)


# ---------------------------------------------------------------------------
# Public conversation API
# ---------------------------------------------------------------------------

def start_conversation(
    entry_point: str = ENTRY_CONSULT,
    language: str = "kk",
) -> ConversationState:
    """Return an initial state with the entry-point opener."""

    ep = entry_point if entry_point in ENTRY_POINTS else ENTRY_CONSULT
    lang = language if language in {"kk", "ru"} else "kk"
    state = ConversationState(entry_point=ep, language=lang)
    state.assistant_messages.append(_opener(ep, lang))
    return state


def _opener(entry_point: str, language: str) -> str:
    msg = ENTRY_OPEN_MESSAGES.get(entry_point, ENTRY_OPEN_MESSAGES[ENTRY_CONSULT])
    return msg.get(language) or msg.get("kk") or ""


# Limit how many slot questions we ask in one turn before showing summary.
MAX_QUESTIONS_PER_TURN = 1


def step_conversation(
    state: ConversationState,
    user_message: str,
    *,
    use_llm: bool = False,
) -> Dict[str, Any]:
    """Process a user message and return next AI step.

    Returns a dict with:

    - ``state`` — updated :class:`ConversationState`
    - ``assistant_text`` — next AI message
    - ``next_questions`` — list of :class:`Question` to render in UI
    - ``ready_for_summary`` — bool
    - ``summary`` — dict (only when ``ready_for_summary``)
    """

    msg = (user_message or "").strip()
    if msg:
        state.user_messages.append(msg)

    # Re-detect doc_type if not yet locked.
    if not state.detected_doc_type:
        state.detected_doc_type = detect_doc_type_from_message(
            msg, entry_point=state.entry_point
        )

    # Consultation mode never generates a document — short-circuit.
    if state.entry_point == ENTRY_CONSULT:
        reply = (
            "Сұрағыңыз қабылданды. Толық жауап үшін «Кеңес» бөлімінде жалғастырыңыз."
            if state.language == "kk"
            else "Вопрос принят. Для полного ответа продолжайте в разделе «Консультация»."
        )
        state.assistant_messages.append(reply)
        return {
            "state": state,
            "assistant_text": reply,
            "next_questions": [],
            "ready_for_summary": False,
            "summary": None,
        }

    # Document modes — build a DocumentRequest from the **whole** transcript
    # (joining all user messages preserves earlier facts), then ask the slot
    # filler what is still missing.
    full_query = " \n".join(state.user_messages).strip()
    try:
        understanding = understand_query_deterministic(full_query)
        request = build_document_request_from_query(
            full_query, understanding, doc_type=state.detected_doc_type
        )
    except Exception:
        request = DocumentRequest(
            doc_type=state.detected_doc_type or "legal_opinion",
            raw_query=full_query,
        )

    # Apply already-collected slot answers (from prior turns).
    if state.collected_facts:
        request = merge_slot_answers(request, state.collected_facts)

    # Compute remaining required questions.
    questions = build_missing_fact_questions(
        request, doc_type=request.doc_type or state.detected_doc_type
    )
    required_questions = [q for q in questions if q.required]

    # Mark as ready for summary if no required questions remain.
    if not required_questions:
        state.ready_for_summary = True
        state.ready_for_payment = True
        state.assistant_messages.append(
            "Барлық қажетті деректер жиналды. Қысқаша қорытынды дайын."
            if state.language == "kk"
            else "Все необходимые данные собраны. Краткое резюме готово."
        )
        return {
            "state": state,
            "assistant_text": state.assistant_messages[-1],
            "next_questions": [],
            "ready_for_summary": True,
            "summary": build_summary(state, request),
        }

    # Otherwise pose the next question(s).
    next_q = required_questions[:MAX_QUESTIONS_PER_TURN]
    state.pending_question_keys = [q.key for q in next_q]
    next_text = render_questions_text(next_q)
    state.assistant_messages.append(next_text)
    return {
        "state": state,
        "assistant_text": next_text,
        "next_questions": [_question_to_dict(q) for q in next_q],
        "ready_for_summary": False,
        "summary": None,
    }


def submit_slot_answer(
    state: ConversationState,
    key: str,
    value: str,
) -> ConversationState:
    """Save a single slot answer and continue."""

    if not key:
        return state
    state.collected_facts[key] = value
    if key not in state.answered_keys:
        state.answered_keys.append(key)
    if key in state.pending_question_keys:
        state.pending_question_keys.remove(key)
    return state


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def build_summary(
    state: ConversationState,
    request: Optional[DocumentRequest] = None,
) -> Dict[str, Any]:
    """Build a short summary card the UI can render before payment."""

    doc_type = state.detected_doc_type or (
        request.doc_type if request else "legal_opinion"
    )
    template = get_template(doc_type)
    title = template.title or doc_type
    section_titles = [s.title for s in template.sections]
    return {
        "doc_type": doc_type,
        "title": title,
        "section_titles": section_titles,
        "collected_facts": dict(state.collected_facts),
        "language": state.language,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _question_to_dict(q: Question) -> Dict[str, Any]:
    return {
        "key": q.key,
        "text": q.text,
        "required": q.required,
        "example": getattr(q, "example", "") or "",
        "validation_hint": getattr(q, "validation_hint", "") or "",
    }


__all__ = [
    "ConversationState",
    "ENTRY_ANALYZE",
    "ENTRY_BANKRUPTCY",
    "ENTRY_CONSULT",
    "ENTRY_COURT",
    "ENTRY_DEFAULT_DOC_TYPE",
    "ENTRY_DOCUMENT",
    "ENTRY_OPEN_MESSAGES",
    "ENTRY_POINTS",
    "MAX_QUESTIONS_PER_TURN",
    "build_summary",
    "detect_doc_type_from_message",
    "start_conversation",
    "step_conversation",
    "submit_slot_answer",
]
