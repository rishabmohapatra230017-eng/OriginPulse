from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "Origin_Medical_Role_Challenge_Rishab_Mohapatra.pdf"
TRANSCRIPT = ROOT / "transcripts" / "mock_meeting_transcript.md"
WRITEUP = ROOT / "docs" / "architecture_writeup.md"
# Accept PNG or PDF proof files
JIRA_SCREENSHOT = ROOT / "assets" / "proof" / "jira_board.png"
SLACK_SCREENSHOT = ROOT / "assets" / "proof" / "slack_message.png"
JIRA_PROOF_PDF = ROOT / "assets" / "proof" / "jira_board.pdf"
SLACK_PROOF_PDF = ROOT / "assets" / "proof" / "slack_message.pdf"


def clean(text: str) -> str:
    replacements = {
        "\u2011": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def md_to_flowables(markdown: str, styles: dict[str, ParagraphStyle]):
    flowables = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            flowables.append(Spacer(1, 0.08 * inch))
            continue
        if line.startswith("# "):
            flowables.append(Paragraph(clean(line[2:]), styles["Title2"]))
        elif line.startswith("## "):
            flowables.append(Paragraph(clean(line[3:]), styles["H1"]))
        elif line.startswith("### "):
            flowables.append(Paragraph(clean(line[4:]), styles["H2"]))
        elif re.match(r"^\d+\.\s+", line):
            flowables.append(Paragraph(clean(line), styles["Bullet"]))
        elif line.startswith("- "):
            flowables.append(Paragraph(clean("• " + line[2:]), styles["Bullet"]))
        elif line.startswith("```"):
            continue
        else:
            flowables.append(Paragraph(clean(line), styles["Body"]))
    return flowables


def screenshot_block(title: str, path: Path, styles: dict[str, ParagraphStyle], pdf_path: Path | None = None):
    items = [Paragraph(title, styles["H2"])]
    # Try PNG first, then fall back to the proof PDF converted to image
    if path.exists():
        img = Image(str(path))
        max_width = 6.5 * inch
        max_height = 4.1 * inch
        scale = min(max_width / img.drawWidth, max_height / img.drawHeight)
        img.drawWidth *= scale
        img.drawHeight *= scale
        items.extend([Spacer(1, 0.08 * inch), img])
    elif pdf_path and pdf_path.exists():
        # Proof PDF exists - reference it with a styled note
        proof_text = Paragraph(
            f"<b>Proof document:</b> <font name='Courier'>{clean(str(pdf_path.relative_to(ROOT)))}</font> "
            f"(generated from live API data &mdash; see attached PDF in assets/proof/)",
            styles["Body"],
        )
        items.extend([Spacer(1, 0.08 * inch), proof_text])
        note = Table(
            [[Paragraph(
                f"Proof PDF generated from live Jira/Slack API data<br/>"
                f"File: <font name='Courier'>{clean(str(pdf_path.relative_to(ROOT)))}</font>",
                styles["Placeholder"]
            )]],
            colWidths=[6.5 * inch],
            rowHeights=[1.2 * inch],
        )
        note.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#0052CC")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F5FF")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        items.extend([Spacer(1, 0.08 * inch), note])
    else:
        box = Table(
            [[Paragraph("Screenshot placeholder<br/>Add image at:<br/><font name='Courier'>"
                        + clean(str(path.relative_to(ROOT)))
                        + "</font>", styles["Placeholder"])]], 
            colWidths=[6.5 * inch],
            rowHeights=[2.6 * inch],
        )
        box.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#9CA3AF")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        items.extend([Spacer(1, 0.08 * inch), box])
    return KeepTogether(items)


def build_styles():
    base = getSampleStyleSheet()
    return {
        "CoverTitle": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=32,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=18,
        ),
        "Subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475569"),
            spaceAfter=10,
        ),
        "Title2": ParagraphStyle(
            "Title2",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=25,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=10,
            spaceAfter=12,
        ),
        "H1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=20,
            textColor=colors.HexColor("#1D4ED8"),
            spaceBefore=12,
            spaceAfter=7,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=10,
            spaceAfter=5,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=13,
            leftIndent=0.18 * inch,
            firstLineIndent=-0.12 * inch,
            spaceAfter=4,
        ),
        "Mono": ParagraphStyle(
            "Mono",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#111827"),
            backColor=colors.HexColor("#F3F4F6"),
            borderPadding=6,
            spaceAfter=6,
        ),
        "Placeholder": ParagraphStyle(
            "Placeholder",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#64748B"),
        ),
    }


def add_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(0.75 * inch, 0.45 * inch, "OriginPulse Automation Brief")
    canvas.drawRightString(7.75 * inch, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


def main():
    styles = build_styles()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    github_url = os.getenv("GITHUB_REPO_URL", "Add public GitHub repository URL before final submission")
    today = date.today().isoformat()

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.7 * inch,
        title="Origin Medical Role Challenge - Rishab Mohapatra",
    )

    story = []
    story.append(Spacer(1, 1.55 * inch))
    story.append(Paragraph("Origin Medical Role Challenge", styles["CoverTitle"]))
    story.append(Paragraph("Post-Meeting Automation with Groq, Jira Cloud, and Slack", styles["Subtitle"]))
    story.append(Paragraph("Prepared by Rishab Mohapatra", styles["Subtitle"]))
    story.append(Paragraph(f"Generated {today}", styles["Subtitle"]))
    story.append(Spacer(1, 0.3 * inch))
    story.append(
        Table(
            [[Paragraph("Objective", styles["H2"]), Paragraph(
                "Automate the manual coordinator workflow: read a meeting transcript, extract reliable action items, create Jira tickets, and post a polished Slack summary.",
                styles["Body"],
            )]],
            colWidths=[1.25 * inch, 5.25 * inch],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("Section 1: The Mock Meeting", styles["Title2"]))
    story.append(Paragraph("Transcript file: <font name='Courier'>transcripts/mock_meeting_transcript.md</font>", styles["Body"]))
    story.extend(md_to_flowables(read_text(TRANSCRIPT), styles))
    story.append(PageBreak())

    story.append(Paragraph("Section 2: Execution Proof", styles["Title2"]))
    story.append(Paragraph(
        "Insert clean screenshots from the live run here. The PDF builder automatically uses these files when present.",
        styles["Body"],
    ))
    story.append(screenshot_block("Jira Kanban Board - Created Action Tickets", JIRA_SCREENSHOT, styles, JIRA_PROOF_PDF))
    story.append(Spacer(1, 0.2 * inch))
    story.append(screenshot_block("Slack Channel - OriginPulse Summary Message", SLACK_SCREENSHOT, styles, SLACK_PROOF_PDF))
    story.append(PageBreak())

    story.append(Paragraph("Section 3: Architecture & Reasoning", styles["Title2"]))
    story.extend(md_to_flowables(read_text(WRITEUP), styles))
    story.append(PageBreak())

    story.append(Paragraph("Section 4: The Code", styles["Title2"]))
    story.append(Paragraph("Repository link:", styles["H2"]))
    story.append(Paragraph(clean(github_url), styles["Mono"]))
    story.append(Paragraph("Key files:", styles["H2"]))
    for path in [
        "automate_meeting.py",
        "slack_oauth_server.js",
        "requirements.txt",
        "package.json",
        ".env.example",
        "README.md",
    ]:
        story.append(Paragraph(f"• <font name='Courier'>{path}</font>", styles["Bullet"]))
    story.append(Paragraph(
        "Security note: <font name='Courier'>.env</font> is ignored by Git and must never be committed.",
        styles["Body"],
    ))

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    print(OUT)


if __name__ == "__main__":
    main()
