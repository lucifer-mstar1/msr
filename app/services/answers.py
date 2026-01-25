from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Set


_CHOICES: Set[str] = {"A", "B", "C", "D", "E", "F"}


@dataclass
class AnswerSpec:
    """Multi-answer representation.

    choices: set of selected MCQ options (A..F)
    manual: list of manual strings (can be multiple)
    """

    choices: Set[str]
    manual: List[str]


def _norm_manual(s: str, *, max_len: int = 256) -> str:
    v = (s or "").strip()
    if not v:
        return ""
    # Keep consistent comparisons across devices.
    v = v.replace("\n", " ").replace("\r", " ")
    # normalize decimal comma
    v = v.replace(",", ".")
    # remove spaces for stable matching (old behavior)
    v = v.replace(" ", "")
    return v.lower()[:max_len]


def normalize_to_spec(value: Any) -> AnswerSpec:
    """Accepts:
    - "A" / "b" / "" / manual string
    - { choices: [...], manual: [...] }
    - stored JSON like {"c":[...],"m":[...]}
    Returns normalized AnswerSpec.
    """
    choices: Set[str] = set()
    manual: List[str] = []

    # Stored JSON string?
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return AnswerSpec(set(), [])
        if s.startswith("{") and s.endswith("}"):
            try:
                obj = json.loads(s)
                value = obj
            except Exception:
                # fall back to plain string
                value = s

    if isinstance(value, dict):
        c = value.get("choices") if "choices" in value else value.get("c")
        m = value.get("manual") if "manual" in value else value.get("m")

        if isinstance(c, list):
            for x in c:
                if isinstance(x, str) and x.strip().upper() in _CHOICES:
                    choices.add(x.strip().upper())

        if isinstance(m, list):
            for x in m:
                if isinstance(x, str):
                    mm = _norm_manual(x)
                    if mm:
                        manual.append(mm)

    elif isinstance(value, list):
        # treat list as choices/manual mixed strings
        for x in value:
            if not isinstance(x, str):
                continue
            xx = x.strip()
            if len(xx) == 1 and xx.upper() in _CHOICES:
                choices.add(xx.upper())
            else:
                mm = _norm_manual(xx)
                if mm:
                    manual.append(mm)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return AnswerSpec(set(), [])
        if len(s) == 1 and s.upper() in _CHOICES:
            choices.add(s.upper())
        else:
            mm = _norm_manual(s)
            if mm:
                manual.append(mm)

    # de-duplicate manuals as a set but keep stable ordering
    seen = set()
    uniq: List[str] = []
    for x in manual:
        if x not in seen:
            seen.add(x)
            uniq.append(x)

    return AnswerSpec(choices=set(sorted(choices)), manual=uniq)


def encode_for_storage(spec: AnswerSpec) -> str:
    """JSON string for DB storage (no schema change for submissions).

    Always uses keys: c (choices), m (manual)
    """
    choices = sorted([c for c in spec.choices if c in _CHOICES])
    manual = [m for m in spec.manual if m]
    if not choices and not manual:
        # Legacy: empty == ""
        return ""
    obj = {"c": choices, "m": manual}
    # Compact for shorter DB values.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def comparable_key(value: Any) -> str:
    """Returns stable comparable string for correctness checks.

    Empty => ""
    """
    spec = normalize_to_spec(value)
    if not spec.choices and not spec.manual:
        return ""
    # choices are already upper; manuals already normalized lower
    c = "".join(sorted(spec.choices))
    m = "|".join(sorted(set(spec.manual)))
    return f"C:{c};M:{m}" if m else f"C:{c}" if c else f"M:{m}"


def is_correct(user_value: Any, correct_value: Any) -> bool:
    u = comparable_key(user_value)
    c = comparable_key(correct_value)
    return u != "" and u == c
