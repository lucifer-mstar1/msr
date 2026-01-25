from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Certificate, User


async def create_certificate_record(*, tg_id: int, test_id: int, pdf_path: str, score_text: str) -> int:
    """Returns certificate id."""
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_id == tg_id))
        user = res.scalar_one()
        cert = Certificate(user_id=user.id, test_id=test_id, pdf_path=str(pdf_path), score_text=score_text)
        session.add(cert)
        await session.commit()
        await session.refresh(cert)
        return cert.id


async def get_certificate_path(cert_id: int) -> Optional[Path]:
    async with SessionLocal() as session:
        res = await session.execute(select(Certificate).where(Certificate.id == cert_id))
        cert = res.scalar_one_or_none()
        if not cert:
            return None
        p = Path(cert.pdf_path or "")
        return p if p.exists() else None


async def get_certificate_path_for_user(*, cert_id: int, tg_id: int) -> Optional[Path]:
    """Returns certificate path only if it belongs to the given Telegram user."""
    async with SessionLocal() as session:
        resu = await session.execute(select(User).where(User.tg_id == tg_id))
        u = resu.scalar_one_or_none()
        if not u:
            return None
        res = await session.execute(select(Certificate).where(Certificate.id == cert_id, Certificate.user_id == u.id))
        cert = res.scalar_one_or_none()
        if not cert:
            return None
        p = Path(cert.pdf_path or "")
        return p if p.exists() else None
