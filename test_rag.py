from rag.rag_retriever import retrieve_rag

result = retrieve_rag(
    task_type="contract",
    queries=[
        "договор возмездного оказания услуг",
        "ответственность сторон",
        "срок исполнения",
        "подсудность",
        "форс-мажор",
        "НДС"
    ],
    source_ids=[
        "kz_gk_code",
        "kz_nk_code"
    ],
    min_articles=15
)

print("ARTICLES:", result["coverage"]["unique_articles"])
