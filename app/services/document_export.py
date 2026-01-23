import os
from pathlib import Path
from datetime import datetime

from docx import Document

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))


def _ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def _find_ttf_font() -> str | None:
    """
    Нужен TTF со поддержкой кириллицы.
    Ищем по нескольким местам (Windows/Linux/папка проекта).
    """
    candidates = [
        os.getenv("PDF_FONT_PATH"),
        str(Path("app/assets/fonts/DejaVuSans.ttf")),
        str(Path("assets/fonts/DejaVuSans.ttf")),
        # Windows (часто есть)
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\DejaVuSans.ttf",
        # Linux (Railway/Docker)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def save_docx(text: str, filename_prefix: str) -> str:
    out_dir = _ensure_output_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"{filename_prefix}_{ts}.docx"

    doc = Document()
    for block in (text or "").split("\n\n"):
        doc.add_paragraph(block.strip())
    doc.save(str(path))

    return str(path)


def save_pdf(text: str, filename_prefix: str) -> str:
    out_dir = _ensure_output_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"{filename_prefix}_{ts}.pdf"

    if not text or len(text.strip()) < 200:
        raise ValueError("Final text too short for PDF")

    font_path = _find_ttf_font()
    font_name = "Helvetica"

    # Регистрируем кириллический TTF, если нашли
    if font_path:
        font_name = "CyrFont"
        pdfmetrics.registerFont(TTFont(font_name, font_path))

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    left = 40
    top = height - 40
    line_height = 14

    c.setFont(font_name, 11)

    y = top
    for paragraph in text.split("\n\n"):
        for line in paragraph.split("\n"):
            line = line.rstrip()
            if not line:
                y -= line_height
                continue

            # примитивный перенос по ширине
            while line:
                max_chars = 110  # примерно под A4 при 11pt
                chunk = line[:max_chars]
                line = line[max_chars:]

                if y < 60:
                    c.showPage()
                    c.setFont(font_name, 11)
                    y = top

                c.drawString(left, y, chunk)
                y -= line_height

        y -= line_height  # пустая строка между абзацами

    c.save()
    return str(path)
