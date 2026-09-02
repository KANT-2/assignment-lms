from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_MD = ROOT / "docs" / "database" / "assignment_lms_erd.md"
SOURCE_DBML = ROOT / "docs" / "database" / "assignment_lms_erd.dbml"
OUTPUT = ROOT / "output" / "pdf" / "assignment_lms_database_erd.pdf"

FONT_REGULAR = Path(r"C:\Windows\Fonts\malgun.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")
pdfmetrics.registerFont(TTFont("Malgun", str(FONT_REGULAR)))
pdfmetrics.registerFont(TTFont("MalgunBold", str(FONT_BOLD)))

NAVY = colors.HexColor("#17365D")
BLUE = colors.HexColor("#2F67D8")
PALE_BLUE = colors.HexColor("#EAF1FF")
PALE_GRAY = colors.HexColor("#F4F6F9")
BORDER = colors.HexColor("#CBD5E1")
TEXT = colors.HexColor("#172033")
MUTED = colors.HexColor("#5F6B7A")
GREEN = colors.HexColor("#17865C")


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="KTitle", fontName="MalgunBold", fontSize=24, leading=34,
    textColor=NAVY, alignment=TA_CENTER, spaceAfter=12,
))
styles.add(ParagraphStyle(
    name="KSubtitle", fontName="Malgun", fontSize=10.5, leading=17,
    textColor=MUTED, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="KH1", fontName="MalgunBold", fontSize=17, leading=24,
    textColor=NAVY, spaceBefore=12, spaceAfter=10,
))
styles.add(ParagraphStyle(
    name="KH2", fontName="MalgunBold", fontSize=13, leading=19,
    textColor=BLUE, spaceBefore=12, spaceAfter=7,
))
styles.add(ParagraphStyle(
    name="KH3", fontName="MalgunBold", fontSize=11.5, leading=17,
    textColor=TEXT, spaceBefore=9, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="KBody", fontName="Malgun", fontSize=8.7, leading=14,
    textColor=TEXT, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="KSmall", fontName="Malgun", fontSize=7.5, leading=11,
    textColor=MUTED,
))
styles.add(ParagraphStyle(
    name="KCode", fontName="Malgun", fontSize=6.2, leading=8.5,
    textColor=TEXT, leftIndent=5, rightIndent=5,
))
styles.add(ParagraphStyle(
    name="KTable", fontName="Malgun", fontSize=7.2, leading=10,
    textColor=TEXT,
))
styles.add(ParagraphStyle(
    name="KTableHead", fontName="MalgunBold", fontSize=7.2, leading=10,
    textColor=colors.white, alignment=TA_LEFT,
))
styles.add(ParagraphStyle(
    name="KBoxTitle", fontName="MalgunBold", fontSize=8, leading=11,
    textColor=NAVY, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="KBoxWhite", fontName="MalgunBold", fontSize=8, leading=11,
    textColor=colors.white, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="KBoxBody", fontName="Malgun", fontSize=6.7, leading=9,
    textColor=TEXT, alignment=TA_CENTER,
))


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def inline(text: str) -> str:
    text = esc(text.strip())
    text = re.sub(r"`([^`]+)`", r'<font name="MalgunBold">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r'<b>\1</b>', text)
    return text


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
    canvas.setFont("Malgun", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 8 * mm, "Assignment LMS DB ERD & Table Specification")
    canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"{doc.page}")
    canvas.restoreState()


def make_table(rows: list[list[str]], widths=None):
    data = []
    for row_index, row in enumerate(rows):
        style = styles["KTableHead"] if row_index == 0 else styles["KTable"]
        data.append([Paragraph(inline(cell), style) for cell in row])
    table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_GRAY]),
    ]))
    return table


