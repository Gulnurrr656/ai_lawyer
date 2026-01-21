import asyncio
from app.ui.services.llm import LlmService

async def run():
    llm = LlmService()
    text = await llm.generate(
        mode="consult",
        facts={"question": "Можно ли расторгнуть договор по соглашению сторон?"},
        rag_context="Нормы права не найдены."
    )
    print(text)

asyncio.run(run())
