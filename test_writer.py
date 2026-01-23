# test_writer.py
# Запускать из корня проекта: python test_writer.py

from app.retrivier.rag_retriever import retrieve_rag
from app.retrivier.rag_verifier import verify_and_filter_rag
from app.llm.writer import (
    build_writer_prompt,
    build_long_generation_plan,
)

# 1️⃣ Получаем RAG (строго по статьям)
rag = retrieve_rag(
    task_type="contract",
    queries=[
        "договор возмездного оказания услуг",
        "предмет договора",
        "ответственность сторон",
        "срок исполнения обязательств",
        "подсудность",
        "форс-мажор",
        "налог на добавленную стоимость",
    ],
    source_ids=[
        "kz_gk_code",
        "kz_nk_code",
    ],
    min_articles=50,  # ⚠️ сразу требуем минимум 50
)

print("RAG FOUND:", len(rag))

# 2️⃣ Верификация: жёстко 50–80 статей
verified = verify_and_filter_rag(
    rag,
    min_articles=50,
    max_articles=80,
)

verified_rag = verified["verified_rag"]

print("RAG AFTER VERIFICATION:", len(verified_rag))

# 3️⃣ Факты дела (вход для LLM)
facts = {
    "Тип договора": "Договор возмездного оказания IT-услуг",
    "Стороны": "ТОО «Заказчик» и ТОО «Исполнитель»",
    "Предмет": "Разработка и внедрение программного обеспечения",
    "Срок исполнения": "2 календарные недели",
    "Цена": "550 000 тенге, включая НДС",
    "Подсудность": "Республика Казахстан",
}

# 4️⃣ Строим ЖЁСТКИЙ writer-пrompt
prompt = build_writer_prompt(
    task_type="contract",
    facts=facts,
    verified_rag=verified_rag,
)

# 5️⃣ План длинной генерации (15–30+ страниц)
generation_plan = build_long_generation_plan()

print("\n==============================")
print("PROMPT LENGTH:", len(prompt))
print("==============================\n")

print("GENERATION PLAN:")
print(generation_plan)

print("\n==============================")
print("PROMPT PREVIEW (first 2000 chars)")
print("==============================\n")
print(prompt[:2000])
