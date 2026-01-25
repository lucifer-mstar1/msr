from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.services.answers import comparable_key


@dataclass
class CheckResult:
    raw_correct: int
    total: int
    score: float   # 0..100 (oddiy: foiz; rasch: percentil)
    per_question_correct: List[bool]


def normalize_answer(a: str) -> str:
    """Normalize answers for correctness checks.

    Backward compatible with the previous single-answer logic, but also supports:
    - multiple choices (A..F)
    - multiple manual answers

    The returned string is a stable comparable key.
    """
    try:
        return comparable_key(a)
    except Exception:
        # fail safe: behave like the old normalizer
        s = (a or "").strip()
        if not s:
            return ""
        s2 = s.replace(" ", "")
        if s2 in {"-", "_", "—", "–"}:
            return ""
        if len(s2) == 1 and s2.upper() in {"A", "B", "C", "D", "E", "F"}:
            return s2.upper()
        s2 = s2.replace(",", ".")
        return s2.lower()[:256]


def simple_check(user_answers: Dict[int, str], correct_answers: Dict[int, str], total: int) -> CheckResult:
    per = []
    raw = 0
    for q in range(1, total + 1):
        ua = normalize_answer(user_answers.get(q, ""))
        ca = normalize_answer(correct_answers.get(q, ""))
        ok = (ua != "" and ua == ca)
        per.append(ok)
        if ok:
            raw += 1
    score = (raw / max(1, total)) * 100.0
    return CheckResult(raw_correct=raw, total=total, score=score, per_question_correct=per)


# ---------------- Rasch (1PL IRT) ----------------
# Bu yerda 1PL Rasch modeli uchun JML (Joint Maximum Likelihood) usuli bilan
# item difficulty (b) va user ability (theta) ni iteratsion baholaymiz.
# Maqsad: natija "nisbiy" bo‘lsin (ishtirokchilar + 10 baseline).

def _logit(p: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    # barqaror sigmoid
    if x >= 0:
        z = math.exp(-x)
        return 1 / (1 + z)
    z = math.exp(x)
    return z / (1 + z)


def rasch_jml_calibrate(resp: List[List[int]], max_iter: int = 12) -> Tuple[List[float], List[float]]:
    """
    resp: n_users x n_items (0/1)
    returns: (thetas, bs)
    """
    n_u = len(resp)
    n_i = len(resp[0]) if n_u else 0
    if n_u == 0 or n_i == 0:
        return [], []

    # init b_i from item p-value
    bs = []
    for i in range(n_i):
        p = sum(resp[u][i] for u in range(n_u)) / max(1, n_u)
        # qiyin savol => p kichik => b katta
        bs.append(_logit(1 - p))

    # init theta_u from raw score
    thetas = []
    for u in range(n_u):
        p = sum(resp[u]) / max(1, n_i)
        thetas.append(_logit(p))

    # iterate
    for _ in range(max_iter):
        # update thetas
        for u in range(n_u):
            theta = thetas[u]
            for __ in range(2):  # 2 ta Newton qadam
                f = 0.0
                fp = 0.0
                for i in range(n_i):
                    p = _sigmoid(theta - bs[i])
                    x = resp[u][i]
                    f += (x - p)
                    fp -= (p * (1 - p))
                if abs(fp) < 1e-8:
                    break
                theta = theta - (f / fp)
                theta = max(-6.0, min(6.0, theta))
            thetas[u] = theta

        # update bs
        for i in range(n_i):
            b = bs[i]
            for __ in range(2):
                f = 0.0
                fp = 0.0
                for u in range(n_u):
                    p = _sigmoid(thetas[u] - b)
                    x = resp[u][i]
                    # b uchun gradient (minus sign)
                    f += (p - x)
                    fp += (p * (1 - p))
                if abs(fp) < 1e-8:
                    break
                b = b - (f / fp)
                b = max(-6.0, min(6.0, b))
            bs[i] = b

        # identifikatsiya: o‘rtacha b = 0
        mean_b = sum(bs) / max(1, n_i)
        bs = [b - mean_b for b in bs]
        thetas = [t - mean_b for t in thetas]

    return thetas, bs


def rasch_percentile_score(resp: List[List[bool]], target_index: int) -> float:
    """
    resp: n_users x n_items (bool)
    returns: target user percentil * 100 (0..100)
    """
    if not resp:
        return 0.0
    mat = [[1 if x else 0 for x in row] for row in resp]
    thetas, _ = rasch_jml_calibrate(mat)
    if not thetas:
        return 0.0
    target_theta = thetas[target_index]
    # percentil (<=)
    sorted_t = sorted(thetas)
    # rank
    rank = 0
    for t in sorted_t:
        if t <= target_theta + 1e-12:
            rank += 1
    return (rank / len(sorted_t)) * 100.0


def sat_scaled_from_percentile(pct: float) -> int:
    # 200..800
    pct = min(100.0, max(0.0, pct))
    return int(round(200 + 6 * pct))
