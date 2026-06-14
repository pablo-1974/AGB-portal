"""Etapa y curso de un grupo (ESO, Bachillerato, FP) a partir del nombre y/o curso en BD."""

from __future__ import annotations

import re
import unicodedata


def _norm_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return " ".join(text.split())


def normalize_group_name(grupo: str) -> str:
    """6º A / 6-A → 6A para reconocer etapa y curso por el código de grupo."""
    g = (grupo or "").strip()
    g = "".join(
        c for c in unicodedata.normalize("NFD", g) if unicodedata.category(c) != "Mn"
    )
    g = re.sub(r"[º°.\-]", "", g)
    g = re.sub(r"\s+", "", g)
    return g


def stage_of(*, grupo: str, curso: str | None) -> str | None:
    g = normalize_group_name(grupo)

    # El código del grupo (1A…6A, fpb1…) es más fiable que el texto de curso en BD.
    if re.match(r"^[1-4][A-Za-z]", g, re.IGNORECASE):
        return "eso"
    if re.match(r"^[56][A-Za-z]", g, re.IGNORECASE):
        return "bachillerato"
    if re.match(r"^fp[bm]\d", g, re.IGNORECASE):
        return "fp"

    c = _norm_text(curso)
    if c:
        if "eso" in c and "bach" not in c and "fp" not in c:
            return "eso"
        if "bach" in c:
            return "bachillerato"
        if re.search(r"\bfp", c):
            return "fp"
    return None


def extract_course_num(*, grupo: str, curso: str | None, stage: str) -> int | None:
    allowed_by_stage = {
        "eso": {1, 2, 3, 4},
        "bachillerato": {1, 2},
        "fp": {1, 2, 3, 4},
    }
    allowed = allowed_by_stage.get(stage, set())
    g = normalize_group_name(grupo)
    curso_s = (curso or "").strip()

    if stage == "bachillerato":
        m = re.match(r"^([56])", g, re.IGNORECASE)
        if m:
            return {5: 1, 6: 2}.get(int(m.group(1)))

    if stage == "eso":
        m = re.match(r"^(\d)", g)
        if m:
            num = int(m.group(1))
            if num in allowed:
                return num

    if stage == "fp":
        m = re.match(r"^fp([bm])(\d)", g, re.IGNORECASE)
        if m:
            cycle, num = m.group(1).lower(), int(m.group(2))
            if cycle == "b" and num in (1, 2):
                return num
            if cycle == "m" and num in (1, 2):
                return {1: 3, 2: 4}[num]

    if curso_s:
        c = _norm_text(curso_s)
        if stage == "fp":
            m = re.search(r"(\d)\D*(fpb|fpm|fp\b)", c)
            if m:
                num = int(m.group(1))
                kind = m.group(2)
                if kind == "fpm":
                    mapped = {1: 3, 2: 4}.get(num)
                    if mapped in allowed:
                        return mapped
                elif num in (1, 2):
                    return num
        else:
            m = re.search(r"(\d)", curso_s)
            if m:
                num = int(m.group(1))
                if num in allowed:
                    return num

    return None


def calendar_end_date_key(*, stage: str, course_num: int | None) -> str | None:
    if stage == "eso":
        return "end_eso"
    if stage == "bachillerato" and course_num in (1, 2):
        return {1: "end_bach1", 2: "end_bach2"}[course_num]
    if stage == "fp" and course_num in (1, 2, 3, 4):
        return {1: "end_fpb1", 2: "end_fpb2", 3: "end_fpm1", 4: "end_fpm2"}[course_num]
    return None
