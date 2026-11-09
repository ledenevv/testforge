"""Generate the synthetic lab documents that the plan scenarios upload (M9b-5).

Every patient, laboratory and result is fictional. The layout is generic and is
not a copy of any real laboratory form.

Run from the repository root:
    uv run --no-project --with reportlab scripts/make_fixture_documents.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "fixtures" / "fonts"
OUT_DIR = ROOT / "fixtures" / "documents"

pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))

BODY = ParagraphStyle("body", fontName="DejaVu", fontSize=9.5, leading=13)
TITLE = ParagraphStyle(
    "title", parent=BODY, fontName="DejaVu-Bold", fontSize=14, leading=18, spaceAfter=6
)
SMALL = ParagraphStyle(
    "small", parent=BODY, fontSize=8, leading=10, textColor=colors.HexColor("#555555")
)

PATIENT = "Иванов Иван Иванович (вымышленный пациент), мужской, 1985 г.р."
SYNTHETIC = (
    "Вымышленный документ для тестирования TestForge. Пациент, лаборатория и результаты не реальны."
)

# rows: (indicator, result, unit, reference range, laboratory flag)
DOCUMENTS = [
    {
        "file": "lab_report_001_biochem_normal.pdf",
        "title": "Биохимический анализ крови",
        "lab": "Лаборатория «Здоровье-Плюс» (условное название)",
        "date": "15.10.2026",
        "order": "БХ-2026-10-0415",
        "rows": [
            ("АЛТ (аланинаминотрансфераза)", "25", "Ед/л", "0 – 41", ""),
            ("АСТ (аспартатаминотрансфераза)", "22", "Ед/л", "0 – 40", ""),
            ("Холестерин общий", "4.9", "ммоль/л", "до 5.2", ""),
            ("Глюкоза", "5.0", "ммоль/л", "3.9 – 6.1", ""),
        ],
        "note": "",
    },
    {
        "file": "lab_report_002_cbc_anemia.pdf",
        "title": "Общий анализ крови",
        "lab": "Центр диагностики «Ориентир» (условное название)",
        "date": "20.10.2026",
        "order": "ОАК-2026-10-0520",
        "rows": [
            ("Гемоглобин", "102", "г/л", "120 – 150", "снижен"),
            ("Эритроциты", "3.6", "× 10¹²/л", "3.8 – 5.1", "снижены"),
            ("Лейкоциты", "6.1", "× 10⁹/л", "4.0 – 9.0", ""),
            ("Тромбоциты", "240", "× 10⁹/л", "180 – 320", ""),
        ],
        "note": "снижение гемоглобина и эритроцитов. Рекомендована консультация врача.",
    },
    {
        "file": "lab_report_003_thyroid_normal.pdf",
        "title": "Гормоны щитовидной железы",
        "lab": "Лаборатория «Здоровье-Плюс» (условное название)",
        "date": "01.11.2026",
        "order": "ЩЖ-2026-11-0101",
        "rows": [
            ("ТТГ (тиреотропный гормон)", "2.1", "мЕд/л", "0.4 – 4.0", ""),
            ("Т4 свободный", "15.2", "пмоль/л", "9.0 – 19.0", ""),
            ("Т3 свободный", "4.9", "пмоль/л", "2.6 – 5.7", ""),
        ],
        "note": "",
    },
    {
        "file": "lab_report_004_mixed_flags.pdf",
        "title": "Печёночные пробы и липидный профиль",
        "lab": "Центр диагностики «Ориентир» (условное название)",
        "date": "05.11.2026",
        "order": "ПП-2026-11-0505",
        "rows": [
            ("АЛТ (аланинаминотрансфераза)", "58", "Ед/л", "0 – 41", "повышен"),
            ("АСТ (аспартатаминотрансфераза)", "35", "Ед/л", "0 – 40", ""),
            ("Холестерин общий", "6.8", "ммоль/л", "до 5.2", "повышен"),
            ("Холестерин ЛПНП", "2.4", "ммоль/л", "до 3.0", ""),
        ],
        "note": "",
    },
    {
        "file": "clinical_note_005_ecg.pdf",
        "title": "Заключение: электрокардиография (ЭКГ)",
        "lab": "Кабинет функциональной диагностики (условное название)",
        "date": "03.11.2026",
        "order": "ЭКГ-2026-11-0303",
        "rows": [],
        "note": (
            "ритм синусовый, ЧСС 72 уд/мин. Интервал PQ 0.16 с, комплекс QRS 0.08 с. "
            "Сегмент ST без смещения. Выраженных изменений не выявлено."
        ),
    },
]


def build(spec: dict) -> None:
    story = [
        Paragraph(spec["title"], TITLE),
        Paragraph(f"Лаборатория: {spec['lab']}", BODY),
        Paragraph(f"Дата взятия материала: {spec['date']}", BODY),
        Paragraph(f"Номер заказа: {spec['order']}", BODY),
        Paragraph(f"Пациент: {PATIENT}", BODY),
        Spacer(1, 6 * mm),
    ]

    if spec["rows"]:
        data = [["Показатель", "Результат", "Единицы", "Референс", "Оценка"]]
        data += [list(row) for row in spec["rows"]]
        table = Table(data, colWidths=[62 * mm, 24 * mm, 30 * mm, 34 * mm, 28 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "DejaVu", 9),
                    ("FONT", (0, 0), (-1, 0), "DejaVu-Bold", 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story += [table, Spacer(1, 6 * mm)]

    if spec["note"]:
        story += [Paragraph(f"Заключение: {spec['note']}", BODY), Spacer(1, 6 * mm)]

    story.append(Paragraph(SYNTHETIC, SMALL))

    doc = SimpleDocTemplate(
        str(OUT_DIR / spec["file"]),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=spec["title"],
        author="TestForge fixtures",
        invariant=1,
    )
    doc.build(story)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in DOCUMENTS:
        build(spec)
        print("wrote", spec["file"])


if __name__ == "__main__":
    main()
