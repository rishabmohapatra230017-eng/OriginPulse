"""Convert proof PDFs to PNG images for embedding in the submission PDF.
Uses reportlab's rlPyCairo or Pillow-based PDF rendering."""
from __future__ import annotations
from pathlib import Path
import subprocess, sys, os

PROOF_DIR = Path(__file__).resolve().parents[1] / "assets" / "proof"

def convert_pdf_to_png(pdf_path: Path, out_path: Path, dpi: int = 150) -> bool:
    """Try multiple methods to convert PDF to PNG."""
    
    # Method 1: Try pdf2image (requires poppler)
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(str(pdf_path), dpi=dpi, first_page=1, last_page=1)
        if images:
            images[0].save(str(out_path), "PNG")
            print(f"Converted {pdf_path.name} -> {out_path.name} (pdf2image)")
            return True
    except Exception as e:
        print(f"pdf2image failed: {e}")

    # Method 2: Try pymupdf
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(pdf_path))
        page = doc[0]
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat)
        pix.save(str(out_path))
        print(f"Converted {pdf_path.name} -> {out_path.name} (pymupdf)")
        return True
    except Exception as e:
        print(f"pymupdf failed: {e}")

    # Method 3: Try ghostscript
    try:
        result = subprocess.run(
            ["gs", "-dNOPAUSE", "-dBATCH", f"-r{dpi}", "-sDEVICE=png16m",
             f"-sOutputFile={out_path}", str(pdf_path)],
            capture_output=True, timeout=30
        )
        if result.returncode == 0 and out_path.exists():
            print(f"Converted {pdf_path.name} -> {out_path.name} (ghostscript)")
            return True
    except Exception as e:
        print(f"ghostscript failed: {e}")

    return False


if __name__ == "__main__":
    jira_pdf = PROOF_DIR / "jira_board.pdf"
    jira_png = PROOF_DIR / "jira_board.png"
    slack_pdf = PROOF_DIR / "slack_message.pdf"
    slack_png = PROOF_DIR / "slack_message.png"

    ok1 = convert_pdf_to_png(jira_pdf, jira_png)
    ok2 = convert_pdf_to_png(slack_pdf, slack_png)

    if ok1 and ok2:
        print("Both proof images generated successfully!")
    else:
        print("Some conversions failed. Install pymupdf: pip install pymupdf")
        sys.exit(1)
