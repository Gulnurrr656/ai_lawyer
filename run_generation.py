# run_generation.py
# Реальная генерация договора по RAG + плану

import os
from app.retrivier import retrieve_rag, verify_and_filter_rag
from app.llm.writer import (
    build_writer_prompt,
    build_long_generation_plan,
    call_llm_chunked,
)

# === 1️⃣ Получаем RAG ===
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
    source_ids=["kz_gk_code", "kz_nk_code"],
    min_articles=50,
)

verified = verify_and_filter_rag(
    rag,
    min_articles=50,
    max_articles=80,
)

verified_rag = verified["verified_rag"]

print(f"✔ Используем статей: {len(verified_rag)}")

# === 2️⃣ Факты ===
facts = {
    "Тип договора": "Договор возмездного оказания IT-услуг",
    "Стороны": "ТОО «Заказчик» и ТОО «Исполнитель»",
    "Предмет": "Разработка и внедрение программного обеспечения",
    "Срок исполнения": "2 календарные недели",
    "Цена": "550 000 тенге, включая НДС",
    "Подсудность": "Республика Казахстан",
}

# === 3️⃣ Строим prompt ===
prompt = build_writer_prompt(
    task_type="contract",
    facts=facts,
    verified_rag=verified_rag,
)

plan = build_long_generation_plan()

# === 4️⃣ Генерация по частям ===
print("🚀 Начинаю генерацию договора...\n")

parts = call_llm_chunked(
    system_prompt=prompt,
    generation_plan=plan,
)

# === 5️⃣ Склеиваем результат ===
final_text = "\n\n".join(parts)

# === 6️⃣ Сохраняем ===
os.makedirs("output", exist_ok=True)

with open("output/contract_result.txt", "w", encoding="utf-8") as f:
    f.write(final_text)

print("\n✅ ГОТОВО")
print("📄 Файл: output/contract_result.txt")
print(f"📏 Длина текста: {len(final_text)} символов")
