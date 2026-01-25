from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas


@dataclass
class CertificateData:
    full_name: str
    test_name: str
    score_text: str
    issued_at: datetime


def _base(out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(A4))
    w, h = landscape(A4)
    # ramka
    c.rect(20, 20, w - 40, h - 40)
    return c, w, h


def _watermark(c: canvas.Canvas, w: float, h: float, text: str = "MSR") -> None:
    """Light watermark (no transparency in basic PDF, so use light gray + rotation)."""
    try:
        c.saveState()
        c.setFont("Helvetica-Bold", 80)
        c.setFillGray(0.92)
        c.translate(w / 2, h / 2)
        c.rotate(25)
        c.drawCentredString(0, 0, text)
    finally:
        try:
            c.restoreState()
        except Exception:
            pass


def render_simple_certificate(out_path: Path, data: CertificateData) -> None:
    """
    Oddiy (DTM / Prezident / Mavzu) uchun.
    """
    c, w, h = _base(out_path)
    _watermark(c, w, h, "MSR")
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(w / 2, h - 80, "SERTIFIKAT")
    c.setFont("Helvetica", 12)
    c.drawCentredString(w / 2, h - 110, "Ushbu sertifikat quyidagi ishtirokchiga taqdim etiladi:")
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(w / 2, h - 150, data.full_name)

    c.setFont("Helvetica", 12)
    c.drawString(60, h - 200, f"Test: {data.test_name}")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, h - 235, f"Natija: {data.score_text}")

    c.setFont("Helvetica", 10)
    c.drawRightString(w - 60, 60, f"Berilgan sana: {data.issued_at.strftime('%Y-%m-%d %H:%M UTC')}")
    c.showPage()
    c.save()


def render_sat_style_certificate(out_path: Path, data: CertificateData) -> None:
    """
    SAT (Math) uchun soddalashtirilgan realistik ko‘rinish.
    """
    c, w, h = _base(out_path)
    _watermark(c, w, h, "SAT • MSR")
    c.setFont("Helvetica-Bold", 22)
    c.drawString(50, h - 70, "SAT MATH PRACTICE CERTIFICATE")
    c.setFont("Helvetica", 12)
    c.drawString(50, h - 100, "Ta’qdim etiladi:")
    c.setFont("Helvetica-Bold", 20)
    c.drawString(170, h - 104, data.full_name)

    c.setFont("Helvetica", 12)
    c.drawString(50, h - 140, f"Test: {data.test_name}")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 175, f"Math Score: {data.score_text} (200–800)")

    c.setFont("Helvetica", 10)
    c.drawRightString(w - 60, 60, f"Berilgan sana: {data.issued_at.strftime('%Y-%m-%d %H:%M UTC')}")
    c.showPage()
    c.save()


def render_milliy_certificate(out_path: Path, *, full_name: str, test_name: str, percent: float, level: str, issued_at: datetime) -> None:
    c, w, h = _base(out_path)
    _watermark(c, w, h, "MILLIY • MSR")
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(w / 2, h - 80, "MILLIY SERTIFIKAT — AMALIYOT")
    c.setFont("Helvetica", 12)
    c.drawCentredString(w / 2, h - 110, "Ushbu sertifikat quyidagi ishtirokchiga taqdim etiladi:")
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(w / 2, h - 150, full_name)

    c.setFont("Helvetica", 12)
    c.drawString(60, h - 200, f"Test: {test_name}")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(60, h - 235, f"Foiz: {percent:.1f}%")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(60, h - 270, f"Daraja: {level}")

    c.setFont("Helvetica", 10)
    c.drawRightString(w - 60, 60, f"Berilgan sana: {issued_at.strftime('%Y-%m-%d %H:%M UTC')}")
    c.showPage()
    c.save()