def erd_box(title: str, body: str, width: float):
    table = Table([
        [Paragraph(title, styles["KBoxTitle"])],
        [Paragraph(body, styles["KBoxBody"])],
    ], colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), PALE_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.7, BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def erd_overview():
    arrow = Paragraph("<b>→</b>", styles["KBoxTitle"])
    down = Paragraph("<b>↓</b>", styles["KBoxTitle"])
    w = 43 * mm
    story = [
        Paragraph("3. 전체 ERD - 관계 요약", styles["KH1"]),
        Paragraph(
            "파란 연결은 물리 FK이며 모두 ON DELETE CASCADE입니다. 외부 계정·팀·회차 연결은 별도 DB의 ID를 저장하는 논리 참조입니다.",
            styles["KBody"],
        ),
        Spacer(1, 5 * mm),
        Table([[erd_box("LECTURE", "강의", w), arrow, erd_box("LESSON", "날짜별 차시", w), arrow,
                erd_box("LESSON_VIDEO", "복수 영상", w)]],
              colWidths=[w, 8 * mm, w, 8 * mm, w], hAlign="CENTER"),
        Spacer(1, 4 * mm),
        Table([["", "", down, "", ""]], colWidths=[w, 8 * mm, w, 8 * mm, w], hAlign="CENTER"),
        Spacer(1, 2 * mm),
        Table([["", "", erd_box("LESSON_MATERIAL", "파일 또는 링크 교안", w), "", ""]],
              colWidths=[w, 8 * mm, w, 8 * mm, w], hAlign="CENTER"),
        Spacer(1, 10 * mm),
        Table([[erd_box("ASSIGNMENT", "개인/팀 과제", w), arrow, erd_box("SUBMISSION", "학생/팀 제출", w), arrow,
                erd_box("SUBMISSION_FILE", "복수 파일/링크", w)]],
              colWidths=[w, 8 * mm, w, 8 * mm, w], hAlign="CENTER"),
        Spacer(1, 4 * mm),
        Table([[erd_box("AI_EVALUATION", "AI 평가 0..1", w), arrow,
                erd_box("SUBMISSION", "중심 제출 엔티티", w), arrow,
                erd_box("EVALUATION", "튜터 평가 0..1", w)]],
              colWidths=[w, 8 * mm, w, 8 * mm, w], hAlign="CENTER"),
        Spacer(1, 4 * mm),
        Table([["", "", down, "", ""]], colWidths=[w, 8 * mm, w, 8 * mm, w], hAlign="CENTER"),
        Spacer(1, 2 * mm),
        Table([["", "", erd_box("GITHUB_SUBMISSION_PUSH", "GitHub 동기화 0..1", w), "", ""]],
              colWidths=[w, 8 * mm, w, 8 * mm, w], hAlign="CENTER"),
        Spacer(1, 9 * mm),
        Table([[erd_box("GRADING_POLICY", "성적 계산 정책", w), "",
                erd_box("ROUND_SCORE", "회차별 점수 스냅샷", w), "",
                erd_box("TODO", "학생 개인 할 일", w)]],
              colWidths=[w, 8 * mm, w, 8 * mm, w], hAlign="CENTER"),
        Spacer(1, 7 * mm),
        Table([[erd_box("EXTERNAL ACCOUNTS", "accounts_user / team / round\n물리 FK 없음", 145 * mm)]],
              hAlign="CENTER"),
        Spacer(1, 4 * mm),
        Paragraph(
            "외부 논리 참조 컬럼: assignment.created_by, submission.student_id, submission.team_id, "
            "submission.last_editor_id, todo.student_id, round_score.round_id, round_score.student_id, "
            "round_score.closed_by, github_student_account.student_id",
            styles["KSmall"],
        ),
        PageBreak(),
    ]
    return story


