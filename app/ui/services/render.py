from pathlib import Path
from datetime import datetime

from docx import Document
from docx.shared import Pt

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


# куда сохраняем сгенерированные файлы
GENERATED_DIR = Path("generated")
GENERATED_DIR.mkdir(exist_ok=True)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# =========================
# DOCX
# =========================

def render_docx(text: str, filename_prefix: str = "document") -> Path:
    """
    Создаёт DOCX-файл из текста
    """
    file_path = GENERATED_DIR / f"{filename_prefix}_{_timestamp()}.docx"

    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)

    for block in text.split("\n\n"):
        p = doc.add_paragraph(block)
        p.paragraph_format.space_after = Pt(12)

    doc.save(file_path)
    return file_path


# =========================
# PDF
# =========================

def render_pdf(text: str, filename_prefix: str = "document") -> Path:
    """
    Создаёт PDF-файл из текста
    """
    file_path = GENERATED_DIR / f"{filename_prefix}_{_timestamp()}.pdf"

    c = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4

    x_margin = 20 * mm
    y_margin = 20 * mm

    x = x_margin
    y = height - y_margin

    c.setFont("Times-Roman", 11)

    for line in text.split("\n"):
        if y < y_margin:
            c.showPage()
            c.setFont("Times-Roman", 11)
            y = height - y_margin

        c.drawString(x, y, line)
        y -= 14

    c.save()
    return file_path
