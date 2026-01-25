from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting, Submission, Test, TestQuestion, User, Certificate


# ---------------- Settings ----------------

async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    res = await session.execute(select(Setting).where(Setting.key == key))
    obj = res.scalar_one_or_none()
    if obj is None:
        return default
    return obj.value or default


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    res = await session.execute(select(Setting).where(Setting.key == key))
    obj = res.scalar_one_or_none()
    if obj is None:
        obj = Setting(key=key, value=value)
        session.add(obj)
    else:
        obj.value = value
    await session.commit()


# ---------------- Users ----------------

async def get_or_create_user(session: AsyncSession, tg_id: int, first_name: str, last_name: str, username: str) -> User:
    res = await session.execute(select(User).where(User.tg_id == tg_id))
    user = res.scalar_one_or_none()
    if user is None:
        user = User(tg_id=tg_id, first_name=first_name, last_name=last_name, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user(session: AsyncSession, tg_id: int) -> Optional[User]:
    res = await session.execute(select(User).where(User.tg_id == tg_id))
    return res.scalar_one_or_none()


async def mark_registered(session: AsyncSession, tg_id: int, phone: str) -> None:
    res = await session.execute(select(User).where(User.tg_id == tg_id))
    user = res.scalar_one()
    user.phone = phone or ""
    user.is_registered = True
    await session.commit()


async def set_user_baseline(session: AsyncSession, tg_id: int, is_baseline: bool) -> None:
    res = await session.execute(select(User).where(User.tg_id == tg_id))
    user = res.scalar_one()
    user.is_baseline = is_baseline
    await session.commit()


# ---------------- Tests ----------------

async def list_tests_by_category(session: AsyncSession, category: str) -> List[Tuple[int, str]]:
    res = await session.execute(select(Test).where(Test.category == category).order_by(Test.id.asc()))
    tests = res.scalars().all()
    return [(t.id, t.name) for t in tests]


async def get_test(session: AsyncSession, test_id: int) -> Test:
    res = await session.execute(select(Test).where(Test.id == test_id))
    return res.scalar_one()


async def get_correct_answers(session: AsyncSession, test_id: int) -> Dict[int, str]:
    res = await session.execute(select(TestQuestion).where(TestQuestion.test_id == test_id).order_by(TestQuestion.q_num.asc()))
    qs = res.scalars().all()
    return {q.q_num: q.correct_answer for q in qs}


async def create_test(
    session: AsyncSession,
    *,
    category: str,
    name: str,
    num_questions: int,
    pdf_path: str,
    correct_answers: Dict[int, str],
    is_rasch: bool,
) -> Test:
    t = Test(category=category, name=name, num_questions=num_questions, pdf_path=pdf_path, is_rasch=is_rasch)
    session.add(t)
    await session.commit()
    await session.refresh(t)

    for q in range(1, num_questions + 1):
        session.add(TestQuestion(test_id=t.id, q_num=q, correct_answer=(correct_answers.get(q, "") or "").strip()))
    await session.commit()
    return t


async def replace_test_pdf(session: AsyncSession, test_id: int, pdf_path: str) -> None:
    t = await get_test(session, test_id)
    t.pdf_path = pdf_path
    await session.commit()
    # any edit enables users to check again
    await delete_nonbaseline_attempts_for_test(session, test_id)


async def replace_test_name(session: AsyncSession, test_id: int, new_name: str) -> None:
    t = await get_test(session, test_id)
    t.name = (new_name or "").strip() or t.name
    await session.commit()


async def replace_test_answers(session: AsyncSession, test_id: int, correct_answers: Dict[int, str]) -> None:
    # delete existing questions and recreate
    await session.execute(delete(TestQuestion).where(TestQuestion.test_id == test_id))
    t = await get_test(session, test_id)
    for q in range(1, t.num_questions + 1):
        session.add(TestQuestion(test_id=test_id, q_num=q, correct_answer=(correct_answers.get(q, "") or "").strip()))
    await session.commit()
    await delete_nonbaseline_attempts_for_test(session, test_id)


async def delete_test(session: AsyncSession, test_id: int) -> None:
    await session.execute(delete(Test).where(Test.id == test_id))
    await session.commit()


# ---------------- Submissions ----------------

async def save_submission(
    session: AsyncSession,
    *,
    tg_id: int,
    test_id: int,
    answers: Dict[int, str],
    raw_correct: int,
    total: int,
    score: float,
    is_rasch: bool,
) -> Submission:
    res = await session.execute(select(User).where(User.tg_id == tg_id))
    user = res.scalar_one()
    sub = Submission(
        user_id=user.id,
        test_id=test_id,
        answers_json=json.dumps({str(k): v for k, v in answers.items()}, ensure_ascii=False),
        raw_correct=raw_correct,
        total=total,
        score=score,
        is_rasch=is_rasch,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def list_answer_matrices_for_test(session: AsyncSession, test_id: int) -> List[List[bool]]:
    """Returns list of boolean correctness arrays for each submission (baseline+real), in chronological order."""
    test = await get_test(session, test_id)
    correct = await get_correct_answers(session, test_id)
    res = await session.execute(select(Submission).where(Submission.test_id == test_id).order_by(Submission.id.asc()))
    subs = res.scalars().all()
    matrices: List[List[bool]] = []
    for s in subs:
        try:
            ans = json.loads(s.answers_json or "{}")
        except Exception:
            ans = {}
        row = []
        from app.services.scoring import normalize_answer
        for q in range(1, test.num_questions + 1):
            ua = normalize_answer(ans.get(str(q), "") or "")
            ca = normalize_answer(correct.get(q, "") or "")
            row.append(ua != "" and ua == ca)
        matrices.append(row)
    return matrices


async def get_latest_submission(session: AsyncSession, tg_id: int, test_id: int) -> Optional[Submission]:
    resu = await session.execute(select(User).where(User.tg_id == tg_id))
    user = resu.scalar_one_or_none()
    if not user:
        return None
    res = await session.execute(
        select(Submission).where(Submission.user_id == user.id, Submission.test_id == test_id).order_by(Submission.id.desc())
    )
    return res.scalars().first()


async def delete_submissions_for_user_test(session: AsyncSession, tg_id: int, test_id: int) -> None:
    """Deletes ALL submissions for (tg_id, test_id) (user or baseline)."""
    resu = await session.execute(select(User).where(User.tg_id == tg_id))
    user = resu.scalar_one_or_none()
    if not user:
        return
    await session.execute(delete(Submission).where(Submission.user_id == user.id, Submission.test_id == test_id))
    await session.commit()


async def delete_nonbaseline_attempts_for_test(session: AsyncSession, test_id: int) -> None:
    """When admin edits a test, allow users to check again by clearing non-baseline attempts + certificates."""
    # delete submissions of non-baseline users
    res = await session.execute(select(User.id).where(User.is_baseline == False))  # noqa: E712
    non_ids = [r[0] for r in res.all()]
    if non_ids:
        await session.execute(delete(Submission).where(Submission.test_id == test_id, Submission.user_id.in_(non_ids)))
        await session.execute(delete(Certificate).where(Certificate.test_id == test_id, Certificate.user_id.in_(non_ids)))
        await session.commit()


async def list_baseline_done_indices(session: AsyncSession, test_id: int) -> List[int]:
    """Returns list of baseline indices (1..10) that already submitted for this test."""
    res = await session.execute(
        select(User.tg_id)
        .join(Submission, Submission.user_id == User.id)
        .where(Submission.test_id == test_id, User.is_baseline == True)  # noqa: E712
    )
    tg_ids = {int(r[0]) for r in res.all()}
    out = []
    for i in range(1, 11):
        if -i in tg_ids:
            out.append(i)
    return out


# ---------------- Baseline (Rasch) ----------------

async def ensure_baseline_users(session: AsyncSession) -> List[User]:
    """
    Global 10 ta baseline user (tg_id: -1..-10) yaratib qo‘yadi.
    Bu userlar faqat Rasch bazasi uchun ishlatiladi.
    """
    users: List[User] = []
    for i in range(1, 11):
        tg_id = -i
        res = await session.execute(select(User).where(User.tg_id == tg_id))
        u = res.scalar_one_or_none()
        if not u:
            u = User(
                tg_id=tg_id,
                first_name=f"Baseline{i}",
                last_name="",
                username="",
                phone="",
                is_registered=True,
                is_baseline=True,
            )
            session.add(u)
            await session.commit()
            await session.refresh(u)
        else:
            if not u.is_baseline:
                u.is_baseline = True
                u.is_registered = True
                await session.commit()
        users.append(u)
    return users


async def count_baseline_submissions(session: AsyncSession, test_id: int) -> int:
    res = await session.execute(
        select(Submission).join(User, Submission.user_id == User.id)
        .where(Submission.test_id == test_id, User.is_baseline == True)  # noqa: E712
    )
    return len(res.scalars().all())