def parse_markdown(text: str):
    lines = text.splitlines()
    story = []
    i = 0
    in_mermaid = False
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("```mermaid"):
            in_mermaid = True
            i += 1
            continue
        if in_mermaid:
            if line.startswith("```"):
                in_mermaid = False
            i += 1
            continue
        if line.startswith("# "):
            i += 1
            continue
        if line.startswith("## 3."):
            while i < len(lines) and not lines[i].startswith("## 4."):
                i += 1
            continue
        if line.startswith("## "):
            story.append(Paragraph(inline(line[3:]), styles["KH1"]))
            i += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(inline(line[4:]), styles["KH2"]))
            i += 1
            continue
        if line.startswith("#### "):
            story.append(Paragraph(inline(line[5:]), styles["KH3"]))
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                available = A4[0] - 36 * mm
                col_count = max(len(row) for row in rows)
                if col_count == 4:
                    widths = [34 * mm, 35 * mm, 18 * mm, available - 87 * mm]
                elif col_count == 3:
                    widths = [42 * mm, 35 * mm, available - 77 * mm]
                else:
                    widths = [available / col_count] * col_count
                story.extend([make_table(rows, widths), Spacer(1, 4 * mm)])
            continue
        if line.startswith("```text"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            story.append(Table([[Paragraph("<br/>".join(esc(x) for x in code), styles["KCode"])]],
                               colWidths=[A4[0] - 36 * mm],
                               style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE_GRAY),
                                                 ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
                                                 ("TOPPADDING", (0, 0), (-1, -1), 7),
                                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 7)])))
            i += 1
            continue
        if re.match(r"^\d+\. ", line):
            story.append(Paragraph(inline(line), styles["KBody"]))
            i += 1
            continue
        if line.startswith("- "):
            story.append(Paragraph("• " + inline(line[2:]), styles["KBody"]))
            i += 1
            continue
        if line:
            paragraph = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||```|- |\d+\. )", lines[i]):
                paragraph.append(lines[i].strip())
                i += 1
            story.append(Paragraph(inline(" ".join(paragraph)), styles["KBody"]))
            continue
        i += 1
    return story


def dbml_appendix(text: str):
    blocks = []
    lines = text.splitlines()
    chunk_size = 72
    for start in range(0, len(lines), chunk_size):
        chunk = lines[start:start + chunk_size]
        blocks.append(Table(
            [[Paragraph("<br/>".join(esc(line).replace(" ", "&nbsp;") for line in chunk), styles["KCode"])]],
            colWidths=[A4[0] - 36 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F8FA")),
                ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        ))
        blocks.append(PageBreak())
    return blocks


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="Assignment LMS 데이터베이스 ERD 및 테이블 명세",
        author="Assignment LMS Team",
    )
    story = [
        Spacer(1, 42 * mm),
        Paragraph("Assignment LMS", styles["KTitle"]),
        Paragraph("데이터베이스 ERD 및 테이블 명세", styles["KTitle"]),
        Spacer(1, 10 * mm),
        Paragraph("우리 팀 소유 테이블 14개 통합 전달본", styles["KSubtitle"]),
        Paragraph("PostgreSQL · 기준일 2026-09-02", styles["KSubtitle"]),
        Spacer(1, 22 * mm),
        Table([
            [Paragraph("업무 테이블", styles["KBoxWhite"]), Paragraph("물리 FK", styles["KBoxWhite"]), Paragraph("외부 논리 참조", styles["KBoxWhite"])],
            [Paragraph("14개", styles["KBoxTitle"]), Paragraph("8개", styles["KBoxTitle"]), Paragraph("9개 컬럼", styles["KBoxTitle"])],
        ], colWidths=[48 * mm] * 3, hAlign="CENTER", style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, 1), PALE_BLUE),
            ("BOX", (0, 0), (-1, -1), 0.6, BLUE),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])),
        Spacer(1, 28 * mm),
        Paragraph("메인 프로젝트 DB 통합용 · 컬럼/제약조건/관계/DBML 포함", styles["KSubtitle"]),
        PageBreak(),
    ]

    md_text = SOURCE_MD.read_text(encoding="utf-8")
    before_erd, _, after_erd = md_text.partition("## 3. 전체 ERD")
    _, _, details_onward = after_erd.partition("## 4. 테이블별 상세 설명")
    story.extend(parse_markdown(before_erd))
    story.append(PageBreak())
    story.extend(erd_overview())
    story.extend(parse_markdown("## 4. 테이블별 상세 설명" + details_onward))
    story.append(PageBreak())
    story.append(Paragraph("부록 A. DBML 원본", styles["KH1"]))
    story.append(Paragraph(
        "아래 원본은 dbdiagram.io 등 DBML 지원 도구에 그대로 붙여 넣거나 import할 수 있습니다.",
        styles["KBody"],
    ))
    story.extend(dbml_appendix(SOURCE_DBML.read_text(encoding="utf-8")))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    build()
